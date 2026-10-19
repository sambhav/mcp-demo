#!/usr/bin/env sh
# Prints commits since the last tag (or since $1) as "<hash> <subject>".
set -eu
since="${1:-$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)}"
git log --no-merges --pretty='%h %s' "${since}..HEAD"
