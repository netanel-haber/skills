#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["rich>=13,<15"]
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""Move a coding-agent session to another machine over SSH, ready to resume there in tmux.

This script decides nothing. It copies what it is told to copy, writes the first prompt to a file,
opens a tmux window in the working directory, and prints the one line that resumes the session
there. The teleport skill (SKILL.md, next to this file) finds the paths, commands and flags for
each agent, version and host.

    uv run teleport.py probe HOST|--here [--dir DIR] [--session ID] [--find-clone URL ...] [--bin NAME ...]
    uv run teleport.py send HOST --dir DIR --run CMD --prompt TEXT
                       [--put LOCAL=REMOTE ...] [--merge LOCAL=REMOTE ...] [--code LOCAL_DIR]
                       [--path DIR ...] [--tmux-session NAME] [--compress zstd|gzip] [--dry-run]

Both take --ssh "ARGS" for extra ssh arguments, such as a port. On HOST, the same file runs with
the system python3 (3.7 or newer) and the standard library only. Here, uv installs rich for the
progress bars, at the versions of the date above; without it, the progress is plain lines.
"""

import argparse
import glob
import io
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

MARK = "@@TELEPORT@@"
SHELLS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "tcsh", "csh"}
BIN_DIRS = [
    "~/.local/bin",
    "~/bin",
    "~/.npm-global/bin",
    "~/.bun/bin",
    "~/.volta/bin",
    "~/.cargo/bin",
    "~/.nvm/versions/node/*/bin",
    "~/.local/share/fnm/node-versions/*/installation/bin",
    "~/.asdf/shims",
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/usr/bin",
    "/bin",
]


def sh(cmd, timeout=None, **kw):
    if "input" not in kw:
        kw.setdefault("stdin", subprocess.DEVNULL)
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, **kw)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


def emit(**kw):
    print(MARK + json.dumps(kw), flush=True)


def git_state(d):
    top = sh(["git", "-C", str(d), "rev-parse", "--show-toplevel"])
    if top.returncode:
        return None
    top = top.stdout.strip()
    g = ["git", "-C", top]
    return {
        "top": top,
        "head": sh(g + ["rev-parse", "-q", "--verify", "HEAD"]).stdout.strip() or None,
        "branch": sh(g + ["symbolic-ref", "--short", "-q", "HEAD"]).stdout.strip() or None,
        "dirty": bool(sh(g + ["status", "--porcelain"]).stdout.strip()),
        "remotes": sorted(set(sh(g + ["remote", "-v"]).stdout.split()[1::3])),
    }


# ----------------------------------------------------------------------------------------------
# On HOST: probe. It reports facts and changes nothing.
# ----------------------------------------------------------------------------------------------


def version_of(path, flag="--version"):
    env = dict(os.environ, PATH=os.path.dirname(path) + os.pathsep + os.environ.get("PATH", ""))
    r = sh([path, flag], timeout=30, env=env)
    for text in (r.stdout, r.stderr):
        good = [
            x.strip()
            for x in text.splitlines()
            if re.search(r"\d+\.\d+", x) and not x.lower().startswith(("warning", "error"))
        ]
        if good:
            return good[0]
    return None


def find_bins(names, shells):
    """Each program as each shell (login, and login + interactive) and the usual install folders find it."""
    found = {n: {} for n in names}
    script = "; ".join(f'printf "%s=%s\\n" {shlex.quote(n)} "$(command -v {shlex.quote(n)})"' for n in names)
    for s in shells:
        for flags in ("-lc", "-lic"):
            for line in sh([s, flags, script], timeout=30).stdout.splitlines():
                n, sep, p = line.strip().partition("=")
                if sep and n in found and p.startswith("/") and os.access(p, os.X_OK):
                    found[n].setdefault(os.path.normpath(p), []).append(f"{os.path.basename(s)} {flags}")
    for n in names:
        for d in BIN_DIRS:
            for p in sorted(glob.glob(os.path.join(os.path.expanduser(d), n))):
                if os.access(p, os.X_OK) and not os.path.isdir(p):
                    found[n].setdefault(os.path.normpath(p), []).append("install folder")
    return {
        n: [
            {
                "path": p,
                "dir": os.path.dirname(p),
                "found_by": how,
                "version": version_of(p, "-V" if n == "tmux" else "--version"),
            }
            for p, how in f.items()
        ]
        for n, f in found.items()
    }


def in_window(tmux, cmd, timeout=30):
    """Run CMD in the shell of a new, throwaway tmux window: the place where the resume line will run.
    Returns its output, or None if tmux is missing or CMD did not finish in time."""
    if not tmux:
        return None
    tmp = Path(tempfile.mkdtemp())
    out, sess = tmp / "out", f"teleport-{os.getpid()}-{secrets.token_hex(2)}"
    if sh([tmux, "new-session", "-d", "-s", sess]).returncode:
        return None
    keys = f"{{ {cmd} ; }} < /dev/null > {out}.part 2>&1; mv {out}.part {out}; exit"
    sh([tmux, "send-keys", "-t", f"={sess}:", "-l", keys])
    sh([tmux, "send-keys", "-t", f"={sess}:", "Enter"])
    end = time.time() + timeout
    while time.time() < end and not out.exists():
        time.sleep(0.5)
    sh([tmux, "kill-session", "-t", f"={sess}"])  # also stops CMD if it is still running
    text = out.read_text(errors="replace") if out.exists() else None
    shutil.rmtree(tmp, ignore_errors=True)
    return text


def window_finds(tmux, names):
    """What the shell of a new tmux window finds for each program."""
    script = "; ".join(f'printf "%s=%s\\n" {shlex.quote(n)} "$(command -v {shlex.quote(n)})"' for n in names)
    found = {}
    for line in (in_window(tmux, script) or "").splitlines():
        n, _, path = line.partition("=")
        found[n] = path or None
    return found


def login_env(names):
    shell = os.environ.get("SHELL") or "/bin/sh"
    script = "; ".join(f'printf "%s\\n" "${n}"' for n in names)
    lines = sh([shell, "-lc", script], timeout=20).stdout.splitlines()
    lines = lines[-len(names) :] if len(lines) >= len(names) else [""] * len(names)
    return {n: v or None for n, v in zip(names, lines)}


def listing(path, n=12):
    """The newest entries of a folder, two levels deep: how a program names what it keeps there."""
    p = Path(path).expanduser()
    if not p.is_dir():
        return {"exists": p.exists(), "is_dir": False}
    entries = []
    for e in p.iterdir():
        entries.append(e)
        if e.is_dir() and not e.is_symlink():
            try:
                entries += list(e.iterdir())[:200]
            except OSError:
                pass

    def mtime(e):
        try:
            return e.lstat().st_mtime
        except OSError:
            return 0

    newest = sorted(entries, key=mtime, reverse=True)[:n]
    return {"exists": True, "newest": [str(e.relative_to(p)) + ("/" if e.is_dir() else "") for e in newest]}


def processes_in(real):
    """Processes whose working directory is REAL (Linux): an agent that runs there shows up, however it started."""
    out = []
    for proc in glob.glob("/proc/[0-9]*"):
        try:
            if os.readlink(proc + "/cwd") == real and int(proc[6:]) != os.getpid():
                with open(proc + "/cmdline", "rb") as f:
                    args = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
                out.append(f"{proc[6:]} {args[:200]}")
        except (OSError, ValueError):
            pass
    return out


def norm_url(u):
    u = re.sub(r"\.git$", "", u.strip().rstrip("/"))
    u = re.sub(r"^[a-z+]+://", "", u)
    u = re.sub(r"^[^@/]+@", "", u)
    head, _, rest = u.partition("/")
    return (head.replace(":", "/", 1) + ("/" + rest if rest else "")).lower()


def find_clones(urls, roots, depth=4, budget=15):
    want, found, end = {norm_url(u) for u in urls}, [], time.time() + budget
    stack = [(Path(r).expanduser(), 0) for r in roots]
    while stack and time.time() < end:
        d, k = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        if any(e.name == ".git" for e in entries):
            try:
                cfg = (d / ".git" / "config").read_text(errors="replace")
            except OSError:
                cfg = ""
            if any(norm_url(u) in want for u in re.findall(r"^\s*url\s*=\s*(\S+)", cfg, re.M)):
                found.append(os.path.realpath(d))
            continue
        if k < depth:
            stack += [
                (Path(e.path), k + 1) for e in entries if not e.name.startswith(".") and e.is_dir(follow_symlinks=False)
            ]
    return {"found": found, "searched_all": not stack}


def probe(req):
    env = login_env(req["env"]) if req.get("env") else {}
    tmux = shutil.which("tmux") or next(
        iter(glob.glob("/usr/local/bin/tmux") + glob.glob("/opt/homebrew/bin/tmux")), None
    )
    tmux_shell = sh([tmux, "show-options", "-gv", "default-shell"]).stdout.strip() if tmux else ""
    # A new tmux window runs default-shell as a login shell; without a setting, that is the login shell.
    window_shell = tmux_shell or os.environ.get("SHELL") or "/bin/sh"
    shells = []
    for s in (window_shell, os.environ.get("SHELL"), "/bin/bash"):
        if s and os.path.exists(s) and s not in shells:
            shells.append(s)
    u = os.uname()
    out = {
        "host": socket.gethostname(),
        "system": f"{u.sysname} {u.release} {u.machine}",
        "home": str(Path.home()),
        "uid": os.getuid(),
        "tmp": tempfile.gettempdir(),
        "login_shell": os.environ.get("SHELL"),
        "window_shell": window_shell,
        "python": f"{sys.executable} {sys.version.split()[0]}",
        "zstd": shutil.which("zstd"),
        "env": env,
        "ls": {p: listing(p) for p in req.get("ls") or []},
        "bins": find_bins(list(dict.fromkeys(req["bins"] + ["tmux"])), shells),
    }
    window = window_finds(tmux, list(out["bins"]))
    for n, found in out["bins"].items():
        for b in found:
            b["in_window"] = bool(window.get(n)) and os.path.realpath(window[n]) == os.path.realpath(b["path"])
    if tmux:
        ls = sh([tmux, "list-sessions", "-F", "#S"])
        out["tmux_sessions"] = ls.stdout.split() if ls.returncode == 0 else []
    if req.get("dir"):
        p = Path(req["dir"]).expanduser()
        out["dir"] = {"given": req["dir"], "exists": p.is_dir()}
        if p.is_dir():
            real = os.path.realpath(p)
            out["dir"].update(real=real, git=git_state(real), processes_in_it=processes_in(real))
    if req.get("session"):
        out["running"] = [
            line.strip()[:300]
            for line in sh(["ps", "-eo", "pid=,args="]).stdout.splitlines()
            if req["session"] in line and "teleport.py" not in line and " _probe " not in line
        ]
    if req.get("clones"):
        out["clones"] = find_clones(req["clones"], req.get("roots") or ["~"])
    return out


# ----------------------------------------------------------------------------------------------
# On HOST: land. It places the files, writes the prompt and opens the tmux window.
# ----------------------------------------------------------------------------------------------


def same_file(a, b):
    return (
        a.is_file()
        and b.is_file()
        and not b.is_symlink()
        and a.stat().st_size == b.stat().st_size
        and a.read_bytes() == b.read_bytes()
    )


def place(src, dst, keep, notes):
    """Move SRC to DST. What DST held before moves to KEEP."""
    if not src.exists():  # an empty folder sends no entries
        src.mkdir(parents=True)
    if dst.exists() or dst.is_symlink():
        if same_file(src, dst):
            return
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(keep))
        notes.append(f"{dst} was replaced; its old copy is {keep}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def merge(src, dst, conflicts):
    """Copy the files of SRC into DST. A file that DST holds with other content stays; SRC's goes to CONFLICTS."""
    if not src.exists():
        return 0
    files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file())
    kept = 0
    for f in files:
        rel = Path(f.name) if f == src else f.relative_to(src)
        target = dst if f == src else dst / rel
        if target.exists() and not same_file(f, target):
            target, kept = conflicts / rel, kept + 1
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
    return kept


