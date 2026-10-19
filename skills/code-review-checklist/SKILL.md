---
name: code-review-checklist
description: Review a diff or set of files against a structured checklist (correctness, security, tests, readability). Use when asked to review code, a PR, or a change before merging.
allowed-tools: Read Grep Glob Bash(git diff:*) Bash(git log:*)
---

# Code review checklist

Review the change named in ARGUMENTS (a path, a branch, or `staged`; default: the
working tree's diff against HEAD).

Go through `references/checklist.md` section by section. For each finding give:

- **where**: `path:line`
- **what**: one sentence
- **why it matters**: the concrete failure, not a style preference
- **severity**: blocker / should-fix / nit

Report blockers first. Skip a section with no findings rather than padding it.
End with a one-line verdict: *ship it*, *ship after fixes*, or *needs another pass*.
