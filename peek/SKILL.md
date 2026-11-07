---
name: peek
description: "After every change the user will see (a page, a component, an image, an animation, an icon), start a background look at it in screenshots while you keep answering, then critique what you see and fix it before the user finds it."
---

Follow the user's instructions first, then the project's rules, then this skill. Do every step. visual-loop covers a round of versions on a live page; this covers every single change in between.

1. **Start the peek as soon as the change is in,** in the background (a background shell job, or a subagent for anything that takes more than a few screenshots), and keep working with the user while it runs. Never wait for the user to look first.
2. **Take the screenshots that show what the user will see:**
   - at real size, at 1x and at 2x, at the user's window size and at a phone's;
   - in every place it is shown: on its own page, and embedded where it is used (a tile on another site, an iframe, a panel);
   - in every state the change touches, including each end of each control and all ends at once;
   - for an animation, a few frames at different points of its cycle, at real size.
   Crop and enlarge only to find what you saw at real size, never instead of it.
3. **Critique against the pixels, not numbers.** A count of frames that change, a pixel diff, a passing test or a matching hash says that something moves or loads, not that it looks right. For each screenshot, ask: does it read as what it is meant to be at this size? Is anything clipped, blurred, striped, faint, misaligned, overlapping or broken? Would the user stop at it?
4. **Fix each problem you would not show,** then peek again at what the fix touches. A fix to one state can break another; look at the others too.
5. **Tell the user** in one line what the peek found and what you fixed, or that it found nothing, with the size and the place you looked at. Never say that something looks right without a peek behind it.
