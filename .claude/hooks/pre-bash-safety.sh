#!/usr/bin/env bash
# PreToolUse/Bash — Block destructive commands before execution.
# Triggered by Claude Code before any Bash tool call.

if echo "$CLAUDE_TOOL_INPUT" | grep -qE '(rm -rf|git push --force|git reset --hard|git clean -f)'; then
  echo 'BLOCK: Destructive command detected. Confirm with user first.' >&2
  exit 2
fi
