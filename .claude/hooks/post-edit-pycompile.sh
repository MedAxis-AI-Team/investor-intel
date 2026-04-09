#!/usr/bin/env bash
# PostToolUse/Edit|Write — Syntax-check every edited Python file.
# Triggered by Claude Code after any Edit or Write tool call.

for f in $(echo "$CLAUDE_FILE_PATHS" | tr ',' '\n' | grep '\.py$'); do
  python -m py_compile "$f" 2>&1 || true
done
