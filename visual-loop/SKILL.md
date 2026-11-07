---
name: visual-loop
description: "Iterate with the user on anything they judge by looking at it: pages, apps, components, charts, diagrams, slides, images, logos and icons. Keep one view that reloads by itself, and look at each round in a screenshot before the user does."
---

Follow the user's instructions first, then the project's rules, then this skill. Do every step. For what goes on a page, use visual-comms; for the words, use coding-comms.

1. **Keep one view that reloads by itself.**
   - If the work has its own dev server with live reload (a web app, a docs site, a slide tool), use it.
   - Otherwise, serve a scratch folder with `live-server --port=8001 --no-browser --quiet <folder>` in the background, and write the view to `index.html` there. End it with `</body>`: live-server adds its reload script there. Show what is not HTML inside that page: an image as `<img>`, a PDF or a slide as `<iframe>` or `<embed>`, a chart as its own output.
   - If the port is taken by your own earlier server, stop that one first.
   - Give the user the address once. After that, never give a new link: write each round over the same view.
2. **Read the medium** before the first round. Find what limits the work and the reader: the screen sizes and themes it is used at, the host's CSS tokens and components, the pixel grid of an icon, the character cell of text art (often twice as tall as wide), the palette, the export format. Work that ignores them looks wrong, and the user often can't say why.
3. **Build the round.**
   - Show each version where and how it is used: a page at the user's window size and at a phone's; a component in each state; an icon in a browser tab on a dark and a light bar at 1x and 2x; a logo at the size of each page that shows it; a chart with real data. Add a close-up of the part that changed.
   - When there is more than one version, put the current one first, so the user compares against it, and label each with what is different, in a few words.
   - Make versions that differ in one idea each. When the user can't say what is wrong, make a few that differ a lot.
   - Keep the scripts that make the versions in the scratch folder, so the next round changes one number, not the whole thing.
4. **Look at it before the user does.**
   - Take a screenshot with a headless browser at the user's window size, with a time limit (`timeout 40 chrome --headless --screenshot=... --window-size=W,H URL`), in the background when it is slow. Take one for each size and state that the round changes. Crop and enlarge each part too small to judge.
   - Judge each version as the user will see it, not in the close-up: does it read as what it is meant to be? Is anything clipped, misaligned, unreadable or broken? Would the user stop at it, and why?
   - Look at the pixels, every time. A number is no look: a count of changing frames, a pixel diff, a passing check or a matching hash proves that something moves or loads, not that it looks right.
   - Look at real size and at 1x as well as 2x, in every place it is shown: embedded in its host (a tile on another site, an iframe, a panel), not only on its own page. What is clean when enlarged can be mush, stripes or moiré at its real size.
   - Look at every state the controls reach, not only the default: each end of each control, and all ends at once. A state that breaks at an end is a defect, however rare.
   - When an animation is made of frames, look at a few of them at real size, at different points of its cycle.
   - Fix or remove each version you would reject yourself, and look again. Do not show a round you would not pick from.
   - Check the view itself: everything loads, the close-ups show the right part, the console has no errors.
5. **Tell the user** only "Look at the tab again", and at most one line: your pick and why, or what you could not fix. Do not describe each version; the labels do that.
6. **When the user picks,** put the version into the project, check it where it is really used (the site, the app, the browser tab, the exported file), and stop your server when the work is done.
