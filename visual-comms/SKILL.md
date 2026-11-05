---
name: visual-comms
description: "Design, build and review visual output about technical work: pages, dashboards, tools, tables, charts, diagrams, and images in PRs and docs. The visual counterpart of coding-comms."
---

Follow the user's instructions first, then the host project's look and rules, then this skill. Do every step. For the words on the page, use coding-comms.

1. **Read the data and the host.**
   - Write down the questions that the reader brings, in order. The answer to the first question goes at the top.
   - For each answer, list the facts: values, units, conditions, versions, dates and sources. Mark each fact that is not a measurement, such as an estimate, a candidate or sample data.
   - Read the host: its CSS tokens, components, states and data API. Open it in a browser and take screenshots. A new page uses the same tokens and components.
   - If there is no host, use one light theme, the system font stack and one accent color.
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
   - Sentences. The page is informative, not talkative: a value goes in a labeled field, a key goes in a legend, and a count is the link to what it counts ("10 snippets ↗").
   - Text that repeats the data, the heading, the control label, or what is obvious (a "shell" label on a shell command).
   - Each row that does not earn its height: a title above an obvious card, a description blurb, a head row that repeats the breadcrumbs. Merge rows instead: the tabs and the meta line in one row, the count and the chart tools in one row.
   - Details that the reader does not use. A label shows what the reader chooses by (GPUs, throughput), not internal settings (TP, MTP, kernel names). A chart shows only the points that answer the question.
   - Sales words, slogans and placeholder text.
   - Fake precision: more digits than the measurement supports.
   - Each control or link that does nothing. In a mock too, every control works.
   - Each color without a meaning.
5. **Build.**
   - Use the host's stack. If there is no host, write one HTML file with inline CSS and JS and no build step.
   - Put the data in one object, and make every view from it. Then two views cannot show two values for one fact.
   - Keep the selection in the URL, so that a link opens the same view. Each value in a link is a name that says what it is (`point=tp4-ep-mtp5-c8`), not an index. A name never changes, and two items never share one.
   - A link that does not make sense opens the closest view under a red banner. The banner has one row for each bad part: the part, a short reason, and the valid choices as links.
   - Use inline SVG for small charts. Use a chart library only if the host already uses one.
   - Label mock data once, near the top of the page.
6. **Check in a browser, and look at every screenshot.**
   - Widths: 1920, 1440, 1024 and 390 px. Skip 390 px if the page is desktop-only, such as a tool behind a VPN. No horizontal scroll, no clipped text, no overlap, and no heading that ends in one word on its own line.
   - States: default, hover, focus, empty, error, loading, blocked and each data state. Open each one from its URL.
   - Open a bad link once, without a reload. A page that cleans its URL on load shows the clean link after a reload, not the bad one.
   - Click every control, then read the result back from the page: the URL, the title, the copied text. Do one pass with the keyboard only.
   - When a state changes, the layout does not jump. Reserve the space only where something below would move; a reserved band with nothing below it is a defect.
   - The page loads without a reflow: a skeleton at each box's final size holds its place, and the real content replaces it in one step. Nothing shows until all the data that decides the first view is in.
   - The page requests only its own files. Decide everything else (a release name, a link target) from the repo's data, not from another host's API at load time.
   - Switch between every pair of views, and back, and check that each shows its own data. A view that was built once and kept aside can keep the old data.
   - The console shows no errors and no warnings, and no request fails.
   - Contrast is at least 4.5:1 for text and 3:1 for chart lines and control borders. Measure the host's colors too.
   - For each number on the page, find its source and its unit.
   - Put the page next to the host at the same width. Fix each difference that the host does not explain.
   - Before you remove a feature or a theme, take screenshots of every state. After it, compare them pixel by pixel. Each difference outside the removed part is a regression.
   - When the user watches a live reload, make each change in one write that leaves the page working, and look at the screenshots before the next change.
7. **Show** the screenshots and the address before you publish. Say which data is mock data.

