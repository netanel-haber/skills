#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["rich>=13,<15"]
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""teleport: move a coding-agent session to another machine over SSH, ready to resume in tmux there.

    teleport.py probe HOST PROGRAM [DIR]                     facts about HOST; changes nothing
    teleport.py send HOST FILE... --run CMD --prompt TEXT    move the session; print the line that resumes it
    teleport.py wait TRANSCRIPT --end REGEX --busy REGEX     wait until a running session's turn ends

Run probe and send in the session's working directory. send:
- copies each FILE (a file or a folder of the session) to the same place on HOST. A path is mapped by
  putting HOST's home, temp folder, uid and working directory in place of this machine's, also where
  the working directory is written into a folder name (with / or each non-alphanumeric as -).
  LOCAL=REMOTE names the place instead. A file replaces HOST's copy; a folder is merged; where both
  have a file, the newer one wins. The loser goes to the stash, ~/.cache/teleport/<run> on HOST.
- brings the code, if the working directory is a git work tree. The working directory on HOST (--dir;
  by default the same path, under HOST's home) becomes a clone at the same commit if it is missing.
  If it is clean at that commit, it gets the uncommitted changes and new files; otherwise they wait in
  the stash. If HOST cannot clone the repository, send sends it along and tries again.
- writes the prompt to a file, opens a tmux window in the working directory, tries the resume line once
  with a made-up session id (a wrong flag fails, and no session starts), and prints the window and the
  line.

It knows nothing about agents: the teleport skill (SKILL.md, next to this file) tells it what to move.
On HOST, it runs a copy of itself with python3 (3.7 or newer). Here, uv installs rich for the progress
bars, at its versions of the date above.
"""

import argparse
import glob
import gzip
import io
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

MARK = "@@TELEPORT@@"  # starts the line of JSON that the host sends back
FAKE_ID = "00000000-0000-0000-0000-000000000000"
ID = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|\b[0-9a-f]{12,}\b")  # a session id in --run
SHELLS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "tcsh", "csh"}
BIN_DIRS = ["~/.local/bin", "~/bin", "~/.npm-global/bin", "~/.bun/bin", "~/.volta/bin", "~/.cargo/bin",
            "~/.nvm/versions/node/*/bin", "~/.local/share/fnm/node-versions/*/installation/bin",
            "/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"]  # fmt: skip


def sh(cmd, timeout=None, **kw):
    kw.setdefault("stdin", subprocess.DEVNULL)
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, **kw)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


def git_state(d):
    top = sh(["git", "-C", str(d), "rev-parse", "--show-toplevel"]).stdout.strip()
    if not top:
        return None
    g = ["git", "-C", top]
    return {
        "top": top,
        "head": sh(g + ["rev-parse", "-q", "--verify", "HEAD"]).stdout.strip() or None,
        "branch": sh(g + ["symbolic-ref", "--short", "-q", "HEAD"]).stdout.strip() or None,
        "dirty": bool(sh(g + ["status", "--porcelain"]).stdout.strip()),
        "remotes": sorted(set(sh(g + ["remote", "-v"]).stdout.split()[1::3])),
    }


def same_path_on_host(cwd, local_home, host_home):
    """The working directory on HOST: the same path, under HOST's home if it is under the home here."""
    rel = os.path.relpath(cwd, local_home)
    return cwd if rel.startswith("..") else os.path.join(host_home, rel)


# ---------------------------------------------------------------------------------------------------
# On HOST: facts.
# ---------------------------------------------------------------------------------------------------


def find_tmux():
    found = [p for d in BIN_DIRS for p in glob.glob(os.path.expanduser(d) + "/tmux") if os.access(p, os.X_OK)]
    return shutil.which("tmux") or next(iter(found), None)


def in_window(cmd, timeout=30):
    """Run CMD in the shell of a new, throwaway tmux window, where the resume line will run. Returns its
    output, or None if there is no tmux or CMD does not finish in time."""
    tmux = find_tmux()
    tmp, sess = Path(tempfile.mkdtemp()), f"teleport-{os.getpid()}-{secrets.token_hex(2)}"
    out = tmp / "out"
    if not tmux or sh([tmux, "new-session", "-d", "-s", sess]).returncode:
        return None
    sh(
        [
            tmux,
            "send-keys",
            "-t",
            f"={sess}:",
            "-l",
            f"{{ {cmd} ; }} </dev/null >{out}.part 2>&1; mv {out}.part {out}; exit",
        ]
    )
    sh([tmux, "send-keys", "-t", f"={sess}:", "Enter"])
    end = time.time() + timeout
    while time.time() < end and not out.exists():
        time.sleep(0.5)
    sh([tmux, "kill-session", "-t", f"={sess}"])  # also stops CMD, if it still runs
    text = out.read_text(errors="replace") if out.exists() else None
    shutil.rmtree(tmp, ignore_errors=True)
    return text


def find_program(name):
    """Where login shells and the usual install folders find NAME, its version, and whether a new tmux
    window finds the same one."""
    lookup = f"command -v {shlex.quote(name)}"
    paths = []
    for shell in {os.environ.get("SHELL") or "/bin/sh", "/bin/bash"}:
        for flags in ("-lc", "-lic"):
            paths += sh([shell, flags, lookup], timeout=30).stdout.split()
    paths += [p for d in BIN_DIRS for p in glob.glob(os.path.expanduser(d) + "/" + name)]
    window = (in_window(lookup) or "").strip()
    found = []
    for p in dict.fromkeys(x for x in paths if x.startswith("/") and os.access(x, os.X_OK)):
        env = dict(os.environ, PATH=os.path.dirname(p) + os.pathsep + os.environ.get("PATH", ""))
        v = sh([p, "-V" if name == "tmux" else "--version"], timeout=30, env=env)
        version = next((x.strip() for x in (v.stdout + v.stderr).splitlines() if re.search(r"\d+\.\d+", x)), None)
        in_win = bool(window) and os.path.realpath(window) == os.path.realpath(p)
        found.append({"path": p, "version": version, "in_window": in_win})
    return found


def processes_in(d):
    """Processes that run in directory D (Linux)."""
    out = []
    for proc in glob.glob("/proc/[0-9]*"):
        try:
            if os.readlink(proc + "/cwd") == d and int(proc[6:]) != os.getpid():
                with open(proc + "/cmdline", "rb") as f:
                    out.append(f"{proc[6:]} " + f.read().replace(b"\0", b" ").decode(errors="replace")[:200])
        except OSError:
            pass
    return out


def norm_url(u):
    u = re.sub(r"^[a-z+]+://|\.git$", "", u.strip().rstrip("/"))
    return re.sub(r"^[^@/]+@", "", u).replace(":", "/", 1).lower()


def find_clones(urls, depth=4, budget=15):
    """Clones of URLS in HOST's home, a few levels deep."""
    want, found, end = {norm_url(u) for u in urls}, [], time.time() + budget
    stack = [(Path.home(), 0)]
    while stack and time.time() < end:
        d, k = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        if any(e.name == ".git" for e in entries):
            try:
                config = (d / ".git" / "config").read_text(errors="replace")
            except OSError:
                config = ""
            if any(norm_url(u) in want for u in re.findall(r"^\s*url\s*=\s*(\S+)", config, re.M)):
                found.append(os.path.realpath(d))
        elif k < depth:
            stack += [
                (Path(e.path), k + 1) for e in entries if not e.name.startswith(".") and e.is_dir(follow_symlinks=False)
            ]
    return found


def probe(req):
    home = str(Path.home())
    d = os.path.expanduser(req["dir"] or same_path_on_host(req["cwd"], req["home"], home))
    u = os.uname()
    out = {"system": f"{u.sysname} {u.release} {u.machine}", "home": home, "uid": os.getuid(),
           "tmp": tempfile.gettempdir(), "python": sys.version.split()[0], "tmux": find_tmux(),
           "program": find_program(req["program"]), "dir": {"path": d, "exists": os.path.isdir(d)}}  # fmt: skip
    if os.path.isdir(d):
        real = os.path.realpath(d)
        out["dir"].update(real=real, git=git_state(real), processes=processes_in(real))
    best = [p["path"] for p in out["program"] if p["in_window"]] + [p["path"] for p in out["program"]]
    if best:
        env = dict(os.environ, PATH=os.path.dirname(best[0]) + os.pathsep + os.environ.get("PATH", ""))
        h = sh([best[0], "--help"], timeout=30, env=env)
        out["help"] = (h.stdout or h.stderr).splitlines()[:80]
    if req["remotes"]:
        out["clones"] = find_clones(req["remotes"])
    return out


# ---------------------------------------------------------------------------------------------------
# On HOST: land. Place the files, bring the code, write the prompt, open the window, try the line.
# ---------------------------------------------------------------------------------------------------


def mapper(local, host):
    """Map a path here to the same place on HOST: home, temp folder, uid and working directory, also as
    written into folder names. One pass, longest match first, so a replacement is never replaced."""
    subs = {}
    for enc in (lambda p: p, lambda p: p.replace("/", "-"), lambda p: re.sub(r"[^A-Za-z0-9]", "-", p)):
        subs[enc(local["cwd"])] = enc(host["cwd"])
    subs.update({local["home"]: host["home"], local["tmp"]: host["tmp"]})
    keys = sorted((k for k in subs if k), key=len, reverse=True)
    pattern = re.compile("|".join(map(re.escape, keys)) + rf"|(?<![0-9]){local['uid']}(?![0-9])")
    return lambda p: pattern.sub(lambda m: subs.get(m.group(0), str(host["uid"])), p)


def same_file(a, b):
    return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()


def place(src, dst, keep, notes):
    """Put SRC at DST. A folder is merged file by file. Where DST has another file, the newer one wins,
    and the other moves to KEEP."""
    if src.is_dir():
        for f in sorted(p for p in src.rglob("*") if p.is_file()):
            place(f, dst / f.relative_to(src), keep / f.relative_to(src), notes)
        return
    if same_file(src, dst):  # already there: the stash keeps only what was replaced
        src.unlink()
        return
    if dst.is_file():
        loser = src if dst.stat().st_mtime > src.stat().st_mtime else dst
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(loser), str(keep))
        notes.append(
            f"{dst}: kept the {'copy on this host' if loser == src else 'copy sent'}, the newer; the other is {keep}"
        )
        if loser == src:
            return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def https_of(url):
    m = re.match(r"^(?:ssh://)?git@([^:/]+)[:/](.+)$", url)
    return f"https://{m.group(1)}/{m.group(2)}" if m else None


