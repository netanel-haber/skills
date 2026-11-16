---
name: ez-review
description: Make an E-Z-Review page for one or more GitHub PRs. The page is one HTML file. It shows a note next to each diff hunk, draft review comments, viewed marks and a reading order. Use this skill when the user asks to review, explain or walk through a PR or a stack of PRs.
---

# E-Z-Review

E-Z-Review makes one HTML page for one or more GitHub pull requests (PRs). The page shows each diff hunk with a note next to it. You do not need a server or a build step.

The tool is `ez_review.py`. It is in the same folder as this file, for example `~/.claude/skills/ez-review/ez_review.py`. Below, `EZ` is that path. Run the tool with `python3 -I EZ`.

The tool needs an authenticated `gh`. For stacked PRs, it also needs a local clone of the repository.

For a diff that is not a GitHub PR (a merge request on a different host, a local branch), `init` does not apply. Make the diff with `git diff BASE HEAD`, run `split`, and write `ez-review.json` by hand. The format is at the top of `ez_review.py`. Leave `url` empty, because the links to lines are GitHub links.

## Procedure

1. **Get the PRs.**
   - Run `python3 -I EZ init --repo OWNER/NAME --prs N [N ...] --clone PATH --dir DIR --mode review` (or `--mode explain`).
   - For a stack, give the PRs from the bottom of the stack to the top. Each PR then shows only its own commits.
   - The tool writes `DIR/ez-review.json`, `diffs/`, `chunks-N/`, `order-N.txt` and empty `notes-N/` folders.

2. **Set the reading order.**
   - Edit `order-N.txt`. Put the files in this order: design documents, public API, implementation (high level first), tests, generated files.
   - Add section lines, for example `# 1. Public API`.
   - The reader must be able to understand each file without the full system.
   - If the overview names the hunks to read first, put them first: an indented `hunks:` line after a path sets the order of the hunks in that file.

3. **Write the notes.**
   - Run `python3 -I EZ brief --mode review` (or `--mode explain`). The output is the section "Brief for note writers" of this file, with the mode filled in.
   - Add the background that the writers need: what the system does, earlier review themes, the preferences of the user, the words that the user uses, and what the user already decided.
   - A writer that does not have this background explains the code to itself, not to the reader. If you can, use writers that have the conversation.
   - Save the result as `DIR/BRIEF.md`.
   - Write `notes-N/agent/notes.json`. Every hunk must have a note.
   - If there are more than approximately 40 hunks, use parallel subagents. Give each subagent one PR or one group of files.
   - Give each subagent the brief, the full paths of its chunk files, the source tree and its output path. Subagents often cannot list folders.
   - Give each subagent its own output file. A later file replaces the same fields of an earlier file, so a subagent that rewrites some notes writes only those entries.
   - Tell the subagents to use only read tools.

4. **Write the overviews.** Copy the `"overview"` text of each notes file into `overview-N.md`. For a stack, put a short primer at the top of the first overview.

5. **Edit the text.** Do this for every note, summary, draft comment and overview, before you make the page.
   - Run the `coding-comms` skill on each text.
   - Run the `sem-compress` skill on the notes as a set: remove what a note repeats from the diff, from the overview or from a different note.
   - Read each note as the reader. If the reader cannot tell in 15 seconds what the hunk does and if it needs attention, write the note again.

6. **Check and make the page.**
   - Run `python3 -I EZ check DIR/ez-review.json`. Fix all missing notes.
   - Run `python3 -I EZ render-multi DIR/ez-review.json DIR/review.html`.
   - Make a headless browser screenshot of the top of the page and of one hunk page (`pages-N/<n>.html`). Look at both.

7. **Change the text when the user asks.**
   - When the user pastes a note or a draft and asks for a new version, write the new text in a later notes file, for example `notes-N/zz_manual/notes.json`. A later file replaces the same fields of an earlier file.
   - Make the page again, and show the new text to the user.

