---
name: visual-loop
description: "Iterate on visual work with the user, such as a logo, an icon, an image or a page: show the versions on one page that reloads by itself, and look at each round in a screenshot before the user does."
---

Follow the user's instructions first, then the project's rules, then this skill. Do every step. For what goes on a page, use visual-comms; for the words, use coding-comms.

1. **Serve one page.**
   - Run `live-server --port=8001 --no-browser --quiet <folder>` on a scratch folder, in the background. If 8001 is taken by your own earlier server, stop that one first.
   - Write the page to `index.html` in that folder, and end it with `</body>`: live-server adds its reload script there, and without it the page does not reload.
   - Give the user the address once. After that, never give a new link: write each round over the same page.
2. **Read the medium** before the first round. Find what limits the drawing: the pixel grid of an icon, the size of a character cell in ASCII art (often twice as tall as wide), the palette, the sizes it will be shown at. A shape drawn without these looks wrong, and the user can't say why.
3. **Build the round.**
   - Show each version at every size where it will be used: an icon in a browser tab on a dark and a light bar, at 1x and 2x; a logo at the size of each page that shows it; a close-up of the part that changed.
   - Put the current version first, so the user compares against it.
   - Label each version with what is different, in a few words.
   - Make versions that differ in one idea each. When the user can't say what is wrong, make a few that differ a lot.
   - Keep the scripts that make the versions in the scratch folder too, so the next round changes one number, not a drawing.
4. **Look at it before the user does.**
   - Take a screenshot of the page with a headless browser at the user's window size, with a time limit (`timeout 40 chrome --headless --screenshot=... --window-size=W,H URL`), in the background when it is slow. Crop and enlarge each part that is too small to judge.
   - Judge each version at its real size, not in the close-up: does it read as what it is meant to be? Would the user stop at it, and why?
   - Fix or remove each version you would reject yourself, and look again. Do not show a round that has none you would pick.
   - Check that the page itself works: the images load, nothing is clipped, the close-ups show the right part.
5. **Tell the user** only "Look at the tab again", and at most one line: your pick and why, or what you could not fix. Do not describe each version; the labels do that.
6. **When the user picks,** write the version into the project, check it where it is really shown (the site, the browser tab), and stop the server when the work is done.
