---
name: ez-review
description: Make an E-Z-Review page for one or more GitHub PRs. The page is one HTML file. It shows a note next to each diff hunk, draft review comments, viewed marks and a reading order. Use this skill when the user asks to review, explain or walk through a PR or a stack of PRs.
---

# E-Z-Review

E-Z-Review makes one HTML page for one or more GitHub pull requests (PRs). The page shows each diff hunk with a note next to it. You do not need a server or a build step.

The tool is `ez_review.py`. It is in the same folder as this file, for example `~/.claude/skills/ez-review/ez_review.py`. Below, `EZ` is that path. Run the tool with `python3 -I EZ`.

The tool needs an authenticated `gh`. For stacked PRs, it also needs a local clone of the repository.

## Procedure

1. **Get the PRs.**
   - Run `python3 -I EZ init --repo OWNER/NAME --prs N [N ...] --clone PATH --dir DIR --mode review` (or `--mode explain`).
   - For a stack, give the PRs from the bottom of the stack to the top. Each PR then shows only its own commits.
   - The tool writes `DIR/ez-review.json`, `diffs/`, `chunks-N/`, `order-N.txt` and empty `notes-N/` folders.

2. **Set the reading order.**
   - Edit `order-N.txt`. Put the files in this order: design documents, public API, implementation (high level first), tests, generated files.
   - Add section lines, for example `# 1. Public API`.
   - The reader must be able to understand each file without the full system.

3. **Write the notes.**
   - Run `python3 -I EZ brief --mode review` (or `--mode explain`). The output is the section "Brief for note writers" of this file, with the mode filled in.
   - Add the background that the writers need: what the system does, earlier review themes, and the preferences of the user.
   - Save the result as `DIR/BRIEF.md`.
   - Write `notes-N/agent/notes.json`. Every hunk must have a note.
   - If there are more than approximately 40 hunks, use parallel subagents. Give each subagent one PR or one group of files.
   - Give each subagent the brief, the full paths of its chunk files, the source tree and its output path. Subagents often cannot list folders.
   - Tell the subagents to use only read tools.

4. **Write the overviews.** Copy the `"overview"` text of each notes file into `overview-N.md`. For a stack, put a short primer at the top of the first overview.

5. **Check and make the page.**
   - Run `python3 -I EZ check DIR/ez-review.json`. Fix all missing notes.
   - Run `python3 -I EZ render-multi DIR/ez-review.json DIR/review.html`.
   - Make a headless browser screenshot of the top of the page and of one hunk page (`pages-N/<n>.html`). Look at both.

6. **Change the text when the user asks.**
   - When the user pastes a note or a draft and asks for a new version, write the new text in a later notes file, for example `notes-N/zz_manual/notes.json`. A later file replaces the same fields of an earlier file.
   - Make the page again, and show the new text to the user.

7. **Update for new commits.** Make the diff again. Run `carry` to move the notes to the new diff. Write new notes only for the hunks that `carry` shows as "changed" or "new".

8. **Record posted comments.**
   - When the user posts a draft, set `"posted_url"` on its `ask`. The draft then goes out of the To do list.
   - `posted` gets the threads of the user into a JSON file. Set the file as `"posted"` in the config.
   - In a notes file, the `"threads"` map can mark each thread as `addressed`, `answered` or `open`.

## Draft comments that the user posts

- Write in the voice of the user. Keep each draft short.
- Name the code first. Put line numbers in parentheses.
- Do not use humble openers. Do not give compliments.
- Ask one question at the end.
- Make sure that each claim is true in the source code. Tell the user what you did not make sure of.
- Before you keep a draft, make sure that its premise is real. If you can run a short check, run it. If the check shows that the problem does not occur, remove the draft (`"ask": null`) and tell the user the result.

## Reports to the user

When you report the state of a review, or the result of a check, use these sections:

- **Current issues:** each open problem, with the file, the line, and how certain you are.
- **Remedies:** for each issue, what to do (post a draft, change a draft, remove a draft, wait for the author).
- **Issues not worth pursuing:** each problem that needs no action, with the reason after "Why not:".
- **Changes made:** what you changed in the notes, the overview or the page.
- **Evidence:** the checks that you ran, with the result, and the paths of the scripts.

## Brief for note writers

The note writers follow the rest of this section. If you write the notes yourself, follow it too. The `brief` command prints it and puts the subject and the mode in place of `__WHAT__` and `__MODE__`.

<!-- brief -->
You write notes for a review page about __WHAT__. A person reads each note next to a diff hunk.

### Mode: __MODE__

- **review:** The reader reviews the PR of a different person.
  - Each note tells what the hunk does, if it is correct, and what to examine.
  - Draft comments ("ask") are in the voice of the reader. The reader can post them without changes.
- **explain:** The reader is the author of the PR, or the reader does not know the code.
  - Each note follows the lines closely. Give line ranges, the real names, shapes and constants, and the data flow.
  - In each note, use one or two sentences to tell which step of the full system these lines do.
  - Write an ask only for a probable bug or a real gap. Write it as a short task for the author.

### Input

