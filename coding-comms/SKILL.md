---
name: coding-comms
description: "Write and review text about code: PR and commit messages, reviews, issues, comments, docstrings, release notes and design docs."
---

Follow the user's instructions first, then the project's rules and recent style (such as title prefixes), then this skill. Do every step.

1. **Read the whole change**, then **list the facts** the reader needs and cannot see in it: what it does, why (only if not obvious to the field), costs, limits, what was and was not tested, and measured numbers with their setup. Put each change on its own line. Mark it
**major** if a user would notice it or search for it: a new API, platform, format or type, changed behavior or results, a removed feature, or a measured speedup.
2. **Draft** from the template below. Write very simply: common words, exact technical terms, short sentences with one idea each, active voice.
3. **Cut** each sentence that:
   - repeats the code, the diff or the docstrings: types, layouts, encodings, formulas, the contract;
   - explains internals, or why the code is this way (tell the user if the code lacks that reason);
   - explains what the field knows, such as why a cache speeds up reads or a smaller format saves memory;
   - tells the story of your work, or uses sales words such as "robust".
4. **Check.**
   - For each claim, find the code that makes it true, and add its conditions.
   - Write the title last. Name every major change with its scope: "Windows builds for the CLI", not "Windows support". Shorten the words, never the list; above about 90 characters, tell the user to consider a split. Keep it natural: "Add retry
support to the upload client", not "Add retry counts and timeouts to the upload client".
   - Start the body with what the change does, not with "This PR".
   - Define any name you made up. The reader did not see your work.
   - In anything public, commits included, remove secrets, personal data, internal paths, hosts, ticket IDs and unreleased products. If unsure, treat it as public.
5. **Show** the full draft before you publish, unless you were told to publish. If no one can answer, return the draft.

## Templates

```
Title: <imperative verb> <every major change, with its scope>
<What it does and why, in one or two sentences.> <Fixes #N.>
- <One sentence for each change a reviewer or user must know. At most three for a new API.>
Tested: <what ran, where, the result, and what was not tested.>
<Only if measured: the setup, then before and after.>
```

- Review reply: per point, one to three sentences: what changed and where, or why not. Thank a person at most once.
- Review comment: the problem, why, the fix, and whether it blocks.
- Maintainer request: what you need, why, and what you tried.
- Issue: the problem as the title. For a bug: what happened, what you expected, versions and a minimal repro. Report security problems privately.
- Code comment: why, only where not obvious.
- Docstring: what it does, plus what the signature hides: units, ranges, errors, side effects.
- Design doc: problem, goals and design, at the depth of similar docs. For a proposal, the rejected alternatives and why.