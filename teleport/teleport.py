#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["rich>=13,<15"]
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""teleport: move a coding-agent session to another machine over SSH, ready to resume in tmux there.

    teleport.py probe HOST PROGRAM [DIR]                     facts about HOST; changes nothing
    teleport.py send HOST FILE... --run CMD --prompt TEXT    move the session; print how to resume it

Run both in the session's working directory, as `uv run --no-project --script teleport.py ...` (uv then
installs rich for the progress bars, at its versions of the date above, and never touches the project
there), or with python3. The working directory on HOST is DIR (--dir), or else the same path, under
HOST's home; send creates it if it is missing, and does nothing else with the project there. send:
- copies each FILE (a file or a folder of the session) to the same place on HOST: HOST's home, temp
  folder, uid and working directory take the place of this machine's, also where the working directory
  is written into a folder name (with / or each non-alphanumeric as -). LOCAL=REMOTE names the place
  instead. A file replaces HOST's copy, and a folder is merged; where both sides have a file, the newer
  one wins, and the other goes to the stash, ~/.cache/teleport/<run> on HOST.
- sends each transcript (a .jsonl file) up to its last complete line or, with --cut REGEX, up to its
  last line that matches REGEX: the end of the last finished turn, for a session that still runs.
- leaves out what the resumed session rebuilds or fetches: environments, packages, dependencies,
  caches, build outputs, binary artifacts (wheels, objects, tensors, archives), files over 10 MiB and
  folders over 50 MiB. Transcripts always go.
- writes the prompt to a file. It adds where the old working directory is, whether a running turn was
  cut, what was left out, and a last line: "You have been teleported using <this skill's link>. ...".
- opens a tmux window in the working directory, tries the resume line once with a made-up session id
  (a wrong flag fails, and no session starts), types the resume line into the window without running
  it, and prints how to attach. It also notes when HOST's program is older than the one here.
- removes its runs on HOST that are older than 14 days.

It knows nothing about agents: the teleport skill (SKILL.md, next to this file) tells it what to move.
On HOST, it runs a copy of itself with python3 (3.7 or newer).
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
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

SKILL = "https://raw.githubusercontent.com/netanel-haber/skills/main/teleport/SKILL.md"
MARK = "@@TELEPORT@@"  # starts the line of JSON that the host sends back
FAKE_ID = "00000000-0000-0000-0000-000000000000"
ID = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|\b[0-9a-f]{12,}\b")  # a session id in --run
SHELLS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "tcsh", "csh"}
REBUILT = {"node_modules", "__pycache__", ".venv", "venv", "site-packages", ".cache", ".ruff_cache", ".mypy_cache",
           ".pytest_cache", ".tox", ".gradle", ".next", "target", "build", "dist"}  # fmt: skip
ARTIFACTS = {".whl", ".so", ".o", ".a", ".pyc", ".pt", ".pth", ".bin", ".safetensors", ".ckpt", ".npy", ".npz",
             ".onnx", ".engine", ".tar", ".gz", ".tgz", ".zip", ".xz", ".zst", ".bz2", ".deb", ".rpm"}  # fmt: skip
BIG, BIG_FOLDER, STASH_DAYS = 10 * 2**20, 50 * 2**20, 14
BIN_DIRS = ["~/.local/bin", "~/bin", "~/.npm-global/bin", "~/.bun/bin", "~/.volta/bin", "~/.cargo/bin",
            "~/.nvm/versions/node/*/bin", "~/.local/share/fnm/node-versions/*/installation/bin",
            "/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"]  # fmt: skip


def sh(cmd, timeout=None, **kw):
    kw.setdefault("stdin", subprocess.DEVNULL)
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, **kw)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


def version_of(path, flag="--version"):
    """PATH's version line, and its numbers, such as (2, 1, 319)."""
    env = dict(os.environ, PATH=os.path.dirname(path) + os.pathsep + os.environ.get("PATH", ""))
    r = sh([path, flag], timeout=30, env=env)
    line = next((x.strip() for x in (r.stdout + r.stderr).splitlines() if re.search(r"\d+\.\d+", x)), None)
    m = re.search(r"\d+(?:\.\d+)+", line or "")
    return line, tuple(int(x) for x in m.group(0).split(".")) if m else ()


def host_dir(given, cwd, local_home, host_home):
    """The working directory on HOST: GIVEN, or else the same path, under HOST's home."""
    rel = os.path.relpath(cwd, local_home)
    return os.path.expanduser(given or (cwd if rel.startswith("..") else os.path.join(host_home, rel)))


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
    keys = f"{{ {cmd} ; }} </dev/null >{out}.part 2>&1; mv {out}.part {out}; exit"
    sh([tmux, "send-keys", "-t", f"={sess}:", "-l", keys])
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
        in_win = bool(window) and os.path.realpath(window) == os.path.realpath(p)
        found.append(
            {"path": p, "version": version_of(p, "-V" if name == "tmux" else "--version")[0], "in_window": in_win}
        )
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


