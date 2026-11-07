---
name: teleport
description: "Move a coding-agent session (Claude Code, Codex or another; this one, or another one, even while it runs) to another machine over SSH, ready to continue in tmux there, with its transcript, scratchpad, memory and uncommitted code. Use when the user says \"teleport us to <host>\" or asks to continue a session on another machine."
argument-hint: "<host> [<dir>] [<session: id, path or phrase>]"
---

The user names the host, and maybe a directory or a session. Decide the rest, and ask only where a step says so. Do every step.

`teleport.py` does the mechanics and knows nothing about agents. It is next to this file; if you read this from a URL, it is at the same URL with `teleport.py` in place of `SKILL.md`: download it. Read its docstring first: it maps paths to the host, brings the code, finds the agent there and tries the resume line by itself. If a part does not fit, change the script or do that part by hand. Run it with `uv run` (or `python3`), outside any sandbox, in the session's working directory.

Agents change where they keep sessions and which flags they take, so find each fact by looking. The examples at the end are hints from November 2026.

1. **Find the session.** It is this one, unless the user points at another: an id, a file, a phrase from it, or "the last session in <dir>".
   - Find its files in the agent's config folder (such as `~/.claude` or `~/.codex`): `find <folder> -name '*<id>*'`, or `grep -rl '<phrase>' <folder>`. A phrase that you wrote in this turn finds this session. Take its transcript, everything else named after its id, its project's memory, and its scratchpad, where they exist. Do not send dependencies or artifacts: the resumed session rebuilds them, and the script leaves them out of folders.
   - Read its working directory, model, effort and permission mode in the latest records of its transcript.
   - If another session may still run, never message it. Wait only for its main agent to end its turn: `teleport.py wait <transcript> --end <regex> --busy <regex>`. Learn both from its transcript: the record that ends each earlier turn, and the records of the main agent's replies and tool calls. Do not wait for subagents, background tasks, workflows or schedules: they do not move, and the prompt names them.
2. **Probe the host,** in the session's working directory: `teleport.py probe HOST <agent's program> [DIR]`.
   - DIR is the directory that the user named. Without one, the probe looks at the same path under the host's home. If that does not exist and the probe found one clone of the repository, use that clone as DIR. If it found several, ask the user.
   - If the session already runs on the host, or `python3` or `tmux` is missing there, tell the user.
3. **Write the resume command** from the host's help (in the probe, and in the help of its resume subcommand): resume the id, with the same model, effort and permission mode, where the host has flags for them.
4. **Write the prompt.** Tell the session:
   - that it moved, from which host and directory to which;
   - that the teleport is done and must not run again (if it moved itself: the tool call that ran it shows as interrupted);
   - what did not move: processes, subagents, background tasks, workflows, schedules and servers that were running (jobs on a shared scheduler keep running: give their IDs).

   The script adds the rest: the code's state, what it did not send, and a last line that says to recover and continue.
5. **Send,** in the session's working directory: `teleport.py send HOST <its files and folders> --run "<resume command>" --prompt "<prompt>" [--dir DIR]`. Its `note` lines show where each one landed. If one did not land where the host's agent keeps such files, send it again as `LOCAL=REMOTE`.
6. **Check** its `check` lines: the resume line, tried on the host with a made-up id. An option error (unknown, unexpected or conflicting) means a wrong flag: fix `--run`, and send again. An error about the id or the terminal means that the line is good.
7. **Reply** with only its last two lines (the window with its attach command, and the resume line), and say which copy is now stale. If you moved this session, make no more tool calls, even if the task is not done. If you moved another one, tell the user to exit it.

## Examples (November 2026: Claude Code 2.1, Codex 0.166)

- Claude Code: `$CLAUDE_CODE_SESSION_ID`; `~/.claude/projects/<working directory, non-alphanumerics as ->/<id>.jsonl`, with `<id>/` and `memory/` beside it; the scratchpad `<tmp>/claude-<uid>/<same name>/<id>/scratchpad`; a turn ends with `"subtype":"turn_duration"`; `claude --resume <id> --model M --effort E --permission-mode P`.
- Codex: `$CODEX_THREAD_ID`; `~/.codex/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl`; a turn ends with `"task_complete"`; `codex resume <id> -C <dir> -m M -c model_reasoning_effort=E`.
