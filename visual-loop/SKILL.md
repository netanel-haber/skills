---
name: visual-loop
description: "Look at every change the user will see before they do, and iterate with them on anything they judge by looking at it: pages, apps, components, charts, diagrams, slides, images, animations, logos and icons. Peek at each visible change in background screenshots while you keep answering, and fix what you find. For rounds of versions, keep one view that reloads by itself."
---

Follow the user's instructions first, then the project's rules, then this skill. Do every step. For what goes on a page, use visual-comms; for the words, use coding-comms.

**Read the medium** before the first change. Find what limits the work and the reader: the screen sizes and themes it is used at, the host's CSS tokens and components, the pixel grid of an icon, the character cell of text art (often twice as tall as wide), the palette, the export format. Work that ignores them looks wrong, and the user often can't say why.

## Peek at every visible change

1. **Start the peek as soon as the change is in,** in the background (a background shell job, or a subagent for anything that takes more than a few screenshots), and keep working with the user while it runs. Never wait for the user to look first.
2. **Take the screenshots that show what the user will see,** with a headless browser and a time limit (`timeout 40 chrome --headless --screenshot=... --window-size=W,H URL`):
   - at real size, at 1x and at 2x, at the user's window size and at a phone's;
   - in every place it is shown: on its own page, and embedded where it is used (a tile on another site, an iframe, a panel);
   - in every state the change touches, including each end of each control and all ends at once;
   - for an animation, a few frames at different points of its cycle.

   Crop and enlarge only to find what you saw at real size, never instead of it. What is clean when enlarged can be mush, stripes or moiré at its real size.
3. **Critique the pixels, not numbers.** A count of frames that change, a pixel diff, a passing test or a matching hash says that something moves or loads, not that it looks right. For each screenshot, ask: does it read as what it is meant to be at this size? Is anything clipped, blurred, striped, faint, misaligned, overlapping or broken? Would the user stop at it?
4. **Fix each problem you would not show,** then peek again at what the fix touches. A fix to one state can break another; look at the others too.
5. **Tell the user** in one line what the peek found and what you fixed, or that it found nothing, with the size and the place you looked at. Never say that something looks right without a peek behind it.

## Iterate in rounds

When the user chooses between versions, also do these steps.

1. **Keep one view that reloads by itself.**
   - If the work has its own dev server with live reload (a web app, a docs site, a slide tool), use it.
   - Otherwise, serve a scratch folder with `live-server --port=8001 --no-browser --quiet <folder>` in the background, and write the view to `index.html` there. End it with `</body>`: live-server adds its reload script there. Show what is not HTML inside that page: an image as `<img>`, a PDF or a slide as `<iframe>` or `<embed>`, a chart as its own output.
   - If the port is taken by your own earlier server, stop that one first.
   - Give the user the address once. After that, never give a new link: write each round over the same view.
2. **Build the round.**
   - Show each version where and how it is used: a page at the user's window size and at a phone's; a component in each state; an icon in a browser tab on a dark and a light bar at 1x and 2x; a logo at the size of each page that shows it; a chart with real data. Add a close-up of the part that changed.
   - When there is more than one version, put the current one first, so the user compares against it, and label each with what is different, in a few words.
   - Make versions that differ in one idea each. When the user can't say what is wrong, make a few that differ a lot.
   - Keep the scripts that make the versions in the scratch folder, so the next round changes one number, not the whole thing.
3. **Peek at every version before the user does,** and judge each as the user will see it, not in the close-up. Fix or remove each version you would reject. Do not show a round you would not pick from. Check the view itself: everything loads, the close-ups show the right part, the console has no errors.
4. **Tell the user** only "Look at the tab again", and at most one line: your pick and why, or what you could not fix. Do not describe each version; the labels do that.
5. **When the user picks,** put the version into the project, peek at it where it is really used (the site, the app, the browser tab, the exported file), and stop your server when the work is done.
