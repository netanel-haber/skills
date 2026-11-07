---
name: teleport
description: "Move a coding-agent session (Claude Code, Codex or another; this one, or a stopped one that the user points at) to another machine over SSH, ready to continue there in tmux, with its transcript, scratchpad, memory and uncommitted code. Use when the user says \"teleport to <host> [<dir>]\" or asks to continue a session on another machine."
argument-hint: "<host> [<dir>] [<session to move: id, path or phrase>]"
---

Follow the user's instructions first, then this skill. Do every step. The user names only the host, and maybe a directory or a session: decide the rest, and ask only where a step says so.

`teleport.py`, next to this file (if you read this from a URL: the same URL, ending in `teleport.py`; download it), does the mechanical part and knows nothing about agents: `probe` reports facts about a machine, and `send` copies the files that you name, opens a tmux window on the host and prints the line that resumes the session there. Read it first. It is a starting point: if a part does not fit, change it or do that part by hand. Run it with `uv run` (or `python3`) outside any sandbox: it needs the network.

Agents change where they keep sessions and which flags they take: find each fact by looking. The examples at the end are hints from November 2026.

1. **Find the session's files.** Move this session, unless the user points at another: an id, a file, a phrase from it, or "the last session in <dir>".
   - Search the agent's config folder (such as `~/.claude`, `~/.codex`, or one its environment names): `find <folder> -name '*<id>*'`, or `grep -rl '<phrase>' <folder>`. For this session, a phrase that you wrote in this turn finds it. Read the id from its name or records.
   - Take the transcript, everything else named after the id (such as subagents), and what the agent keeps for the project next to them (such as memory). A scratchpad that your instructions name belongs to this session. For another session, find its own by the same pattern.
   - Read the session's working directory, model, effort and permission mode in the latest records of its transcript.
   - Another session must be stopped: `teleport.py probe --here --dir <its working directory> --session <id>` shows no process for it, and its transcript is quiet for a minute. If it still runs, tell the user to type the teleport request into it instead: it moves itself between tool calls.
2. **Probe the host:** `teleport.py probe HOST --bin <agent> --dir DIR --session <id> --find-clone <origin URL> --ls <the host's config folder>`.
   - DIR is the directory that the user named. Else, it is the session's working directory with your home replaced by the host's home, if it exists there. Else, it is the one clone found. If it found none, keep the first choice: `send --code` makes it a clone at the session's commit. Ask only if it found several.
   - If the session already runs on the host, ask the user before you continue. If `python3` or `tmux` is missing, tell the user.
3. **Map each file** to where the host's agent would have written it, had the session run in DIR. Learn the naming here: compare each path with the session's working directory, id, date, uid and config folder. Name the host's paths the same way, with the host's real DIR, home, uid and temp folder. Compare them with the host's `--ls` entries; if they differ, follow the host.
4. **Write the resume command** from the host's help (`<agent> --help`, and its resume subcommand's): resume the id, with the same model, effort and permission mode, if the host has flags for them. If the agent's `in_window` is false, pass its folder with `--path`.
5. **Write the prompt.** Tell the session:
   - that it moved from this host and directory to the new ones;
   - that the teleport is done and must not run again (for this session: the tool call that ran it shows as interrupted);
   - each path that changed, old → new;
   - what did not move: processes, background tasks and servers; jobs on a shared scheduler keep running (give their IDs);
   - to continue the work.
6. **Send:**
   ```
   teleport.py send HOST --dir DIR --session <id> --tmux-session <agent> [--path <bin folder>] \
     --put <file or folder>=<host path> ... [--merge <memory folder>=<host path>] \
     [--code <working directory>] [--compress zstd] --run "<resume command>" --prompt "<prompt>"
   ```
   Pass only what exists; `--compress zstd` only if both machines have `zstd`. `--code` applies the changes only to a clean work tree at the same commit; otherwise it leaves them in the stash, and the prompt says where. If it cannot clone into a missing DIR, send again with `--ship-repo`. The last two lines are the window with its attach command, and the resume line.
7. **Check** its `check` lines, the resume line tried on the host with a made-up id. An option error (unknown, unexpected, conflicting) means a wrong flag: fix `--run` and send again. An error about the id or the terminal means the line is good.
8. **Reply** with only those two lines, and say which copy is now stale. If you moved this session, make no more tool calls, even if the task is not done.
9. **If it fails,** read the error, fix the parameter or the script, and send again. Each run keeps what it replaced on the host in its stash, `~/.cache/teleport/<run>`.

## Examples (November 2026: Claude Code 2.1, Codex 0.166)

- Claude Code: `$CLAUDE_CODE_SESSION_ID`; `~/.claude/projects/<directory, non-alphanumerics as ->/<id>.jsonl`, with `<id>/` and `memory/` beside it; the scratchpad `<tmp>/claude-<uid>/<same name>/<id>/scratchpad`; `claude --resume <id> --model M --effort E --permission-mode P`.
- Codex: `$CODEX_THREAD_ID`; `~/.codex/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl`, at the same path on the host; `codex resume <id> -C DIR -m M -c model_reasoning_effort=E`.

## What does not move

- Files outside the git work tree and the scratchpad, and ignored files.
- This skill: install it on the host to teleport from there.
