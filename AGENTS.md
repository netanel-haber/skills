# Skills

| Skill |  |
|---|---|
| [sem-compress](sem-compress) | Makes code smaller. It removes repetition, dead code and needless layers, and it keeps every feature. |
| [coding-comms](coding-comms) | Writes and reviews text about code: PR and commit messages, reviews, issues, comments, docstrings, design docs and answers to questions. |
| [visual-comms](visual-comms) | Designs, builds and reviews visual output about code: pages, dashboards, tables, charts, diagrams and images in PRs. Also looks at every visible change in background screenshots, fixes what it finds, and iterates with the user in rounds in one view that reloads by itself. |
| [fractal-incrementality](fractal-incrementality) | Splits every decision, large or small, into the smallest step that gives a real answer, for fast validation. |
| [teleport](teleport) | Moves a Claude Code or Codex session, even a running one, to another machine over SSH, with its transcript, history, memory and notes, and types the line that resumes it into a tmux window there. It can also pack the session as a tar for the agent on the other machine to unpack. To use it, tell Claude Code or Codex, from any machine: `Read netanel.dev/teleport and teleport us to <host>`. |
| [ez-review](ez-review) | Makes one HTML page for a PR or a stack of PRs, with a note for the reviewer next to each diff hunk, draft review comments, viewed marks and a reading order. |
| [vibecheck](vibecheck) | Keeps an agent from hanging: every command has a deadline, nothing waits for input or forever, and a watchdog reports what outlives its deadline, a server that stops answering and a log that stops growing. To use it, tell Claude Code or Codex: `Read netanel.dev/vibe and vibecheck this session`. |

# Changing a skill

Keep every skill generic: do not overfit it to the case that prompted a change. A rule or an example belongs in a skill only if it also holds in other projects, tools and fields.