8. **Update for new commits.**
   - Make the diff again. Run `carry` to move the notes to the new diff, and set `"since"` in the config to the last reviewed commit.
   - Keep the `prev` and `change` fields that `carry` writes. The page uses them to keep the viewed marks of hunks that only moved, and to show the changed hunks as not viewed.
   - Write new notes for the hunks that `carry` shows as "changed" or "new". The note of a changed hunk starts with one sentence, "**Changed since <commit>:**", that tells what changed and why. The rest of the note describes the code as it is now.
   - Read the notes of the "moved" and "unchanged" hunks too: a change in a different hunk can make them false. Correct them without a "Changed since" sentence.
   - Hunk numbers change. Update the `hunks:` lines of the order file and the hunk numbers in the overview.

9. **Record posted comments.**
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
  - Draft comments ("ask") are in the voice of the reader. The reader can post them without changes, or give them to the agent that wrote the code.
- **explain:** The reader is the author of the PR, or the reader does not know the code.
  - Each note follows the lines closely. Give line ranges, the real names, shapes and constants, and the data flow.
  - In each note, use one or two sentences to tell which step of the full system these lines do.
  - Write an ask only for a probable bug or a real gap. Write it as a short task for the author.

### Input

- You get one chunk file for each changed file. Your task message gives the paths.
- In a chunk file, each hunk starts with a line `===== HUNK <id>`. The line numbers are the numbers in the new file.
- If a hunk is only a part of a file, read the full source file.

### Notes

The reader of a note sees one hunk and did not see your work. The note must let the reader understand the hunk and decide about it. Do not write for yourself or for the author.

Write each note with the `coding-comms` skill: simple words, exact technical terms, short sentences, active voice. Then run the `sem-compress` skill on your notes as a set: remove what a note repeats from the diff, from the overview or from a different note.

Shape of a hunk note:
1. What the hunk changes, in one or two sentences. Name the thing first. If the change is clear only next to the old behavior, tell the old behavior ("Before, ...").
2. Why, in one sentence, only if the reader cannot see the reason in the diff.
3. Then only the labels that apply, each as one short paragraph:
   - **Decide:** the reader must choose. Tell what occurs now, the options and your recommendation.
   - **Check:** a risk that the reader must examine. Tell the risk and how certain you are.
   - **Know:** a fact that changes how the reader judges the hunk: a limit, an earlier decision of the reader, a behavior that is not obvious.
   - **Tested:** or **Not tested:** only if the code is not trivial and the result is not obvious.

Rules:
- Use one to three sentences for most hunks. Use eight sentences or fewer for a main hunk: a new file, a new function, a changed algorithm.
- Do not use fixed headings, "none" entries, or a list of what you did not examine. If a point that you did not examine is important, write it under Check as one sentence.
- In review mode, do not go through the lines one by one, and do not repeat the code: types, shapes, formulas, argument lists. Give a line number only if the reader must find one line.
- If the diff does not show a name, tell what it is in a few words.
- Describe the code as it is now. Do not tell the history of your work or of this page. One exception: if the task gives a commit that the reader already reviewed, the note of a hunk that changed since then starts with one sentence, "**Changed since <commit>:**", that tells what changed and why.
- Use only the markup that the page renders. The list is at the top of `ez_review.py`. The page does not render tables: use a list.
- Give the name of the thing. Do not use "it" or "this" if the reader cannot see what it is.
- Do not give compliments.
- **File note:** two or three sentences: what the file is, what the PR changes in it, and which hunk to read first.
- **Tests:** tell what each test proves, and how many cases ran before and run now. Put a coverage gap under Check, with its risk.
- **GPU kernels:** tell where the data is (global memory, shared memory, registers, tensor memory). Tell which grid, warps and threads do the work. Tell what they calculate, and where they write the result.
- **References:** "#N" is hunk N of the same file. "other.py hunk #N" is hunk N of a different file.

Before you write the output, read each note as the reader. If the reader cannot tell in 15 seconds what the hunk does and if it needs attention, write the note again.

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
           "summary": "one line, 14 words or fewer, as the reader would say it", "note": "...",
           "ask": {"priority": "should|question|nit", "title": "...", "text": "...", "line": 123}}},
 "overview": "150 to 350 words of Markdown, with no tables: what the PR does; numbered steps of one call from start to end; 'Read in this order' with the 3 to 6 most important hunks; what was tested and what was not; the open asks"}
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
