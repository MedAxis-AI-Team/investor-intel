#!/usr/bin/env bash
# Stop — Append git status snapshot to the changelog log at session end.
# Triggered by Claude Code when the session stops.

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

if [ -d .git ]; then
  echo '--- Session End Git Status ---' >> .claude/docs/git-changelog.log 2>/dev/null
  git log --oneline -5 >> .claude/docs/git-changelog.log 2>/dev/null
  echo '' >> .claude/docs/git-changelog.log 2>/dev/null
fi
