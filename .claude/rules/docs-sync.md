# Documentation Sync — investor-intel

## Rule
When making changes to files, always update the relevant documentation and architecture specs to reflect those changes. Documentation must stay in sync with the code at all times.

## What to update

| Change | Docs to update |
|--------|---------------|
| New endpoint or router | `CLAUDE.md` (Architecture section, routers list), `README.md` (Endpoints table, example requests) |
| New service or module | `CLAUDE.md` (Architecture section) |
| New dependency | `README.md` (if setup instructions change), `requirements.txt` |
| Changed scoring model, weights, or confidence logic | `CLAUDE.md` (Scoring model section), `README.md` (Scoring Model section) |
| New or changed config/env vars | `README.md` (Configuration section), `.env.example` |
| New test files or changed test counts | `README.md` (Tests section, test structure) |
| Benchmark system changes | `CLAUDE.md` (Benchmarking system), `README.md` (Benchmarking section) |
| Architectural decisions | `.claude/docs/adr/` (new ADR if significant) |
| Deployment changes | `CLAUDE.md` (Deployment), `render.yaml`, `README.md` (Deployment section) |

## Where docs live
- `CLAUDE.md` — Architecture, conventions, and commands for Claude Code
- `README.md` — Setup, endpoints, tests, benchmarking, scoring model for humans
- `.claude/docs/adr/` — Architectural Decision Records
- `.claude/docs/tasks/` — Implementation task tracking
- `.claude/docs/decisions/` — Session decision log
- `.claude/rules/` — Rules files (including this one)
