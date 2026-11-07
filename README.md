| Skill |  |
|---|---|
| [sem-compress](sem-compress) | Makes code smaller. It removes repetition, dead code and needless layers, and it keeps every feature. |
| [coding-comms](coding-comms) | Writes and reviews text about code: PR and commit messages, reviews, issues, comments, docstrings and design docs. |
| [visual-comms](visual-comms) | Designs, builds and reviews visual output about code: pages, dashboards, tables, charts, diagrams and images in PRs. |
| [visual-loop](visual-loop) | Looks at every visible change in background screenshots and fixes what it finds, and iterates with the user in rounds, in one view that reloads by itself. |
| [fractal-incrementality](fractal-incrementality) | Splits every decision, large or small, into the smallest step that gives a real answer, for fast validation. |
| [teleport](teleport) | Moves a Claude Code or Codex session to another machine over SSH, with its context, scratchpad, memory and code changes, and prints the one line that resumes it there in tmux. |

To move a session, tell Claude Code or Codex, from any machine: `Read https://raw.githubusercontent.com/netanel-haber/skills/main/teleport/SKILL.md and teleport us to <host>`.

Each SKILL.md is at most 1,000 words (`wc -w */SKILL.md`).