## Look

- Use the host's theme. If the host has only a dark theme, do not add a light theme.
- Use one theme on a page. The one exception is the star, the command that the reader came for: it can stay dark on a light page. Each other box follows the page, or the eye jumps between themes.
- A light theme is not a dark theme with its colors flipped. Tint the page and the cards with one hue, a little apart. Plain grey with pure white cards looks corporate and glares.
- Use two surface colors (the page and the card) and at most one tint that means something. A box inside a card takes the card's color and a border; a third, close tint looks like a hole.
- The star fills its card edge to edge. Do not frame it twice, and do not put a glow or a colored border around it.
- Use one accent color, only for the primary action, the selection and links. If the organization has a brand color, the accent is exactly that color, such as NVIDIA green (#76b900). Do not darken it.
- Where the accent fails contrast as text, as green does on a light page, use it only for fills, lines, underlines and borders. A link is dark text with a 2 px accent underline, and a button is an accent fill with dark text.
- Navigate with breadcrumbs in the header, each a dropdown of its choices, not with a sidebar. Group a long dropdown (`optgroup`) by family, and sort sizes as numbers.
- Status colors (green, amber, red, gray) mean status only. Always put a word next to the color.
- Use two font weights and at most four text sizes. Make hierarchy with size and weight, not with color.
- Thin, dim text on a dark background looks fragile. Use weight 500 for body and code text, and bright secondary text (about #a6b4c8 on #020618).
- Embed the monospace font (a variable WOFF2, Latin subset), so that code looks the same on every machine.
- Use tabular figures (`font-variant-numeric: tabular-nums`) for each number in a column and each value that changes.
- Use a monospace font for commands, flags, paths, hashes and identifiers.
- Chart text (ticks, axis titles) differs from the page's text: monospace, in a quiet tint of the axis color, and not selectable.
- Keep each range, value with its unit, and identifier on one line: 26–28%, PR #55390. Balance the lines of headings (`text-wrap: balance`).
- Use one border radius for cards and one for controls. On a dark background, do not use shadows to separate cards.
- On a light page, a 1 px light border looks brittle: give the cards 2 px. The dark star keeps 1 px, as a light rim around it frames it twice. Browsers round a fractional border down to whole pixels, so 1.5 px draws as 1 px.
- Never use a dull grey for a surface, a chip or a muted control. Tint it with the page's hue or the accent.
- The primary action is the one strong button. If the accent fails contrast with both dark and light text, make the button dark like the star, with the accent in its icon.
- Turn off ligatures on the whole page (`font-variant-ligatures: none`, after every `font` shorthand, or with `!important`): a monospace font can join `###` into one glyph.
- Style every native control for the theme. A white default input on a dark page is a bug.

## Numbers

- Give each number its unit, in its label or in its column header: "Output TPS/GPU", "TTFT (ms)".
- Show the numbers that the reader compares as one quiet row: small labels over figures a little larger than the text. Boxed tiles with large figures compete with the chart and the command.
- Put the environment that measured the numbers (version, image, checkpoint, session, workload) in its own box, apart from what the page recommends.
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
- Draw a constraint, such as a floor or a target, as a dashed line. Label it with its value, unless an axis tick already sits on it.
- Mark the chosen point with a color of its own that no other point has, with good contrast, and a small arrow above it that points down and bobs a little (still under reduced motion). No ring.
- Put one border around the whole graph, with its axes and labels inside, and padding. The graph keeps the card's color; do not give it a fill of its own.
- Give a chart a fixed shape (16:9), so that its height follows its width: never the window's height, and never the data.
- Give each point a halo in the background color, so that close points and the line stay apart. Draw the chosen point once more, above every point.
- Do not add an inset or a minimap: zoom serves close points.
- Axes of amounts start at zero and end a little past the largest value. Tick the x axis at round steps that include each constraint.
- A drag on the plot zooms to the rectangle as drawn, not to the tight extent of its points. The zoom hint and "Clear zoom" are a chip in the chart's top-right corner, with the other chips (the data's date, as a date-time that links to its commit).
- Give the few points that a reader quotes (the best of each objective) a name and an icon. Draw each as a small disc with its icon inside, in place of its dot, and a little see-through. Name them in a boxed key in the plot's empty corner, show the name first in the hover tooltip, and use the same icon component wherever they appear.
- The details of the selected point go under the chart.
- Mark each limit that the data shows, such as a cliff or an overflow. If a note collides with the data or a label, move it to the caption.
- If tick labels touch, show every second label.
- Show the exact values on hover and on keyboard focus.
- A color means the same thing in every chart on the page.
- Bars start at zero. Do not use 3D, gradients or two y-axes.
- Do not draw an empty chart. Write what is absent and why.

## Commands

- The copy button copies exactly the text on the screen. It confirms with a word, then goes back.
- The copy button is in the box that it copies, on a tab on the box's top edge: it takes no height and covers no text. Leave at least 8 px between the tab and the row above it.
- A long command also has a button that copies it as one line, without its line continuations. Label it by what it removes: `no \`.
- A selection of a command copies only the command. Draw every label, group name and link arrow with CSS (`::before`, `::after`, `attr()`), and make each line a block.
- Highlight shell, and only shell, with one small tokenizer: the command, flags, numbers, other values, strings, comments and line continuations. Each has a visible color; continuations are quiet but readable.
- Group the flags by subsystem (parallelism, MoE, KV cache, Mamba, speculative decoding, vision), with a faint colored edge and the group name small and faint on the right of its first line. Flags that match no group come first, with no name. A long line pushes the name down; it never runs into it.
- Where many commands share most flags, show the shared lines first and each command's own lines after them, each part named on its right. Changing the command changes only its own part.
- Put one flag on each line, with a line continuation. Use flag forms that need no JSON quotes.
- Pin the version: an image tag or digest, or a commit. Put the image's pull command on a row above the command, in the same dark box, with its own copy button.
- Show the command for the version it pins: drop each flag that is a default or does nothing there, rename each renamed flag, and drop what only the measurement needed. Do it in one function, and keep the stored data as measured.
- Name the shared part and the own part on a tab that sits on the line between them: centered, with a border only where its colors differ from the box under it. When the selection changes, the own part glows faintly once.
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
- A click picks a point. A separate checkbox for the same choice is noise; give "Select all" and "Unselect all" instead.
- Link every external thing that has a page: the model card (only if it exists), the image tag, the release, the commit, the source run. Draw the link arrow with CSS.
- Use a segmented control for two to five options, and a select for more.
- Make each control target at least 32 px high.
- Give each hover effect to keyboard focus too.
- A disabled option says why, in its label or its title.

## Export

- An export makes Markdown for another document: a native dialog, opened by the primary button.
- Its scope follows the breadcrumbs: a segmented control of their levels, where a level takes in everything under it, and the chosen level and every level after it are highlighted.
- Checkboxes, under a short label, choose what goes in. The Markdown shows in a box dark like the star, highlighted like it, with a primary copy button.
- The Markdown holds what the target needs (headings, the version, the commands), not every number on the page.

## Links

- One function owns the link: it reads the address once, gives each state its first value, checks each value for the banner, and writes the address back. Nothing else touches the address.
- A choice that the page computes, such as the best point at a floor, has a stable name in the link (`point=min-latency`). When a click picks an item that a name means, the link shows the name.
- An open dialog and its choices are in the link too.

## PRs and docs

- Put the headline result in a heading: "Representative result: +2.62% output TPS".
- Use a Markdown table for before and after, with the setup in a list under it.
- Put full commands, environments and logs in `<details>`.
- Use a screenshot only when it proves something that text cannot. Crop it to the part that proves it.
- Draw shapes and flows as aligned plain text in a code block.
- Link code at a pinned commit and line range, not at a branch.
