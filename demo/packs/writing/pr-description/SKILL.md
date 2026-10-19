---
name: pr-description
description: Write a pull request title and description from the current branch's commits and diff. Use when opening a PR or asked to describe a change.
---

# PR description

1. `git log --oneline main..HEAD` and `git diff main...HEAD --stat` to see the change.
2. Title: imperative, under 70 characters, no trailing period.
3. Body sections: **Why** (the problem, 1-3 sentences), **What** (bullet list of changes),
   **How to test** (exact commands), **Risk** (what could break, rollout notes).
4. Link issues mentioned in commits. Keep it skimmable; no filler.
