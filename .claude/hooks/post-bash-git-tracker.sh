#!/usr/bin/env bash
# PostToolUse/Bash — Append git mutating commands to the changelog log.
# Triggered by Claude Code after any Bash tool call.

if echo "$CLAUDE_TOOL_INPUT" | grep -qE '^git (commit|merge|rebase|cherry-pick)'; then
  echo "[git-tracker] $(date '+%Y-%m-%d %H:%M:%S') | $CLAUDE_TOOL_INPUT" \
    >> .claude/docs/git-changelog.log 2>/dev/null || true
fi
