---
name: sem-compress
description: Cleanup-only pass that makes code smaller by removing repetition, dead code, duplicated control flow and needless layers, without changing behavior or packing text. Use when asked to sem-compress, de-bloat, shrink or simplify a file, module or repository while keeping every feature.
---

# Semantic compression

Make the code smaller in substance, not in appearance. A change counts only if the program the machine runs (and the reader follows) gets simpler: fewer concepts, fewer layers, less duplicated logic. Line count is a side effect, never the goal.

## Arguments

`/sem-compress [path] [goal]`: the target file, directory or section (default: ask, or the obvious hot spot), and an optional goal such as a size target. If the goal can only be met by removing something that might count as a feature (vendored code, generated files, docs, tooling, fallbacks for rare cases), ask before removing it.

## What counts

- Remove dead code: unreachable branches, unused functions, exports, styles, selectors, variables, flags, config.
- Merge duplicated logic: two functions that fetch-parse-map the same way, two near-identical render blocks, copy-pasted control flow, parallel tables that should be one.
- Collapse layers: wrappers that only forward, helpers with one caller that read worse than their inlined body, abstractions with one implementation, indirection that exists for a past need.
- Delegate to primitives the language, platform or project already has instead of reimplementing them.
- Replace special cases with the general path when the general path already handles them correctly.
- Prefer early returns and flat flow over nested conditionals when it removes branches.

## What does not count

- Shortening names, removing blank lines, braces or comments that carry meaning, joining statements onto one line, chaining unrelated declarations, dense ternary chains.
- Macros, code generators, metaprogramming, decorators or helper DSLs whose expansion is the same amount of code (or more, or harder to follow). Judge every abstraction by its expanded form: the preprocessed source, the generated code, the compiled or bundled output, the CSS after cascade.
- Moving code to another file, package or config so the target looks smaller.
- Trading clarity for brevity: tricks whose correctness needs a proof, parameters only one caller uses, coupling to another function's incidental behavior, extra runtime cost, extra stack or memory, new side effects.

Never make the code even slightly worse to save lines. Stop when the next change would only hide structure.

## Workflow

1. Read the project's own guidance (README, AGENTS.md, CONTRIBUTING, style config) and the target in full before editing. Follow project rules where they are stricter than this skill.
2. Establish a baseline: run the formatter, record line counts (and bytes, if size is the goal), and capture the current behavior with whatever proves it: the test suite, a differential run against the old version, golden outputs, screenshots for UI.
3. Find the largest regions of repetition and wrapper layers first. Sort candidates by how much logic they remove, not how many lines.
4. Make one simplification at a time. Each must be simpler in both source and expanded form.
5. After each change: format, run the checks, compare behavior with the baseline. Any difference is a regression to fix or an intentional change to call out.
6. Measure the final size only after formatting. A delta taken before formatting, or earned by deleting whitespace, is not a result.
7. If a failure might be environmental, reproduce it on the unmodified baseline before calling it a regression.

## Proving behavior is unchanged

Use the strongest check available, in this order:
- A differential run: old and new versions on the same inputs (exhaustive small inputs, edge-case tokens, random inputs), outputs compared line by line.
- The project's test suite, plus tests for any path the change touches that the suite misses.
- For UI: render every state before and after, then pixel-diff the screenshots.
- For build or tooling scripts: run them, or at least syntax-check them and exercise their argument parsing.

## Report

- Line (and byte) delta per file and in total, measured after formatting.
- What survived and why each change is simpler: which layer, branch or duplicate it removed.
- What was rejected because it only compressed the source text, not the expanded code.
- The behavior check that ran and its result.
- Scope decisions you made or that need the user (anything removed that could be a feature).
