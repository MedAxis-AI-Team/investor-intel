# Record Decision

Track a decision made during development. Decisions capture the "why" behind choices that aren't obvious from code alone.

## What This Command Does

1. Records a decision with context, rationale, and alternatives considered
2. Saves to `.claude/docs/decisions/` with a timestamped filename
3. Links to related ADRs or tasks if applicable

## Process

1. Ask the user (or infer from context):
   - **What** was decided?
   - **Why** this choice over alternatives?
   - **What alternatives** were considered?
   - **What are the consequences?**
2. Write to `.claude/docs/decisions/YYYY-MM-DD-<slug>.md`
3. Confirm with the user

## Template

```markdown
# Decision: <title>
Date: YYYY-MM-DD
Status: accepted | superseded | deprecated
Related: [ADR-NNN](../adr/NNN-title.md) | [Task](../tasks/...)

## Context
<What prompted this decision>

## Decision
<What we chose to do>

## Rationale
<Why this approach>

## Alternatives Considered
- <Alternative 1>: <why not>
- <Alternative 2>: <why not>

## Consequences
- <positive or negative outcomes>
```
