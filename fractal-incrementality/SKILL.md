---
name: fractal-incrementality
description: Reach a real answer fast by splitting every decision, large or small, into the smallest step that can confirm, shrink or kill the idea. Use for any uncertain work: research ideas, performance experiments, prototypes, debugging, cluster and environment setup.
---

# Fractal incrementality

At every decision point, take the smallest step that gives a real answer, then decide again. The rule is the same at every scale: the project, the experiment, the script, the single command.

## The loop

1. Name the question this step answers, and the result that would change the plan.
2. Find the cheapest step that answers it. Try smaller first: one shape, one layer, one GPU, one node, one file, a short run, an upper bound, a hook instead of a kernel, a one-liner instead of a script.
3. Run it, and read the result before doing anything else.
4. Decide: stop, go smaller, or grow by one size. Never skip a size.

## Order of work

- **Riskiest assumption first.** Check what the idea depends on most before building on it.
- **Bound before you build.** Measure the best case (the ideal kernel's time, a smaller dense op, a stub that skips the work) before writing the real thing. If the best case isn't worth it, stop.
- **Real hardware over models.** Simulators and byte counts only choose what to measure.
- **Reuse before you write.** Existing tools, tests, profilers and hooks come first.
- **One change per step.** Compare every step with the same baseline.

## The same rule at small scale

- Run a command on one item before all of them, and on one node before two.
- Run the first minute of a long job, and check its output, before the full run.
- Before patching, check that the target exists and matches what you patch against.
- Debug with the smallest input that still fails.
- When setup breaks, fix the smallest thing. Don't widen the scope.

## Keep it resumable

Log every step in one line each: the question, what ran, the result, the decision. Stop and report as soon as a result answers the question or kills the idea.
