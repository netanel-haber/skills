---
name: visual-comms
description: "Design, build and review visual output about technical work: pages, dashboards, tools, tables, charts, diagrams, and images in PRs and docs. The visual counterpart of coding-comms."
---

Follow the user's instructions first, then the host project's look and rules, then this skill. Do every step. For the words on the page, use coding-comms.

1. **Read the data and the host.**
   - Write down the reader's questions, in order. The first answer goes at the top.
   - For each answer, list the facts with their units, conditions, versions, dates and sources. Mark each estimate and each piece of sample data.
   - Read the host in a browser: its CSS tokens, components and states. Reuse them. With no host, use one light theme and the system fonts.
2. **Choose one form for each fact,** and show each fact once.
   - One result: the number, its unit and its state, with its conditions next to it.
   - A few values to compare: a table. A trend or a tradeoff: a chart.
   - A flow: a plain-text diagram or a simple SVG.
   - A command or a config: a code block with a copy button.
   - Full commands, logs, methods and raw data: a collapsed `<details>`.
3. **Lay out the page.**
   - At 1920 × 1080, the first screen holds the controls, the answer and its state.
   - Order the sections: the answer, its conditions, the evidence, the method.
   - Use one 4 px grid. Keep prose to 72 characters per line.
4. **Cut:**
   - decoration: gradients, glows, shadows, emoji, and icons that repeat their label;
   - sentences where a labeled value would do, and text that repeats the data or a label;
   - rows that do not earn their height, internal settings, sales words and placeholder text;
   - digits that the measurement does not support, controls that do nothing, and colors without a meaning.
5. **Build** with the host's stack, or with no host, one HTML file with inline CSS and JS. Put the data in one object, and make every view from it. Use inline SVG for small charts. Label mock data once, near the top.
6. **Check in a browser, and look at every screenshot.**
   - At 1920, 1440, 1024 and 390 px wide: no horizontal scroll, clipped text or overlap.
   - Open each state from its URL: default, hover, focus, empty, error, loading and each data state.
   - Click every control, and read the result back from the page. Do one pass with the keyboard only.
   - The console has no errors or warnings, and no request fails.
   - Contrast is at least 4.5:1 for text and 3:1 for lines and control borders.
   - Put the page next to the host at the same width. Fix each difference that the host does not explain.
7. **Show** the screenshots and the address before you publish.

## Look

- Use one theme on a page: the host's. Only the one thing that the reader came for, such as a command, can stay dark on a light page.
- Use one accent color, exactly the brand color if there is one, only for the primary action, the selection and links.
- Use two font weights and at most four text sizes. Make hierarchy with size and weight, not with color.
- Use a monospace font for code and identifiers, and tabular figures for numbers in a column.

## Numbers and tables

- Give each number its unit, in its label or its column header. Right-align numbers and left-align text.
- Use thousands separators, and the same decimals in a column. Give measured values their spread and count.
- Show a change as before → after, with the result in bold.
- Put the conditions that differ between numbers next to each number, and the shared environment in a box of its own.
- All the numbers in one panel come from one measurement. Compute each summary sentence from the data.
- Sort a table by the column that answers the question, and make bold only the answer.

## Charts

- Label each axis with its metric and unit, at round ticks. Axes of amounts start at zero.
- With four series or fewer, label the lines, not a legend.
- Show the exact values on hover and on keyboard focus. Do not use 3D or two y-axes.

## Commands

- The copy button copies exactly the command on the screen, and confirms with a word. Draw labels with CSS, so that a selection copies only the command.
- Put environment variables first, then one flag on each line. Pin the version: an image digest or a commit.

## States

- Give each record one state, with a word and a status color, its evidence and its date. Status colors mean status only.
- Do not show a number, a chart or a panel that no data supports. Say what is absent and why.
- A blocked choice shows the rule that blocks it and one way out. Never fall back to another choice in silence.

## Controls and links

- Use native elements with a visible focus ring. Give each hover effect to keyboard focus too.
- Link every external thing that has a page, such as the release, the commit or the source run.
- Keep the selection in the URL, as names that say what they are (`view=latency`), not indices. One function reads and writes the address.
- A link that does not make sense opens the closest view under a red banner that lists each bad part.

## PRs and docs

- Put the headline result in a heading, and before and after in a Markdown table with the setup under it.
- Use a screenshot only to prove what text cannot.
- Link code at a pinned commit and line range.