def clone(code, d, info):
    """Make D a clone at the old commit: from the repository sent along, or else from each remote."""
    sources = [str(code / "repo.bundle")] if (code / "repo.bundle").exists() else []
    sources += [x for u in info["remotes"] for x in (u, https_of(u)) if x]
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND="ssh -o BatchMode=yes")
    for src in sources:
        partial = [] if src.endswith(".bundle") else ["--filter=blob:none"]
        if sh(["git", "clone", "-q", "--no-checkout", *partial, src, d], timeout=3600, env=env).returncode == 0:
            break
        shutil.rmtree(d, ignore_errors=True)
    else:
        return None
    g = ["git", "-C", d]
    if src.endswith(".bundle") and info["remotes"]:
        sh(g + ["remote", "set-url", "origin", info["remotes"][0]])
    if (code / "commits.bundle").exists():
        sh(g + ["fetch", "-q", str(code / "commits.bundle"), "HEAD"], env=env)
    target = ["-B", info["branch"], info["head"]] if info["branch"] else ["--detach", info["head"]]
    if sh(g + ["checkout", "-q", *target], timeout=3600, env=env).returncode:
        return None
    return f"created {d} as a clone of {'the repository sent along' if src.endswith('.bundle') else src} at {info['head'][:12]}"


def bring_code(code, d, notes):
    """Bring the old work tree's code to D, only where that is safe. None: send the repository along."""
    info = json.loads((code / "info.json").read_text())
    patch, new = code / "uncommitted.patch", code / "untracked.tar"
    if not os.path.isdir(d):
        made = clone(code, d, info)
        if not made:
            return None
        notes.append(made)
    here = git_state(d)
    stash = f"The snapshot is in {code}: uncommitted.patch (git apply), untracked.tar, commits.bundle (git fetch)."
    if not here:
        return f"not applied: {d} is not a git work tree. {stash}"
    if here["head"] != info["head"]:
        return f"not applied: HEAD here is {(here['head'] or '-')[:12]}, the old HEAD was {info['head'][:12]}. {stash}"
    top = here["top"]
    if not patch.exists() and not new.exists():
        return "nothing to apply: the old work tree was clean"
    if here["dirty"]:  # applied already, by an earlier send?
        applied = not patch.exists() or not sh(["git", "-C", top, "apply", "--check", "-R", str(patch)]).returncode
        if applied and new.exists():
            with tarfile.open(new) as t:
                files = [m for m in t.getmembers() if m.isfile()]
                applied = all(same_bytes(Path(top) / m.name, t.extractfile(m).read()) for m in files)
        return f"already applied to {top}" if applied else f"not applied: the work tree here has other changes. {stash}"
    if patch.exists() and sh(["git", "-C", top, "apply", "--binary", str(patch)]).returncode:
        return f"not applied: git apply failed. {stash}"
    if new.exists():
        with tarfile.open(new) as t:
            t.extractall(top, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    return f"applied to {top}: the uncommitted changes and the new files"


def same_bytes(path, data):
    return path.is_file() and path.read_bytes() == data


def open_window(sess, name, d):
    """A detached tmux window in D. A window of an earlier send that sits at a shell prompt is replaced."""
    tmux = find_tmux()
    has = sh([tmux, "has-session", "-t", f"={sess}"]).returncode == 0
    names = sh([tmux, "list-windows", "-t", f"={sess}", "-F", "#W"]).stdout.split() if has else []
    if name in names:
        cmd = sh([tmux, "display-message", "-p", "-t", f"={sess}:{name}", "#{pane_current_command}"]).stdout.strip()
        if cmd in SHELLS:
            sh([tmux, "kill-window", "-t", f"={sess}:{name}"])
            names.remove(name)
    base, i = name, 2
    while name in names:
        name, i = f"{base}-{i}", i + 1
    where = ["new-window", "-d", "-t", f"={sess}:"] if has else ["new-session", "-d", "-s", sess]
    r = sh([tmux, *where, "-n", name, "-c", d])
    if r.returncode:
        raise RuntimeError(f"tmux: {r.stderr.strip()}")
    return f"{sess}:{name}"


def land(stash):
    stash = Path(stash)
    meta = json.loads((stash / "meta.json").read_text())
    local = meta["local"]
    host = {"home": str(Path.home()), "tmp": tempfile.gettempdir(), "uid": os.getuid()}
    d = host["cwd"] = os.path.realpath(
        os.path.expanduser(meta["dir"] or same_path_on_host(local["cwd"], local["home"], host["home"]))
    )
    to_host, notes = mapper(local, host), []
    for i, f in enumerate(meta["files"]):
        dst = Path(os.path.expanduser(f["to"] or to_host(f["from"])))
        place(stash / "files" / str(i), dst, stash / "replaced" / str(i), notes)
        notes.append(f"{f['from']} -> {dst}")
    code = None
    if (stash / "code" / "info.json").exists():
        code = bring_code(stash / "code", d, notes)
        if code is None:
            print(MARK + json.dumps({"need_repo": True}), flush=True)
            return
    os.makedirs(d, exist_ok=True)
    prompt = stash / "prompt.txt"
    prompt.write_text(meta["prompt"] + (f"\n\nCode: {code}" if code else "") + "\n")
    program = next(w for w in shlex.split(meta["run"]) if "=" not in w)
    found = (in_window(f"command -v {shlex.quote(program)}") or "").strip()
    path = "" if found else next((p["path"] for p in find_program(program)), "")
    line = (
        f'PATH={shlex.quote(os.path.dirname(path))}:"$PATH" ' if path else ""
    ) + f'{meta["run"]} "$(cat {shlex.quote(str(prompt))})"'
    (stash / "resume.sh").write_text(f"cd {shlex.quote(d)} && {line}\n")
    sid = ID.search(meta["run"])
    window = open_window(os.path.basename(program), f"tp-{sid.group(0)[:8] if sid else secrets.token_hex(3)}", d)
    check = None
    if sid:  # the line with a made-up id: a wrong flag fails here, and no session starts
        out = in_window(
            f"cd {shlex.quote(d)} && " + line.replace(sid.group(0), FAKE_ID).replace(str(prompt), "/dev/null")
        )
        check = [x for x in (out or "(no exit after 30 s)").splitlines() if x.strip()][:6]
    print(MARK + json.dumps({"window": window, "line": line, "code": code, "notes": notes, "check": check}), flush=True)


# ---------------------------------------------------------------------------------------------------
# Here: progress, the code snapshot, and the stream to HOST.
# ---------------------------------------------------------------------------------------------------


class Progress:
    """Progress bars on stderr with rich, or plain lines without it."""

    def __init__(self):
        try:
            from rich.console import Console
            from rich.progress import BarColumn, SpinnerColumn, TextColumn, TimeElapsedColumn
            from rich.progress import Progress as Bars

            columns = (
                SpinnerColumn(finished_text="✓"),
                TextColumn("{task.description}"),
                BarColumn(),
                TimeElapsedColumn(),
            )
            self.bars = Bars(*columns, console=Console(stderr=True, width=None if sys.stderr.isatty() else 120))
        except Exception:  # no rich, or a rich that changed
            self.bars = None

    def __enter__(self):
        if self.bars:
            self.bars.__enter__()
        return self

    def __exit__(self, *exc):
        if self.bars:
            self.bars.__exit__(*exc)

    def start(self, text, total=None):
        if not self.bars:
            print(f"...  {text}", file=sys.stderr, flush=True)
        return self.bars.add_task(text, total=total) if self.bars else text

    def advance(self, task, n):
        if self.bars:
            self.bars.advance(task, n)

    def done(self, task, text):
        if self.bars:
            self.bars.update(task, description=text, total=1, completed=1)
        else:
            print(f"done {text}", file=sys.stderr, flush=True)


def ssh_cmd(host):
    """ssh to HOST over one shared connection: the user's, if their ssh config makes one, else its own."""
    opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
    if not re.search(r"^controlpath (?!none$)", sh(["ssh", "-G", host]).stdout.lower(), re.M):
        ctl = os.path.join(tempfile.gettempdir(), "teleport-ssh-%C")
        opts += ["-o", "ControlMaster=auto", "-o", f"ControlPath={ctl}", "-o", "ControlPersist=60"]
    return ["ssh", *opts, host]


def die(msg):
    sys.exit(f"teleport: {msg}")


def snapshot(d, with_repo):
    """What a clone of the work tree at D lacks: uncommitted changes, new files, commits on no remote."""
    st = git_state(d)
    if not st or not st["head"]:
        return None, []
    g, files, tmp = ["git", "-C", st["top"]], [], Path(tempfile.mkdtemp())
    diff = subprocess.run(g + ["diff", "--binary", "HEAD"], capture_output=True, check=True).stdout
    if diff:
        files.append(("uncommitted.patch", diff))
    names = [n for n in sh(g + ["ls-files", "-z", "--others", "--exclude-standard"]).stdout.split("\0") if n]
    if names:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t:
            for n in names:
                t.add(os.path.join(st["top"], n), arcname=n, recursive=False)
        files.append(("untracked.tar", buf.getvalue()))
    st["unpushed"] = int(sh(g + ["rev-list", "--count", "HEAD", "--not", "--remotes"]).stdout or 0)
    if st["unpushed"]:
        sh(g + ["bundle", "create", "-q", str(tmp / "commits.bundle"), "HEAD", "--not", "--remotes"]).check_returncode()
        files.append(("commits.bundle", tmp / "commits.bundle"))
    if with_repo:
        sh(g + ["bundle", "create", "-q", str(tmp / "repo.bundle"), "--all"]).check_returncode()
        files.append(("repo.bundle", tmp / "repo.bundle"))
    st["new_files"] = len(names)
    files.append(("info.json", json.dumps(st).encode()))
    return st, [(f"code/{name}", data) for name, data in files]


def write_tar(out, entries, advance):
    with tarfile.open(fileobj=out, mode="w|", format=tarfile.PAX_FORMAT) as tar:
        for arc, src in entries:
            if isinstance(src, bytes) or src.suffix == ".jsonl":  # a transcript: cut before a line still being written
                data = src if isinstance(src, bytes) else src.read_bytes()
                data = data if isinstance(src, bytes) else data[: data.rfind(b"\n") + 1]
                info = tarfile.TarInfo(arc)
                info.size, info.mode = len(data), 0o600
                info.mtime = time.time() if isinstance(src, bytes) else src.stat().st_mtime
                tar.addfile(info, io.BytesIO(data))
            else:
                tar.add(str(src), arcname=arc, recursive=False)
            advance(len(src) if isinstance(src, bytes) else src.lstat().st_size)


def from_host(text):
    return next((json.loads(x[len(MARK) :]) for x in text.splitlines() if x.startswith(MARK)), None)


def cmd_probe(a):
    st = git_state(os.getcwd())
    req = {"program": a.program, "dir": a.dir, "cwd": os.path.realpath(os.getcwd()), "home": str(Path.home()),
           "remotes": st["remotes"] if st else []}  # fmt: skip
    with Progress() as bars:
        task = bars.start(f"probe {a.host}")
        cmd = f"python3 -I - _probe {shlex.quote(json.dumps(req))}"
        r = subprocess.run(ssh_cmd(a.host) + [cmd], input=Path(__file__).read_bytes(), capture_output=True)
        bars.done(task, f"probed {a.host}")
    facts = from_host(r.stdout.decode(errors="replace"))
    if facts is None:
        die(f"the probe on {a.host} failed: {r.stderr.decode(errors='replace')[-1500:]}")
    print(json.dumps(facts, indent=1))


def cmd_wait(a):
    """Wait until the newest line that matches --end is newer than every line that matches --busy, and
    the transcript has been quiet for 15 seconds."""
    f, end, busy, t0 = Path(a.transcript).expanduser(), re.compile(a.end), re.compile(a.busy), time.time()
    with Progress() as bars:
        task = bars.start(f"wait for the turn in {f.name} to end")
        while True:
            lines = f.read_bytes().decode(errors="replace").splitlines()
            last_end = max((i for i, x in enumerate(lines) if end.search(x)), default=-1)
            last_busy = max((i for i, x in enumerate(lines) if busy.search(x)), default=-1)
            if last_end > last_busy and time.time() - f.stat().st_mtime >= 15:
                break
            time.sleep(5)
        bars.done(task, f"the turn ended after {time.time() - t0:.0f} s")


def entries(files, meta, code):
    out = [("teleport.py", Path(__file__).resolve()), ("meta.json", json.dumps(meta).encode()), *code]
    for i, (p, _) in enumerate(files):
        if p.is_dir():
            out += [(f"files/{i}/{q.relative_to(p)}", q) for q in sorted(p.rglob("*")) if q.is_file() or q.is_symlink()]
        else:
            out.append((f"files/{i}", p))
    return out


def send_once(host, items, bars):
    total = sum(len(s) if isinstance(s, bytes) else s.lstat().st_size for _, s in items)
    task = bars.start(f"send {len(items)} files ({total / 2**20:.1f} MiB) to {host}", total)
    stash = f'"$HOME"/.cache/teleport/{time.strftime("%Y%m%d-%H%M%S")}-{secrets.token_hex(3)}'
    remote = f'set -e; umask 077; S={stash}; mkdir -p "$S"; cd "$S"; gzip -dc | tar -xf -; exec python3 -I "$S/teleport.py" _land "$S"'
    ssh = subprocess.Popen(
        ssh_cmd(host) + [remote], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    err = []
    threading.Thread(target=lambda: err.append(ssh.stderr.read()), daemon=True).start()
    try:
        with gzip.GzipFile(fileobj=ssh.stdin, mode="wb", compresslevel=1) as z:
            write_tar(z, items, lambda n: bars.advance(task, n))
        ssh.stdin.close()
    except BrokenPipeError:
        pass
    bars.done(task, f"sent {len(items)} files ({total / 2**20:.1f} MiB) to {host}")
    task = bars.start("place them, open the window, try the line")
    result = from_host(ssh.stdout.read().decode(errors="replace"))
    ssh.wait()
    if not result:
        die(f"on {host}: {b''.join(err).decode(errors='replace')[-2000:]}")
    bars.done(task, f"opened {result['window']}" if "window" in result else f"{host} cannot clone the repository")
    return result


def cmd_send(a):
    files = []
    for x in a.files:
        local, _, to = x.partition("=")
        path = Path(local).expanduser()
        if not path.exists():
            die(f"{local} does not exist here")
        files.append((path, to or None))
    cwd = os.path.realpath(os.getcwd())
    local = {"home": str(Path.home()), "tmp": tempfile.gettempdir(), "uid": os.getuid(), "cwd": cwd}
    meta = {"run": a.run, "prompt": a.prompt, "dir": a.dir, "local": local,
            "files": [{"from": str(p.resolve()), "to": to} for p, to in files]}  # fmt: skip
    t0 = time.time()
    with Progress() as bars:
        st, code = None, []
        if git_state(cwd):
            task = bars.start("snapshot the code")
            st, code = snapshot(cwd, False)
            bars.done(
                task,
                f"code: {st['top']} at {st['head'][:12]}, {st['new_files']} new files, {st['unpushed']} unpushed commits",
            )
        result = send_once(a.host, entries(files, meta, code), bars)
        if result.get("need_repo"):  # HOST cannot clone it: send the repository along
            st, code = snapshot(cwd, True)
            result = send_once(a.host, entries(files, meta, code), bars)
            if result.get("need_repo"):
                die(f"{a.host} could not clone the repository, even from the copy sent along")
    for n in result["notes"]:
        print(f"note    {n}")
    print(f"code    {result['code'] or '-'}")
    for c in result["check"] or []:
        print(f"check   {c}")
    print(f"time    {time.time() - t0:.1f} s")
    print(f"window  {result['window']}  (ssh -t {a.host} tmux attach -t {result['window']})")
    print(result["line"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe", help="facts about HOST: the program, the working directory, clones; changes nothing")
    p.add_argument("host")
    p.add_argument("program", help="the agent's program, such as claude")
    p.add_argument("dir", nargs="?", help="the working directory on HOST (default: the same path, under its home)")
    s = sub.add_parser("send", help="move the session; print the line that resumes it")
    s.add_argument("host")
    s.add_argument("files", nargs="+", metavar="FILE", help="a file or folder of the session, or LOCAL=REMOTE")
    s.add_argument(
        "--run", required=True, help="the command that resumes the session; the prompt becomes its last argument"
    )
    s.add_argument("--prompt", required=True, help="the first message to the resumed session")
    s.add_argument("--dir", help="the working directory on HOST (default: the same path, under its home)")
    w = sub.add_parser("wait", help="wait until a running session's turn ends; touch nothing")
    w.add_argument("transcript")
    w.add_argument("--end", required=True, metavar="REGEX", help="a line that ends a turn")
    w.add_argument(
        "--busy", required=True, metavar="REGEX", help="a line of work: a reply, a tool call, a user message"
    )
    a = ap.parse_args()
    {"probe": cmd_probe, "send": cmd_send, "wait": cmd_wait}[a.cmd](a)


if __name__ == "__main__":
    if sys.argv[1:2] == ["_probe"]:
        print(MARK + json.dumps(probe(json.loads(sys.argv[2]))), flush=True)
    elif sys.argv[1:2] == ["_land"]:
        land(sys.argv[2])
    else:
        main()
