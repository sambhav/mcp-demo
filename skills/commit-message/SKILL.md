---
name: commit-message
description: Write a Conventional Commits message for the staged changes. Use when the user asks to commit, or to write or improve a commit message.
---

# Commit message

1. Run `git diff --cached --stat` and `git diff --cached` to see what is staged.
   If nothing is staged, say so and stop.
2. Pick the type: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `build` or `ci`.
   Add a scope in parentheses when the change sits in one area: `feat(server): ...`.
3. Subject line: imperative mood, lower case, no trailing period, at most 72 characters.
4. Body (only when the why is not obvious): wrap at 72, explain *why*, not *what*.
5. Footer: `BREAKING CHANGE: ...` for incompatible changes; `Refs: #123` for issues.

Show the message, then commit with `git commit -F -` reading it from a heredoc.
If ARGUMENTS are given, treat them as a hint about intent.