def probe(req):
    home = str(Path.home())
    d = host_dir(req["dir"], req["cwd"], req["home"], home)
    u = os.uname()
    out = {"system": f"{u.sysname} {u.release} {u.machine}", "home": home, "uid": os.getuid(),
           "tmp": tempfile.gettempdir(), "python": sys.version.split()[0], "tmux": find_tmux(),
           "program": find_program(req["program"]), "dir": {"path": d, "exists": os.path.isdir(d)}}  # fmt: skip
    if os.path.isdir(d):
        out["dir"]["processes"] = processes_in(os.path.realpath(d))
    best = [p["path"] for p in out["program"] if p["in_window"]] + [p["path"] for p in out["program"]]
    if best:
        env = dict(os.environ, PATH=os.path.dirname(best[0]) + os.pathsep + os.environ.get("PATH", ""))
        h = sh([best[0], "--help"], timeout=30, env=env)
        out["help"] = (h.stdout or h.stderr).splitlines()[:80]
    return out


# ---------------------------------------------------------------------------------------------------
# On HOST: land. Place the files, write the prompt, open the window, try the line, type it in.
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


def place(src, dst, keep, notes):
    """Put SRC at DST; a folder is merged, file by file. Where DST holds another file, the newer one wins,
    and the other moves to KEEP."""
    if not src.exists():  # a folder with nothing to send
        dst.mkdir(parents=True, exist_ok=True)
        return
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(p for p in src.rglob("*") if p.is_file()):
            place(f, dst / f.relative_to(src), keep / f.relative_to(src), notes)
        return
    if dst.is_file() and dst.read_bytes() == src.read_bytes():
        src.unlink()  # already there; the stash keeps only what was replaced
        return
    if dst.is_file():
        older = src if dst.stat().st_mtime > src.stat().st_mtime else dst
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(older), str(keep))
        notes.append(f"{dst}: kept the newer copy; the older one is {keep}")
        if older == src:
            return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


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


def remove_made_up(near):
    """Remove what a program made for the made-up id: entries named after it, next to the places where
    the session's files went (in their folders and the three folders above, two levels deep)."""
    for folder in {a for p in near for a in list(Path(p).parents)[:3]}:
        for q in [*folder.glob("*"), *folder.glob("*/*")]:
            if FAKE_ID in q.name and q.exists():
                shutil.rmtree(q, ignore_errors=True) if q.is_dir() else q.unlink()


def try_line(line, sid, prompt, d, near):
    """The resume line, run once in a throwaway window with a made-up id: a wrong flag fails, and no
    session starts."""
    trial = line.replace(sid, FAKE_ID).replace(str(prompt), "/dev/null")
    out = in_window(f"cd {shlex.quote(d)} && {trial}") or "(no exit after 30 s)"
    remove_made_up(near)
    return [x for x in out.splitlines() if x.strip()][:6]


def land(stash):
    stash = Path(stash)
    meta = json.loads((stash / "meta.json").read_text())
    local = meta["local"]
    for old in stash.parent.iterdir():  # runs older than STASH_DAYS
        if old != stash and time.time() - old.stat().st_mtime > STASH_DAYS * 86400:
            shutil.rmtree(old, ignore_errors=True)
    host = {"home": str(Path.home()), "tmp": tempfile.gettempdir(), "uid": os.getuid()}
    d = host["cwd"] = os.path.realpath(host_dir(meta["dir"], local["cwd"], local["home"], host["home"]))
    os.makedirs(d, exist_ok=True)
    to_host, notes, placed = mapper(local, host), [], []
    for i, f in enumerate(meta["files"]):
        dst = Path(os.path.expanduser(f["to"] or to_host(f["from"])))
        place(stash / "files" / str(i), dst, stash / "replaced" / str(i), notes)
        notes.append(f"{f['from']} -> {dst}")
        placed.append(dst)
    if meta["left_out"]:
        notes.append(f"not sent: {len(meta['left_out'])} environments, packages, caches, builds or artifacts")
    prompt = stash / "prompt.txt"
    prompt.write_text(
        meta["prompt"]
        + f"\n\nThe old working directory, {local['host']}:{local['cwd']}, keeps its files, uncommitted changes and"
        + " builds; take from there what the work needs."
        + (
            "\n\nThe turn that was still running in the old session when you moved is not in this copy;"
            + " what it did, it did in the old working directory."
            if meta["cut"]
            else ""
        )
        + (f"\n\nNot sent: {', '.join(meta['left_out'][:40])}" if meta["left_out"] else "")
        + f"\n\nYou have been teleported using {SKILL}. Recover: set up here what the work needs (the project,"
        + " its dependencies, what was not sent). Stop or pick up the jobs that the old session left running,"
        + " but do not duplicate or ignore them. Then continue the work.\n"
    )
    program = next(w for w in shlex.split(meta["run"]) if "=" not in w)
    found = (in_window(f"command -v {shlex.quote(program)}") or "").strip()
    path = found if found.startswith("/") else next((p["path"] for p in find_program(program)), "")
    host_version = version_of(path) if path else (None, ())
    if host_version[1] and meta["version"][1] and host_version[1] < tuple(meta["version"][1]):
        notes.append(
            f"{program} on this host is older ({host_version[0]}) than on {local['host']} ({meta['version'][0]})"
        )
    prefix = f'PATH={shlex.quote(os.path.dirname(path))}:"$PATH" ' if path and not found else ""
    line = f'{prefix}{meta["run"]} "$(cat {shlex.quote(str(prompt))})"'
    (stash / "resume.sh").write_text(f"cd {shlex.quote(d)} && {line}\n")
    sid = ID.search(meta["run"])
    window = open_window(os.path.basename(program), f"tp-{sid.group(0)[:8] if sid else secrets.token_hex(3)}", d)
    check = try_line(line, sid.group(0), prompt, d, placed) if sid else None
    sh([find_tmux(), "send-keys", "-t", f"={window}", "-l", line])  # typed in, not run: Enter starts it
    print(MARK + json.dumps({"window": window, "line": line, "notes": notes, "check": check}), flush=True)