- You get one chunk file for each changed file. Your task message gives the paths.
- In a chunk file, each hunk starts with a line `===== HUNK <id>`. The line numbers are the numbers in the new file.
- If a hunk is only a part of a file, read the full source file.

### Notes

Write in Simplified Technical English:
- Use short sentences: 20 words or fewer for instructions, and 25 words or fewer for descriptions.
- Use the active voice. Use one topic in each paragraph. Use lists for steps.
- Give the name of the thing. Do not use "it" or "this" if the reader cannot see what it is.
- Use one hedge or fewer in a note. Use a hedge only for a conclusion that is not certain.
- Do not give compliments.

Structure:
- **Every note starts with action items:**
  - **Current issues:** each problem that needs an action, with the line and the risk. Write "none" if there is no such problem.
  - **Remedies:** for each current issue, what the reader does (post the draft, reply, ask for a change). Write "none" if there is no current issue.
  - **Issues not worth pursuing:** each problem that you found but that needs no action. Give the reason after "Why not:" (for example: low risk, intended, covered by other tests or evals). Leave this section out if it is empty.
  - The explanation of the code comes after these sections.
- **Large hunk** (a new file or a large block): use these headings:
  - **Role.**
  - **Data flow.** (numbered steps, with line ranges)
  - **Key details.**
- **Small hunk:** write 1 to 4 sentences.
- **Tests:** put each coverage gap under Current issues or under Issues not worth pursuing, with its risk. Then tell what each test proves.
- **GPU kernels:** tell where the data is (global memory, shared memory, registers, tensor memory). Tell which grid, warps and threads do the work. Tell what they calculate, and where they write the result.
- **References:** "#N" is hunk N of the same file. "other.py hunk #N" is hunk N of a different file.

### Draft comments ("ask")

Most hunks do not have an ask. Write an ask only for a probable bug, a real question or a useful nit.

- Use 1 to 4 sentences. Or use one claim, a short list of evidence, and one question.
- State facts that you examined as facts. Use one hedge or fewer, and only on the conclusion.
- Do not use humble openers, for example "Am I missing..." or "If I read it right". Do not give compliments.
- Name the code first. Put line numbers in parentheses, for example "`store_state` (L812)".
- Tell what the code does now. Tell what to do instead. End with one question or one suggestion.
- Do not ask for an assert or a check for a condition that is always true. Ask for a comment that tells why the code is correct.
- You can ask for a check on public API input when bad input gives wrong results and no error.
- An `assert` always runs. Do not write about `python -O`.
- Do not ask for a test of a failure that you did not show can occur. If you can run the code, run it first. If a test would only check a library (for example, that a compiled op equals the eager op), do not ask for it.

### Output

Write one JSON file. Your task message gives the path.

```json
{"files": {"<path>": {"summary": "one line", "note": "what the change in the file does, and what to read first"}},
 "hunks": {"<path>#<i>": {"severity": "important|question|nit|pre-existing|info", "trivial": false,
           "summary": "one line, 14 words or fewer", "note": "...",
           "ask": {"priority": "should|question|nit", "title": "...", "text": "...", "line": 123}}},
 "overview": "150 to 350 words of Markdown: what the PR does; numbered steps of one call from start to end; 'Read in this order' with the 3 to 6 most important hunks; the open asks"}
```

- Each hunk id in your chunk files must have an entry. Copy the ids exactly.
- If a hunk has no ask, do not write the `ask` field.
- `trivial: true` is only for changes that do not need a review: renames, format changes, generated files, re-exports.
- `severity`:
  - `important`: a probable bug.
  - `question`: a decision is necessary.
  - `nit`: a small problem.
  - `pre-existing`: the problem was there before this PR.
  - `info`: an explanation only. Most hunks are `info`.
- Write only your output file.
- Read the file again when you finish. Make sure that the JSON is valid.
<!-- /brief -->

## What the page does

- Each file and each hunk has a "viewed" checkbox. When a hunk changes, it becomes "not viewed" again.
- You can show the diff side by side or inline. You can hide whitespace changes.
- Each PR has an Overview tab and a To do list of draft comments.
- The ↗ link copies a draft comment and opens its line on GitHub.
- A file list puts the files in a reading order, in sections.
- For a stack of PRs, each PR shows only its own commits.
- Each hunk also has its own page. Use j and k to go to the next or previous hunk.
- You can copy the review state from one browser and paste it into another.

## The files

- `SKILL.md`: this file. It is the Claude Code skill and the brief for the note writers.
- `ez_review.py`: the tool. It makes the page. The HTML, CSS and JavaScript are in this file.

## Use the tool without Claude Code

You need Python 3.9 or newer, an authenticated `gh`, and `git` for stacked PRs. Keep the two files in the same folder.

1. Get the PRs:
   `python3 -I ez_review.py init --repo owner/repo --prs 101 102 --clone ~/src/repo --dir review`
2. Put the file paths in `review/order-*.txt` in a reading order.
3. Write the notes in `review/notes-*/<any name>.json`. The format is at the top of `ez_review.py`. `python3 -I ez_review.py brief` shows the full instructions.
4. Check the notes: `python3 -I ez_review.py check review/ez-review.json`
5. Make the page: `python3 -I ez_review.py render-multi review/ez-review.json review/review.html`
