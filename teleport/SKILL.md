---
name: teleport
description: "Move a coding-agent session (Claude Code, Codex or another; this one, or another one, even while it runs) to another machine over SSH, ready to continue in tmux there, with its transcript, history, memory and notes. Use when the user says \"teleport us to <host>\" or asks to continue a session on another machine."
argument-hint: "<host> [<dir>] [<session: id, path or phrase>]"
---

The user names the host, and maybe a directory or a session. Decide the rest, and ask only where a step says so. Do every step.

Move only what the session needs to resume: its transcript, history, memory and notes. Do nothing with the project: no building, cloning, installing or copying it. The resumed session sets up what it needs.

`teleport.py` does the mechanics and knows nothing about agents. It is next to this file; if you read this from a URL, it is at the same URL with `teleport.py` in place of `SKILL.md`: download it. Read its docstring first. If a part does not fit, change the script or do that part by hand. Run it as `uv run --no-project --script <path>` (or `python3 <path>`), outside any sandbox, in the session's working directory.

Agents change where they keep sessions and which flags they take, so find each fact by looking. The examples at the end are hints from November 2026. Find only the facts that the steps ask for, with few commands.

1. **Find the session.** It is this one, unless the user points at another: an id, a file, a phrase from it, or "the last session in <dir>".
   - Its files: search the agent's config folder (such as `~/.claude` or `~/.codex`) with `find <folder> -name '*<id>*'`, or `grep -rl '<phrase>' <folder>`. A phrase that you wrote in this turn finds this session. Take its transcript, everything else named after its id, its project's memory, and its scratchpad, where they exist.
   - Its working directory, model, effort and permission mode: the latest records of its transcript.
   - What it had running (jobs, subagents, background tasks, workflows, schedules): what its transcript shows. Do not investigate further.
   - When you move another session, never message it and never wait for it, and always pass `send` the record that ends a turn, as `--cut <regex>` (learn it from the earlier turns in its transcript). It then moves as of its last finished turn, whether or not it still runs. When this session moves itself, do not cut.
2. **Probe the host,** in the session's working directory: `teleport.py probe HOST <agent's program> [DIR]`. DIR is the directory that the user named, or else the same path under the host's home; `send` creates it if it is missing. If the session already runs on the host, or `python3` or `tmux` is missing there, tell the user.
3. **Write the resume command** from the host's help (in the probe, and in the help of its resume subcommand): resume the id, with the same model, effort and permission mode, where the host has flags for them.
4. **Write the prompt.** Tell the session:
   - that it moved, from which host and directory to which;
   - that the teleport is done and must not run again (if it moved itself: the tool call that ran it shows as interrupted);
   - what it had running, which did not move (jobs on a shared scheduler keep running: give their IDs).

   The script adds the rest: where the old working directory is, whether a running turn was cut, what it did not send, and a last line that says to recover: set up the project and what was not sent, stop or pick up the jobs left running (not duplicate or ignore them), and continue.
5. **Send,** in the session's working directory: `teleport.py send HOST <its files and folders> --run "<resume command>" --prompt "<prompt>" [--dir DIR] [--cut <regex>]`. Its `note` lines show where each one landed. If one did not land where the host's agent keeps such files, send it again as `LOCAL=REMOTE`.
6. **Check** its `check` lines: the resume line, tried on the host with a made-up id. An option error (unknown, unexpected or conflicting) means a wrong flag: fix `--run`, and send again. An error about the id or the terminal means that the line is good.
7. **Reply** with its last line (the command that attaches to the window, where the resume line is typed in: the user presses Enter), any `note` that the user must act on (such as an older version on the host), and which copy is now stale. If you moved this session, make no more tool calls, even if the task is not done. If you moved another one, tell the user to exit it.

## Examples (November 2026: Claude Code 2.1, Codex 0.166)

- Claude Code: `$CLAUDE_CODE_SESSION_ID`; `~/.claude/projects/<working directory, non-alphanumerics as ->/<id>.jsonl`, with `<id>/` and `memory/` beside it; the scratchpad `<tmp>/claude-<uid>/<same name>/<id>/scratchpad`; a turn ends with `"subtype":"turn_duration"`; `claude --resume <id> --model M --effort E --permission-mode P`.
- Codex: `$CODEX_THREAD_ID`; `~/.codex/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl`; a turn ends with `"task_complete"`; `codex resume <id> -C <dir> -m M -c model_reasoning_effort=E`.