# ---------------------------------------------------------------------------------------------------
# Here: what to send, the stream to HOST, and progress.
# ---------------------------------------------------------------------------------------------------


def folder_size(path, limit):
    """The bytes of the files under PATH other than transcripts, counted up to LIMIT."""
    total = 0
    for d, _, names in os.walk(path):
        for n in names:
            f = os.path.join(d, n)
            if not n.endswith(".jsonl") and not os.path.islink(f):
                total += os.path.getsize(f)
                if total > limit:
                    return total
    return total


def rebuilt(path):
    """True for what the resumed session rebuilds or fetches itself: environments, installed or unpacked
    packages, dependencies, caches, build outputs, binary artifacts, big files and big folders."""
    if path.is_dir() and not path.is_symlink():
        package = any(c.suffix in (".dist-info", ".egg-info") for c in path.iterdir())
        return (
            path.name in REBUILT
            or (path / "pyvenv.cfg").exists()
            or package
            or folder_size(path, BIG_FOLDER) > BIG_FOLDER
        )
    if not path.is_file() or path.is_symlink() or path.suffix == ".jsonl":
        return False
    return path.suffix in ARTIFACTS or path.stat().st_size > BIG


def sendable(root, left_out):
    """The files under ROOT to send. What is left out goes to LEFT_OUT."""
    for d, dirs, names in os.walk(root):
        for x in [x for x in dirs if rebuilt(Path(d) / x)]:
            dirs.remove(x)
            left_out.append(os.path.join(d, x) + "/")
        for n in sorted(names):
            f = Path(d) / n
            if rebuilt(f):
                left_out.append(str(f))
            else:
                yield f


def transcript(path, cut):
    """A transcript up to its last complete line, or, with CUT, up to its last line that matches CUT.
    Also whether CUT dropped lines: a turn that was still running."""
    data = path.read_bytes()
    lines = data[: data.rfind(b"\n") + 1].splitlines(keepends=True)
    ends = [i for i, x in enumerate(lines) if cut and cut.search(x.decode(errors="replace"))]
    kept = lines[: ends[-1] + 1] if ends else lines
    return b"".join(kept), len(kept) < len(lines)


def bundle(files, meta, cut):
    """The entries of the send, as (name, path, data): DATA, when set, is sent in place of PATH's bytes."""
    items, meta["left_out"], meta["cut"] = [("teleport.py", Path(__file__).resolve(), None)], [], False
    for i, (p, _) in enumerate(files):
        paths = (
            [(f"files/{i}/{f.relative_to(p)}", f) for f in sendable(p, meta["left_out"])]
            if p.is_dir()
            else [(f"files/{i}", p)]
        )
        for name, f in paths:
            if f.suffix == ".jsonl" and not f.is_symlink():
                data, dropped = transcript(f, cut)
                meta["cut"] |= dropped
                items.append((name, f, data))
            else:
                items.append((name, f, None))
    return [*items, ("meta.json", None, json.dumps(meta).encode())]


def write_tar(out, items, advance):
    with tarfile.open(fileobj=out, mode="w|", format=tarfile.PAX_FORMAT) as tar:
        for name, path, data in items:
            if data is None:
                tar.add(str(path), arcname=name, recursive=False)
            else:
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = len(data), 0o600, path.stat().st_mtime if path else time.time()
                tar.addfile(info, io.BytesIO(data))
            advance(len(data) if data is not None else path.lstat().st_size)


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


