# Git Changelog

Generate a summary of git changes for tracking and review.

## What This Command Does

1. Shows recent commits with diff stats
2. Lists all modified files since last tag or specified commit
3. Categorizes changes by type (feat, fix, refactor, etc.)
4. Appends summary to `.claude/docs/git-changelog.log`

## Process

1. Run `git log --oneline --since="1 week ago"` for recent history
2. Run `git diff --stat HEAD~10` for change scope
3. Group commits by type prefix
4. Write summary to `.claude/docs/git-changelog.log` with timestamp
5. Display summary to user

## Output Format

```
## Git Changelog — YYYY-MM-DD

### Features
- <commit hash> <description>

### Fixes
- <commit hash> <description>

### Other
- <commit hash> <description>

### Files Changed
- <file> (+additions / -deletions)
```