def already_applied(top, patch, untracked):
    """True if the work tree at TOP already holds the patch and the new files."""
    if patch.exists() and sh(["git", "-C", top, "apply", "--check", "--reverse", "--binary", str(patch)]).returncode:
        return False
    if untracked.exists():
        with tarfile.open(untracked) as t:
            for m in t.getmembers():
                f = t.extractfile(m) if m.isfile() else None
                target = Path(top) / m.name
                if f is None or not target.is_file() or target.read_bytes() != f.read():
                    return False
    return patch.exists() or untracked.exists()


def https_of(url):
    """git@host:owner/repo -> https://host/owner/repo, so a host without ssh keys can still clone."""
    m = re.match(r"^(?:ssh://)?git@([^:/]+)[:/](.+)$", url)
    return f"https://{m.group(1)}/{m.group(2)}" if m else None


def make_clone(code, d):
    """Create D as a clone of the old work tree's repository, at its commit. Sources, in order: the
    repository bundle (--ship-repo), then each remote, by its own URL and by https."""
    info = json.loads((code / "info.json").read_text())
    sources = [str(code / "repo.bundle")] if (code / "repo.bundle").exists() else []
    for u in info["remotes"]:
        sources += [u] + ([https_of(u)] if https_of(u) else [])
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND="ssh -o BatchMode=yes")
    errors = []
    for src in sources:
        partial = [] if src.endswith(".bundle") else ["--filter=blob:none"]
        r = sh(["git", "clone", "--quiet", "--no-checkout", *partial, src, d], timeout=3600, env=env)
        if r.returncode == 0:
            break
        errors.append(f"{src}: {(r.stderr.strip().splitlines() or ['failed'])[-1]}")
        shutil.rmtree(d, ignore_errors=True)
    else:
        return (
            None,
            f"could not create {d} (send again with --ship-repo): no clone source worked: {'; '.join(errors)[:400]}",
        )
    g = ["git", "-C", d]
    if src.endswith(".bundle") and info["remotes"]:  # point origin back at the real repository
        sh(g + ["remote", "set-url", "origin", info["remotes"][0]])
    if (code / "commits.bundle").exists():  # commits that are on no remote
        sh(g + ["fetch", "--quiet", str(code / "commits.bundle"), "HEAD"], env=env)
    if sh(g + ["cat-file", "-e", info["head"] + "^{commit}"]).returncode:
        sh(g + ["fetch", "--quiet", "origin", info["head"]], timeout=3600, env=env)
    target = ["-B", info["branch"], info["head"]] if info["branch"] else ["--detach", info["head"]]
    r = sh(g + ["checkout", "--quiet", *target], timeout=3600, env=env)
    if r.returncode:
        return None, f"cloned {src} into {d}, but could not check out {info['head'][:12]}: {r.stderr.strip()[:300]}"
    return f"created {d} as a clone of {src} at {info['head'][:12]}", None


