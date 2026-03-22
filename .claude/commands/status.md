# Project Status

Show current project status including git state, open tasks, and recent decisions.

## What This Command Does

1. Shows current git branch, recent commits, and uncommitted changes
2. Lists open tasks from `.claude/docs/tasks/`
3. Lists recent decisions from `.claude/docs/decisions/`
4. Shows test coverage summary

## Process

1. Run `git status` and `git log --oneline -10`
2. Read task files in `.claude/docs/tasks/` — show incomplete items
3. Read recent decision files in `.claude/docs/decisions/`
4. Run `coverage report -m` if `.coverage` exists
5. Display consolidated summary
