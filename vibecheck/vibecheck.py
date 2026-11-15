#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""vibecheck: is anything of this agent session stuck? Prints one line per finding; silent when all is well.

    vibecheck.py once  [options]   one check; exit 1 if it found anything
    vibecheck.py watch [options]   a check every --every seconds, forever; each finding once (run it in the background,
                                   or as the agent's monitor, where each line it prints becomes a notification)

What it finds:
  STUCK  a process of the session that outlived its deadline, plus --grace (the timeout itself failed: `timeout`
         without -k, a child that ignores TERM); or, with no deadline at all, one that ran past --limit. Its deadline is
         the N of the nearest `timeout N` process at or above it; a process with none above it (a tool call's shell) is
         waiting for the `timeout` processes below it, and has the longest of their deadlines. Only the topmost stuck
         process of a tree is reported: for a tool call that is the agent's shell, whose command line says what it ran.
  DOWN   a --url that did not answer in 5 seconds (and UP when it answers again).
  QUIET  a --quiet PATH=SECONDS file (a job's log) that has not grown for SECONDS (and LIVE when it grows again).

The session: every process under the agent's own process, the nearest ancestor of this script whose program is the
agent (--agent, a regex on the program's name: claude or codex), or under --root PID. Not the watcher itself and its
ancestors, and not what --allow names (servers and helpers that are meant to live: MCP servers, language servers).
"""

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.request

AGENT = r"claude|codex"
ALLOW = r"mcp|language[-_]server|lsp\b|vibecheck"
# A `timeout` process's command line: `timeout [options] N[smhd] command`. -k and -s take a value.
TIMEOUT = re.compile(
    r"^\S*timeout\s+(?:-[ks]\s+\S+\s+|-\S+\s+)*(\d+(?:\.\d+)?)([smhd]?)\s"
)
UNIT = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}

Procs = dict  # pid: (ppid, seconds running, args)


def processes() -> Procs:
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid=,etime=,args="],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    procs = {}
    for line in out.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3:
            pid, ppid, etime = parts[:3]
            procs[int(pid)] = (
                int(ppid),
                seconds(etime),
                parts[3] if len(parts) > 3 else "",
            )
    return procs


def seconds(etime: str) -> int:
    """ps's etime, [[dd-]hh:]mm:ss, in seconds."""
    days, _, clock = etime.rpartition("-")
    total = 0
    for part in clock.split(":"):
        total = total * 60 + int(part)
    return total + int(days or 0) * 86400


def ancestors(pid: int, procs: Procs) -> list:
    """The pids above pid, nearest first."""
    out, seen = [], {pid}
    while pid in procs and procs[pid][0] not in seen and procs[pid][0] in procs:
        pid = procs[pid][0]
        seen.add(pid)
        out.append(pid)
    return out


def program(args: str) -> str:
    return os.path.basename(args.split(None, 1)[0]) if args else ""


def limit_of(pid: int, procs: Procs):
    """The seconds of pid's command line if it is a `timeout` process, else None."""
    m = (
        TIMEOUT.match(procs[pid][2] + " ")
        if program(procs[pid][2]) == "timeout"
        else None
    )
    return float(m[1]) * UNIT[m[2]] if m else None


def deadline(pid: int, procs: Procs):
    """pid's deadline in seconds: the nearest `timeout` process at or above it, else the longest of the `timeout`
    processes below it (it waits for them), else None."""
    for p in [pid, *ancestors(pid, procs)]:
        if (limit := limit_of(p, procs)) is not None:
            return limit
    below = [limit_of(p, procs) for p in procs if pid in ancestors(p, procs)]
    return max((x for x in below if x is not None), default=None)


def shown(args: str, width: int = 160) -> str:
    """A command line in one short line: its start and its end (a tool's shell puts the command last)."""
    args = " ".join(args.split())
    return args if len(args) <= width else args[:50] + " ... " + args[-(width - 55) :]


def stuck(root: int, procs: Procs, me: int, opts) -> list:
    """(pid, line) of each topmost stuck process under root."""
    skip = {me, *ancestors(me, procs)}
    allow = re.compile(opts.allow)
    over = {}
    for pid, (_, secs, args) in procs.items():
        if pid in skip or root not in ancestors(pid, procs) or allow.search(args):
            continue
        limit = deadline(pid, procs)
        if secs > (limit + opts.grace if limit is not None else opts.limit):
            why = (
                f"past its timeout of {limit:g}s"
                if limit is not None
                else f"with no deadline, past {opts.limit}s"
            )
            over[pid] = f"STUCK pid {pid}, {secs}s {why}: {shown(args)}"
    return [(pid, line) for pid, line in over.items() if procs[pid][0] not in over]


def answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5):
            return True
    except Exception:  # noqa: BLE001
        return False


def check(opts, state: dict) -> list:
    """The lines to print now: new findings, and things that recovered. state: what was reported, across checks."""
    procs, me = processes(), os.getpid()
    root = opts.root or next(
        (
            p
            for p in ancestors(me, procs)
            if re.fullmatch(opts.agent, program(procs[p][2]))
        ),
        None,
    )
    if root is None:
        return [
            f"vibecheck: no ancestor of pid {me} runs {opts.agent}: pass --root PID"
        ]
    lines = []
    for pid, line in stuck(root, procs, me, opts):
        if pid not in state.setdefault("stuck", set()):
            state["stuck"].add(pid)
            lines.append(line + "  -> kill it, or find what it waits on")
    for url in opts.url:
        up = answers(url)
        if up == state.get(url, True):
            continue
        state[url] = up
        lines.append(
            f"UP {url} answers again" if up else f"DOWN {url} did not answer in 5s"
        )
    for spec in opts.quiet:
        path, _, secs = spec.rpartition("=")
        try:
            idle = time.time() - os.stat(path).st_mtime
        except OSError:
            idle = float("inf")
        quiet = idle > float(secs)
        if quiet == state.get(path, False):
            continue
        state[path] = quiet
        lines.append(
            f"QUIET {path} has not grown for {secs}s"
            if quiet
            else f"LIVE {path} grows again"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("mode", choices=["once", "watch"])
    parser.add_argument(
        "--every",
        type=float,
        default=60,
        help="seconds between checks in watch mode (60)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=120,
        help="seconds a process with no deadline may run (120)",
    )
    parser.add_argument(
        "--grace",
        type=int,
        default=30,
        help="seconds past its timeout before a process is stuck (30)",
    )
    parser.add_argument(
        "--agent", default=AGENT, help=f"regex of the agent's program name ({AGENT})"
    )
    parser.add_argument(
        "--root",
        type=int,
        help="the session's root pid, instead of the agent's process",
    )
    parser.add_argument(
        "--allow",
        default=ALLOW,
        help=f"regex of command lines that may live long ({ALLOW})",
    )
    parser.add_argument(
        "--url", action="append", default=[], help="a URL that must answer (repeatable)"
    )
    parser.add_argument(
        "--quiet",
        action="append",
        default=[],
        help="PATH=SECONDS: a file that must keep growing",
    )
    opts = parser.parse_args()
    state: dict = {}
    while True:
        lines = check(opts, state)
        for line in lines:
            print(line, flush=True)
        if opts.mode == "once":
            return 1 if lines else 0
        time.sleep(opts.every)


if __name__ == "__main__":
    sys.exit(main())
