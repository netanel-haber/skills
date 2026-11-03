---
name: visual-comms
description: "Design, build and review visual output about technical work: pages, dashboards, tools, tables, charts, diagrams, and images in PRs and docs. The visual counterpart of coding-comms."
---

Follow the user's instructions first, then the host project's look and rules, then this skill. Do every step. For the words on the page, use coding-comms.

1. **Read the data and the host.**
   - Write down the questions that the reader brings, in order. The answer to the first question goes at the top.
   - For each answer, list the facts: values, units, conditions, versions, dates and sources. Mark each fact that is not a measurement, such as an estimate, a candidate or sample data.
   - Read the host: its CSS tokens, components, states and data API. Open it in a browser and take screenshots. A new page uses the same tokens and components.
   - If there is no host, use one dark theme, the system font stack and one accent color.
2. **Choose one form for each fact.**
   - One result: the number, its unit and its state, with its conditions next to it.
   - A few values to compare: a table.
   - A tradeoff or a trend on a continuous axis: a chart.
   - A flow or a data shape: a plain-text diagram or a simple SVG.
   - A command or a config: a code block with a copy button.
   - Full commands, logs, methods and raw data: a collapsed `<details>` section.
   - Show each fact once. A table of the values in a chart is a repetition, unless the table is in `<details>`.
3. **Lay out the page.**
   - At 1920 × 1080, the first screen holds the controls, the answer and its state. At 390 px wide, the answer comes before the evidence.
   - Order the sections as the reader uses them: the answer, then its conditions, then the evidence, then the method.
   - Use one grid and one spacing scale in multiples of 4 px. Align every edge to the grid.
   - Align the cards in a row to the top. A card that stretches and leaves an empty band is a defect.
   - Keep prose to 72 characters per line. Tables and charts can use the full width.
   - On a narrow screen, fold the controls into one summary line above the answer. Show each table row as a block, with each cell under its column name.
4. **Cut.**
   - Decoration: gradients, glows, shadows, illustrations, emoji, and icons that repeat their label.
   - Text that repeats the data, the heading or the control label.
   - Sales words, slogans and placeholder text.
   - Fake precision: more digits than the measurement supports.
   - Each control or link that does nothing. In a mock too, every control works.
   - Each color without a meaning.
5. **Build.**
   - Use the host's stack. If there is no host, write one HTML file with inline CSS and JS and no build step.
   - Put the data in one object, and make every view from it. Then two views cannot show two values for one fact.
   - Keep the selection in the URL, so that a link opens the same view.
   - Use inline SVG for small charts. Use a chart library only if the host already uses one.
   - Label mock data once, near the top of the page.
6. **Check in a browser, and look at every screenshot.**
   - Widths: 1920, 1440, 1024 and 390 px. No horizontal scroll, no clipped text, no overlap, and no heading that ends in one word on its own line.
   - States: default, hover, focus, empty, error, loading, blocked and each data state. Open each one from its URL.
   - Click every control, then read the result back from the page: the URL, the title, the copied text. Do one pass with the keyboard only.
   - When a state changes, the layout does not jump. Reserve the space.
   - The console shows no errors and no warnings, and no request fails.
   - Contrast is at least 4.5:1 for text and 3:1 for chart lines and control borders. Measure the host's colors too.
   - For each number on the page, find its source and its unit.
   - Put the page next to the host at the same width. Fix each difference that the host does not explain.
7. **Show** the screenshots and the address before you publish. Say which data is mock data.

## Look

- Use the host's theme. If the host has only a dark theme, do not add a light theme.
- Use one accent color, only for the primary action, the selection and links.
- Status colors (green, amber, red, gray) mean status only. Always put a word next to the color.
- Use two font weights and at most four text sizes. Make hierarchy with size and weight, not with color.
- Use tabular figures (`font-variant-numeric: tabular-nums`) for each number in a column and each value that changes.
- Use a monospace font for commands, flags, paths, hashes and identifiers.
- Keep each range, value with its unit, and identifier on one line: 26–28%, PR #55390. Balance the lines of headings (`text-wrap: balance`).
- Use one border radius for cards and one for controls, and 1 px borders. On a dark background, do not use shadows to separate cards.
- Style every native control for the theme. A white default input on a dark page is a bug.

## Numbers

- Give each number its unit, in its label or in its column header: "Output TPS/GPU", "TTFT (ms)".
- Use thousands separators, and the same number of decimals in a column: 1,137 and 95.7%.
- Give measured values their spread and count when they have them: 1,751.5 ± 3.8 (n=4).
- Show a change as before → after, and put the result in bold: 92.02 → **95.71**.
- Put the conditions near the number: hardware, concurrency, workload, version and date.
- Define each derived metric once, at its first use, with its formula.
- All the numbers in one panel come from one measurement. Do not put the latency of one run next to the throughput of another.
- Make each summary sentence from the data, and only over the points where the comparison is true. Exclude failed or overflowed points.
- Use absolute dates and exact versions.

## Tables

- Right-align numbers and left-align text. Align each header with its column.
- One row for each item and one fact in each cell. Put the units in the header, not in the cells.
- In an uppercase header, units and symbols keep their case: "TTFT (ms)", not "TTFT (MS)".
- Make bold only the values that answer the question, such as the winner.
- Sort by the column that answers the question, and show which column it is.
- A long table has a sticky header and a row count.

## Charts

- Label each axis with the metric and the unit. Use round tick values in the unit of the data. A tick never shows clock time with milliseconds.
- With four series or fewer, put the labels on the lines, not in a separate legend.
- Draw a constraint, such as a floor or a target, as a line with its value. Put a ring on the chosen point.
- Mark each limit that the data shows, such as a cliff or an overflow. If a note collides with the data or a label, move it to the caption.
- If tick labels touch, show every second label.
- Show the exact values on hover and on keyboard focus.
- A color means the same thing in every chart on the page.
- Bars start at zero. Do not use 3D, gradients or two y-axes.
- Do not draw an empty chart. Write what is absent and why.

## Commands

- The copy button copies exactly the text on the screen. It confirms with a word, then goes back.
- Put one flag on each line, with a line continuation. Use flag forms that need no JSON quotes.
- Pin the version: an image tag or digest, or a commit.
- Put environment variables before the command, one on each line.
- Make each form of a command (shell, container, scheduler, config file) from the same list of flags.

## States

- Give each record one state, with a word and a color, such as validated, candidate, stale, regressed or blocked.
- A state is a claim. Show its evidence and its date next to it.
- Do not show expected numbers that no measurement supports. Say what is absent and why.
- The title of a panel agrees with its state. Do not write "Expected" above a panel that has no numbers.
- The state note and the panel body say different things. Do not repeat a sentence between them.
- A blocked choice shows the rule that blocks it and one way out. Never fall back to another choice in silence.

## Controls

- Use native elements: `button`, `select`, `input`, `details` and `a`. Each one shows a visible focus ring.
- Use a segmented control for two to five options, and a select for more.
- Make each control target at least 32 px high.
- Give each hover effect to keyboard focus too.
- A disabled option says why, in its label or its title.

## PRs and docs

- Put the headline result in a heading: "Representative result: +2.62% output TPS".
- Use a Markdown table for before and after, with the setup in a list under it.
- Put full commands, environments and logs in `<details>`.
- Use a screenshot only when it proves something that text cannot. Crop it to the part that proves it.
- Draw shapes and flows as aligned plain text in a code block.
- Link code at a pinned commit and line range, not at a branch.