def from_host(text):
    return next((json.loads(x[len(MARK) :]) for x in text.splitlines() if x.startswith(MARK)), None)


def cmd_probe(a):
    req = {"program": a.program, "dir": a.dir, "cwd": os.path.realpath(os.getcwd()), "home": str(Path.home())}
    with Progress() as bars:
        task = bars.start(f"probe {a.host}")
        cmd = f"python3 -I - _probe {shlex.quote(json.dumps(req))}"
        r = subprocess.run(ssh_cmd(a.host) + [cmd], input=Path(__file__).read_bytes(), capture_output=True)
        bars.done(task, f"probed {a.host}")
    facts = from_host(r.stdout.decode(errors="replace"))
    if facts is None:
        die(f"the probe on {a.host} failed: {r.stderr.decode(errors='replace')[-1500:]}")
    print(json.dumps(facts, indent=1))


def cmd_send(a):
    files = []
    for x in a.files:
        local, _, to = x.partition("=")
        path = Path(local).expanduser()
        if not path.exists():
            die(f"{local} does not exist here")
        files.append((path, to or None))
    program = next(w for w in shlex.split(a.run) if "=" not in w)
    here = shutil.which(program)
    local = {"host": socket.gethostname(), "home": str(Path.home()), "tmp": tempfile.gettempdir(),
             "uid": os.getuid(), "cwd": os.path.realpath(os.getcwd())}  # fmt: skip
    meta = {"run": a.run, "prompt": a.prompt, "dir": a.dir, "local": local, "version": version_of(here) if here else (None, ()),
            "files": [{"from": str(p.resolve()), "to": to} for p, to in files]}  # fmt: skip
    items, t0 = bundle(files, meta, re.compile(a.cut) if a.cut else None), time.time()
    total = sum(len(d) if d is not None else p.lstat().st_size for _, p, d in items)
    size = f"{len(items)} files ({total / 2**20:.1f} MiB)"
    stash = f'"$HOME"/.cache/teleport/{time.strftime("%Y%m%d-%H%M%S")}-{secrets.token_hex(3)}'
    remote = f'set -e; umask 077; S={stash}; mkdir -p "$S"; cd "$S"; gzip -dc | tar -xf -; exec python3 -I "$S/teleport.py" _land "$S"'
    with Progress() as bars:
        task = bars.start(f"send {size} to {a.host}", total)
        ssh = subprocess.Popen(
            ssh_cmd(a.host) + [remote], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        err = []
        threading.Thread(target=lambda: err.append(ssh.stderr.read()), daemon=True).start()
        try:
            with gzip.GzipFile(fileobj=ssh.stdin, mode="wb", compresslevel=1) as z:
                write_tar(z, items, lambda n: bars.advance(task, n))
            ssh.stdin.close()
        except BrokenPipeError:
            pass
        bars.done(task, f"sent {size} to {a.host}")
        task = bars.start("place them, open the window, try the line")
        result = from_host(ssh.stdout.read().decode(errors="replace"))
        ssh.wait()
        if not result:
            die(f"on {a.host}: {b''.join(err).decode(errors='replace')[-2000:]}")
        bars.done(task, f"opened {result['window']}")
    for n in result["notes"]:
        print(f"note    {n}")
    for c in result["check"] or []:
        print(f"check   {c}")
    print(f"time    {time.time() - t0:.1f} s")
    print(f"line    {result['line']}")
    print(f"resume  ssh -t {a.host} tmux attach -t {result['window']}   (then press Enter: the line is typed in)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe", help="facts about HOST: the program and the working directory; changes nothing")
    p.add_argument("host")
    p.add_argument("program", help="the agent's program, such as claude")
    p.add_argument("dir", nargs="?", help="the working directory on HOST (else the same path, under its home)")
    s = sub.add_parser("send", help="move the session; print how to resume it")
    s.add_argument("host")
    s.add_argument("files", nargs="+", metavar="FILE", help="a file or folder of the session, or LOCAL=REMOTE")
    s.add_argument(
        "--run", required=True, help="the command that resumes the session; the prompt becomes its last argument"
    )
    s.add_argument("--prompt", required=True, help="the first message to the resumed session")
    s.add_argument("--dir", help="the working directory on HOST (else the same path, under its home)")
    s.add_argument("--cut", metavar="REGEX", help="send each transcript up to its last line that matches: a turn's end")
    a = ap.parse_args()
    (cmd_probe if a.cmd == "probe" else cmd_send)(a)


if __name__ == "__main__":
    if sys.argv[1:2] == ["_probe"]:
        print(MARK + json.dumps(probe(json.loads(sys.argv[2]))), flush=True)
    elif sys.argv[1:2] == ["_land"]:
        land(sys.argv[2])
    else:
        main()
