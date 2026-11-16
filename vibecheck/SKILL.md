---
name: vibecheck
description: "Keeps a coding agent (Claude Code, Codex or another) from hanging: every command it runs has a deadline, nothing waits for input or forever, and a watchdog reports any process of the session that outlives its deadline, a server that stops answering, and a log that stops growing. Use whenever the agent runs commands, when the user says \"vibecheck\", and when a session hung."
---

> **Usage:** tell Claude Code or Codex, at the start of a session or after a hang:
> `Read netanel.dev/vibe and vibecheck this session`

A session hangs when it waits for something that will not come: a command that never ends, a prompt nobody answers, a reply that never arrives. While it waits, it reads nothing, not even its own watchdog. So every wait gets a bound, and a watchdog catches what slips through. Follow these rules for the rest of the session.

`vibecheck.py` is the watchdog. It is next to this file, and at https://raw.githubusercontent.com/netanel-haber/skills/main/vibecheck/vibecheck.py: download it if you read this from a URL. Read its docstring. Run it as `python3 <path>` (or `uv run --no-project --script <path>`).

## Rules

1. **Every command has a deadline.** In the foreground: `timeout -k 5 N <command>`, with N at most 60. The `-k 5` kills a command that ignores the timeout's TERM. Anything that may take longer runs in the background, with its own `timeout -k 5 N`, while you keep working. Never block on it, and never poll it with `sleep`.
2. **Nothing waits for input.**
   - stdin: `< /dev/null` for anything that may read it. Never `python3 -` or `cat >` without a heredoc.
   - Pagers and editors: `GIT_PAGER=cat PAGER=cat`, `git commit -m`, `GIT_EDITOR=true`, no `-i` flags.
   - Prompts: `ssh -o BatchMode=yes -o ConnectTimeout=10`, `apt-get -y`, `pip --no-input`, `npx --yes`, `CI=1`.
3. **Nothing waits on the network without a bound:** `curl -m 20`, `timeout=` in every HTTP client, `-o ConnectTimeout` for ssh. A script that waits for a reply (a socket, a browser over CDP, a queue) bounds each wait and its whole run inside the script, in the helper that every caller uses, so that no caller can forget.
4. **Servers and followers run in the background,** never in the foreground: dev servers, `tail -f`, `watch`, `--follow`. A server gets a deadline as long as the task (`timeout 4h`). To wait until it is up, use a bounded loop: `for i in $(seq 20); do curl -sfm 2 URL && break; sleep 1; done`.
5. **The watchdog runs while you work.** Run `vibecheck.py watch`, with:
   - `--url` for each server the task depends on;
   - `--quiet LOG=SECONDS` for a job's log that must keep growing;
   - `--allow REGEX` for what is meant to live long.

   Where the agent turns a background command's output into notifications (Claude Code's Monitor tool), run it there, and re-arm it when it expires. Elsewhere, run `vibecheck.py once` after each step that started something.
6. **When it reports, act at once.**
   - Stop what is stuck, with its whole tree: a child can ignore TERM, so end with KILL.
   - Find which wait had no bound, and fix it where the wait is made: in the script or the shared helper, not in this one call.
   - Then run it again. Never retry the same command as is, and never just wait longer.
7. **Silence is not progress.** A background job that prints nothing for a long time is checked (its log, its process), not trusted.
8. **Leave nothing behind.** Before you finish, stop every background process that you started and that the user did not ask to keep. Say which ones you kept, and why.

## Examples (November 2026: Claude Code 2.1, Codex 0.166)

- Claude Code: the Monitor tool, with `python3 <path>/vibecheck.py watch --url http://127.0.0.1:8000/` and the longest `timeout_ms`, re-armed at each expiry. Each line it prints arrives as a notification, also while a background command runs.
- Codex: `python3 <path>/vibecheck.py once` after each step. Exit 1 means it found something.
