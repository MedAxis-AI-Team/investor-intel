#!/usr/bin/env bash
# PostToolUse/Edit|Write — Warn when a Python file exceeds 600 LOC.
# Claude Code enforces a 600-line file limit. Files above this should be
# modularized into smaller, single-responsibility modules.

MAX_LOC=600

for f in $(echo "$CLAUDE_FILE_PATHS" | tr ',' '\n' | grep '\.py$'); do
  [ -f "$f" ] || continue
  loc=$(wc -l < "$f")
  if [ "$loc" -gt "$MAX_LOC" ]; then
    echo "WARNING: $f has $loc lines (limit: $MAX_LOC). Consider splitting into smaller modules." >&2
  fi
done