def apply_code(code, d):
    info = json.loads((code / "info.json").read_text())
    patch, untracked = code / "uncommitted.patch", code / "untracked.tar"
    here = git_state(d)
    where = (
        f"The snapshot is in {code}: info.json, and whichever exist of uncommitted.patch (git apply"
        " --binary), untracked.tar (new files) and commits.bundle (commits on no remote; git fetch it)."
    )
    if not here:
        return f"not applied: {d} is not a git repository. {where}"
    if here["head"] != info["head"]:
        return (
            f"not applied: HEAD here is {(here['head'] or 'none')[:12]}, the old HEAD was"
            f" {(info['head'] or 'none')[:12]} ({info.get('branch') or 'detached'}). {where}"
        )
    if here["dirty"] and already_applied(here["top"], patch, untracked):
        return f"already applied to {here['top']} (by an earlier send)"
    if here["dirty"]:
        return f"not applied: the work tree here has uncommitted changes. {where}"
    if not patch.exists() and not untracked.exists():
        return f"nothing to apply: both work trees are clean at {info['head'][:12]}"
    if patch.exists():
        check = sh(["git", "-C", here["top"], "apply", "--check", "--binary", str(patch)])
        if check.returncode:
            return f"not applied: git apply --check failed: {check.stderr.strip()[:300]}. {where}"
    if untracked.exists():
        with tarfile.open(untracked) as t:
            taken = [m.name for m in t.getmembers() if (Path(here["top"]) / m.name).exists()]
        if taken:
            return f"not applied: these new files already exist here: {', '.join(taken[:5])}. {where}"
    if patch.exists():
        sh(["git", "-C", here["top"], "apply", "--binary", str(patch)]).check_returncode()
    if untracked.exists():
        with tarfile.open(untracked) as t:
            t.extractall(here["top"], **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    return f"applied to {here['top']}: the uncommitted changes and the new files of the old work tree"


def open_window(tmux, sess, win, d):
    has = sh([tmux, "has-session", "-t", f"={sess}"]).returncode == 0
    names = sh([tmux, "list-windows", "-t", f"={sess}", "-F", "#W"]).stdout.split() if has else []
    if win in names:  # a window of an earlier send: reuse it if it only shows a shell prompt
        cur = sh([tmux, "display-message", "-p", "-t", f"={sess}:{win}", "#{pane_current_command}"]).stdout.strip()
        if cur in SHELLS:
            sh([tmux, "kill-window", "-t", f"={sess}:{win}"])
            names.remove(win)
    base, i = win, 2
    while win in names:
        win, i = f"{base}-{i}", i + 1
    where = ["new-window", "-d", "-t", f"={sess}:"] if has else ["new-session", "-d", "-s", sess]
    r = sh([tmux] + where + ["-n", win, "-c", d])
    if r.returncode:
        raise RuntimeError(f"tmux failed: {r.stderr.strip()}")
    return f"{sess}:{win}"


def land(stash):
    stash = Path(stash)
    meta = json.loads((stash / "meta.json").read_text())
    notes = []
    for i, dst in enumerate(meta["put"]):
        place(stash / "put" / str(i), Path(dst).expanduser(), stash / "replaced" / str(i), notes)
    for i, dst in enumerate(meta["merge"]):
        kept = merge(stash / "merge" / str(i), Path(dst).expanduser(), stash / "conflicts" / str(i))
        if kept:
            notes.append(
                f"{kept} files in {dst} differ here and were kept; the old machine's copies are in"
                f" {stash / 'conflicts' / str(i)}"
            )
    d = os.path.realpath(os.path.expanduser(meta["dir"]))
    has_code = (stash / "code" / "info.json").is_file()
    code = None
    if not os.path.isdir(d):  # a missing directory becomes a clone of the session's repository, or empty
        made, failed = make_clone(stash / "code", d) if has_code else (None, None)
        if failed:
            raise RuntimeError(failed)
        if made:
            notes.append(made)
        os.makedirs(d, exist_ok=True)
    if has_code:
        code = apply_code(stash / "code", d)
    text = meta["prompt"] + (f"\n\nCode from the old machine: {code}" if code else "")
    prompt = stash / "prompt.txt"
    prompt.write_text(text + "".join(f"\nNote: {n}." for n in notes) + "\n")
    path = ":".join(shlex.quote(os.path.expanduser(p)) for p in meta["path"])
    line = (f'PATH={path}:"$PATH" ' if path else "") + f'{meta["run"]} "$(cat {shlex.quote(str(prompt))})"'
    (stash / "resume.sh").write_text(f"cd {shlex.quote(d)} && {line}\n")
    check = None
    if meta.get("session") and meta["session"] in meta["run"]:
        # The same line with a made-up session id: a wrong flag fails here, and no session starts.
        fake = line.replace(meta["session"], "00000000-0000-0000-0000-000000000000")
        out = in_window(meta["tmux"], f"cd {shlex.quote(d)} && {fake.replace(str(prompt), '/dev/null')}")
        out = "(no exit after 30 s; stopped)" if out is None else out
        check = [x for x in out.splitlines() if x.strip()][:6] or ["exit 0, no output"]
    target = open_window(meta["tmux"], meta["tmux_session"], meta["window"], d)
    emit(event="done", target=target, dir=d, line=line, code=code, notes=notes, stash=str(stash), check=check)


# ----------------------------------------------------------------------------------------------
# Here: progress, the git snapshot, and the stream to HOST.
# ----------------------------------------------------------------------------------------------


class UI:
    """Progress bars on stderr with rich, or plain lines without it."""

    def __init__(self):
        try:
            from rich.console import Console
            from rich.progress import (
                BarColumn,
                DownloadColumn,
                Progress,
                ProgressColumn,
                SpinnerColumn,
                TextColumn,
                TimeElapsedColumn,
                TransferSpeedColumn,
            )
            from rich.text import Text

            class Bytes(ProgressColumn):
                def __init__(self, inner):
                    super().__init__()
                    self.inner = inner

                def render(self, task):
                    return self.inner.render(task) if task.fields.get("bytes") else Text("")

            self.p = Progress(
                SpinnerColumn(finished_text="[green]✓"),
                TextColumn("{task.description}"),
                BarColumn(),
                Bytes(DownloadColumn()),
                Bytes(TransferSpeedColumn()),
                TimeElapsedColumn(),
                console=Console(stderr=True, width=None if sys.stderr.isatty() else 120),
            )
        except Exception:  # no rich, or a rich that changed: plain lines
            self.p = None
        self.t0 = {}

    def __enter__(self):
        if self.p:
            self.p.__enter__()
        return self

    def __exit__(self, *exc):
        if self.p:
            self.p.__exit__(*exc)

    def task(self, desc, total=None):
        if self.p:
            t = self.p.add_task(desc, total=total, bytes=total is not None)
        else:
            t = len(self.t0)
            print(f"...  {desc}", file=sys.stderr, flush=True)
        self.t0[t] = time.time()
        return t

    def advance(self, t, n):
        if self.p:
            self.p.advance(t, n)

    def done(self, t, desc=None):
        if self.p:
            task = next(x for x in self.p.tasks if x.id == t)
            total = task.total or task.completed or 1
            self.p.update(t, description=desc or task.description, total=total, completed=total)
            self.p.stop_task(t)
        else:
            print(f"done {desc or ''} ({time.time() - self.t0[t]:.1f} s)", file=sys.stderr, flush=True)


def ssh_cmd(host, extra):
    """ssh to HOST. It shares one connection: the user's, if their ssh config sets one up, else its own."""
    opts = ["BatchMode=yes", "ConnectTimeout=20"]
    config = sh(["ssh", "-G", *shlex.split(extra), host]).stdout.lower()
    if not re.search(r"^controlpath (?!none$)", config, re.M):
        ctl = os.path.join(tempfile.gettempdir(), "teleport-ssh-%C")
        opts += ["ControlMaster=auto", f"ControlPath={ctl}", "ControlPersist=60"]
    return ["ssh"] + [x for o in opts for x in ("-o", o)] + shlex.split(extra) + [host]


def die(msg):
    sys.exit(f"teleport: {msg}")


def snapshot_code(d):
    """The git state of the work tree at D, as (name, bytes) pairs: what a clone of it lacks."""
    st = git_state(d)
    if not st or not st["head"]:
        return None, []
    g, out = ["git", "-C", st["top"]], []
    diff = subprocess.run(g + ["diff", "--binary", "HEAD"], capture_output=True, check=True).stdout
    if diff:
        out.append(("uncommitted.patch", diff))
    listed = subprocess.run(g + ["ls-files", "-z", "--others", "--exclude-standard"], capture_output=True, check=True)
    names = [n.decode() for n in listed.stdout.split(b"\0") if n]
    if names:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t:
            for n in names:
                t.add(os.path.join(st["top"], n), arcname=n, recursive=False)
        out.append(("untracked.tar", buf.getvalue()))
    st["unpushed"] = int(sh(g + ["rev-list", "--count", "HEAD", "--not", "--remotes"]).stdout or 0)
    if st["unpushed"]:
        with tempfile.TemporaryDirectory() as tmp:
            b = Path(tmp) / "commits.bundle"
            sh(g + ["bundle", "create", "-q", str(b), "HEAD", "--not", "--remotes"]).check_returncode()
            out.append(("commits.bundle", b.read_bytes()))
    st["untracked"] = len(names)
    out.append(("info.json", json.dumps(st, indent=1).encode()))
    return st, [(f"code/{n}", data) for n, data in out]


def walk(path, arc):
    if not path.is_dir() or path.is_symlink():
        return [(arc, path)]
    return [(f"{arc}/{p.relative_to(path)}", p) for p in sorted(path.rglob("*")) if not p.is_dir() or p.is_symlink()]


def size_of(src):
    return len(src) if isinstance(src, bytes) else (src.lstat().st_size if src.is_file() else 0)


def write_tar(out, entries, advance):
    with tarfile.open(fileobj=out, mode="w|", format=tarfile.PAX_FORMAT) as tar:
        for arc, src in entries:
            if isinstance(src, bytes) or (src.is_file() and not src.is_symlink() and src.suffix == ".jsonl"):
                data = src if isinstance(src, bytes) else src.read_bytes()
                if not isinstance(src, bytes):
                    data = data[: data.rfind(b"\n") + 1]  # drop a line that is still being written
                ti = tarfile.TarInfo(arc)
                ti.size, ti.mtime, ti.mode = len(data), time.time(), 0o600
                tar.addfile(ti, io.BytesIO(data))
            elif src.is_file() and not src.is_symlink():
                ti = tar.gettarinfo(str(src), arcname=arc)
                with open(src, "rb") as f:
                    tar.addfile(ti, f)
            else:
                tar.add(str(src), arcname=arc, recursive=False)
            advance(size_of(src))


def pairs(items, flag):
    out = []
    for x in items:
        local, sep, remote = x.partition("=")
        if not sep or not local or not remote:
            die(f"{flag} takes LOCAL=REMOTE, not {x!r}")
        if not Path(local).expanduser().exists():
            die(f"{flag}: {local} does not exist here")
        out.append((Path(local).expanduser(), remote))
    return out


def cmd_probe(a):
    req = {"bins": a.bin, "dir": a.dir, "session": a.session, "env": a.env, "ls": a.ls}
    req.update(clones=a.find_clone, roots=a.search_root)
    if a.here:
        print(json.dumps(probe(req), indent=1))
        return
    if not a.host:
        die("probe needs HOST, or --here for this machine")
    with UI() as ui:
        t = ui.task(f"probe {a.host}")
        r = subprocess.run(
            ssh_cmd(a.host, a.ssh) + [f"{a.python} -I - _probe {shlex.quote(json.dumps(req))}"],
            input=Path(__file__).read_bytes(),
            capture_output=True,
        )
        ui.done(t)
    out = r.stdout.decode(errors="replace")
    for line in out.splitlines():
        if line.startswith(MARK):
            print(json.dumps(json.loads(line[len(MARK) :]), indent=1))
            return
    die(
        f"the probe on {a.host} failed (exit {r.returncode}):\n{out[-1500:]}{r.stderr.decode(errors='replace')[-1500:]}"
    )


def cmd_send(a):
    puts, merges = pairs(a.put, "--put"), pairs(a.merge, "--merge")
    if a.compress == "zstd" and not shutil.which("zstd"):
        die("--compress zstd needs zstd here; use gzip")
    nonce = secrets.token_hex(4)
    meta = {"dir": a.dir, "run": a.run, "prompt": a.prompt, "path": a.path, "tmux": a.tmux, "session": a.session}
    meta.update(tmux_session=a.tmux_session, window=a.window or f"tp-{(a.session or nonce)[:8]}")
    meta.update(put=[r for _, r in puts], merge=[r for _, r in merges])
    name = f"{time.strftime('%Y%m%d-%H%M%S')}-{nonce}"
    stash = shlex.quote(a.stash) if a.stash else f'"$HOME"/.cache/teleport/{name}'
    decompress = "zstd -dcq" if a.compress == "zstd" else "gzip -dc"
    remote = (
        f'set -e; umask 077; S={stash}; mkdir -p "$S"; cd "$S"; {decompress} | tar -xf -;'
        f' exec {a.python} -I "$S/teleport.py" _land "$S"'
    )
    t_start = time.time()
    with UI() as ui:
        entries = [("teleport.py", Path(__file__).resolve())]
        for i, (local, _) in enumerate(puts):
            entries += walk(local, f"put/{i}")
        for i, (local, _) in enumerate(merges):
            entries += walk(local, f"merge/{i}")
        if a.code:
            t = ui.task("snapshot the git state")
            st, code = snapshot_code(a.code)
            entries += code
            if a.ship_repo and st:
                bundle = Path(tempfile.mkdtemp()) / "repo.bundle"
                sh(["git", "-C", st["top"], "bundle", "create", "-q", str(bundle), "--all"]).check_returncode()
                entries.append(("code/repo.bundle", bundle))
            state = "uncommitted changes" if st and st["dirty"] else "clean"
            ui.done(
                t,
                f"git: HEAD {st['head'][:12]}, {state}, {st['untracked']} new files,"
                f" {st['unpushed']} commits on no remote"
                if st
                else "git: not a work tree with commits; nothing to send",
            )
        entries.append(("meta.json", json.dumps(meta, indent=1).encode()))
        if a.dry_run:
            files = [[arc, str(src) if isinstance(src, Path) else f"<{len(src)} bytes>"] for arc, src in entries]
            print(json.dumps({"ssh": ssh_cmd(a.host, a.ssh) + [remote], "meta": meta, "files": files}, indent=1))
            return
        t = ui.task(f"send {len(entries)} files to {a.host} ({a.compress})", total=sum(size_of(s) for _, s in entries))
        pipes = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        ssh = subprocess.Popen(ssh_cmd(a.host, a.ssh) + [remote], **pipes)
        err = []
        threading.Thread(target=lambda: err.append(ssh.stderr.read()), daemon=True).start()
        try:
            if a.compress == "zstd":
                z = subprocess.Popen(["zstd", "-T0", "-3", "-q", "-c"], stdin=subprocess.PIPE, stdout=ssh.stdin)
                sink = z.stdin
            else:
                import gzip

                z, sink = None, gzip.GzipFile(fileobj=ssh.stdin, mode="wb", compresslevel=1)
            write_tar(sink, entries, lambda n: ui.advance(t, n))
            sink.close()
            if z:
                z.wait()
            ssh.stdin.close()
        except BrokenPipeError:
            pass
        ui.done(t, f"sent {len(entries)} files to {a.host}")
        t = ui.task(f"place them and open a window in tmux session {a.tmux_session}")
        result = None
        for raw in ssh.stdout:
            line = raw.decode(errors="replace")
            if line.startswith(MARK):
                result = json.loads(line[len(MARK) :])
        ssh.wait()
        if result and not result.get("error"):
            ui.done(t, f"opened {result['target']} on {a.host} in {result['dir']}")
    if not result:
        die(
            f"the command on {a.host} failed (exit {ssh.returncode}):\n{b''.join(err).decode(errors='replace')[-2000:]}"
        )
    if result.get("error"):
        die(f"on {a.host}: {result['error']}")
    attach = shlex.join(["ssh", "-t", *shlex.split(a.ssh), a.host, "tmux", "attach", "-t", result["target"]])
    for n in result["notes"]:
        print(f"note    {n}")
    if result["code"]:
        print(f"code    {result['code']}")
    for c in result.get("check") or []:
        print(f"check   {c}")
    print(f"stash   {result['stash']}")
    print(f"time    {time.time() - t_start:.1f} s")
    print(f"window  {result['target']}  ({attach})")
    print(result["line"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe", help="print facts about HOST; change nothing")
    s = sub.add_parser("send", help="copy, write the prompt, open a tmux window, print the resume line")
    p.add_argument("host", nargs="?")
    p.add_argument("--here", action="store_true", help="probe this machine instead of HOST")
    s.add_argument("host")
    for x in (p, s):
        x.add_argument("--ssh", default="", metavar="ARGS", help='extra ssh arguments, e.g. "-p 2222"')
        x.add_argument("--python", default="python3", help="python on HOST (default python3)")
    p.add_argument("--dir", help="report this directory: real path, git state, processes that run in it")
    p.add_argument("--session", help="report processes on HOST whose command line has this id")
    p.add_argument("--find-clone", action="append", default=[], metavar="URL", help="report clones of this URL")
    p.add_argument("--search-root", action="append", default=[], metavar="DIR", help="where to look (default ~)")
    p.add_argument("--bin", action="append", default=[], metavar="NAME", help="a program to find (tmux always)")
    p.add_argument("--env", action="append", default=[], metavar="NAME", help="a variable of the login shell")
    p.add_argument("--ls", action="append", default=[], metavar="PATH", help="a folder whose newest entries to list")
    s.add_argument("--dir", required=True, help="working directory on HOST")
    s.add_argument("--run", required=True, help="command that resumes the session; the prompt is its last argument")
    s.add_argument("--prompt", required=True, help="first message to the resumed session")
    s.add_argument("--put", action="append", default=[], metavar="LOCAL=REMOTE", help="copy a file or folder")
    s.add_argument(
        "--merge", action="append", default=[], metavar="LOCAL=REMOTE", help="add files; keep differing ones"
    )
    s.add_argument(
        "--code",
        metavar="LOCAL_DIR",
        help="snapshot this git work tree; apply it in --dir if safe; if --dir is missing, clone the repository there first",
    )
    s.add_argument(
        "--ship-repo", action="store_true", help="with --code: also send the whole repository, to clone from"
    )
    s.add_argument("--session", metavar="ID", help="the id in --run; the line is tried once with a made-up id")
    s.add_argument("--path", action="append", default=[], metavar="DIR", help="put DIR first on PATH in the line")
    s.add_argument("--tmux", default="tmux", help="tmux on HOST")
    s.add_argument("--tmux-session", default="teleport", help="tmux session on HOST; created if missing")
    s.add_argument("--window", help="tmux window name (default tp-<random>)")
    s.add_argument("--stash", help="folder on HOST for this run (default ~/.cache/teleport/<time>-<random>)")
    s.add_argument("--compress", choices=["zstd", "gzip"], default="gzip", help="zstd only if both sides have it")
    s.add_argument("--dry-run", action="store_true", help="print what would be sent; send nothing")
    a = ap.parse_args()
    (cmd_probe if a.cmd == "probe" else cmd_send)(a)


if __name__ == "__main__":
    if sys.argv[1:2] == ["_probe"]:
        print(MARK + json.dumps(probe(json.loads(sys.argv[2]))), flush=True)
    elif sys.argv[1:2] == ["_land"]:
        try:
            land(sys.argv[2])
        except Exception as e:  # report to the caller instead of a bare traceback
            emit(event="done", error=f"{type(e).__name__}: {e}")
            raise
    else:
        main()
