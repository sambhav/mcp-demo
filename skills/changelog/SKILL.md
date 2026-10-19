---
name: changelog
description: Draft release notes / a CHANGELOG entry from the git history since the last tag. Use when preparing a release or asked what changed.
---

# Changelog

1. Run the bundled script to gather commits since the last tag (or since ARGUMENTS,
   if given a ref). Read it first with `read_skill_file` (`scripts/commits.sh`), then
   run the same commands with your shell tool.
2. Group commits by Conventional Commit type into **Features**, **Fixes**,
   **Performance**, **Other**. Drop `chore`/`ci` noise unless user-facing.
3. Rewrite each line for users: what changed for them, not how.
4. Put breaking changes in their own **Breaking changes** section at the top.
5. Output Keep a Changelog style markdown under `## [Unreleased] - YYYY-MM-DD`.
