# Create ADR

Create an Architectural Decision Record to document significant architecture choices.

## What This Command Does

1. Creates a numbered ADR in `.claude/docs/adr/`
2. Documents the architectural decision with full context
3. Links to related decisions and tasks

## When to Use

- Adding a new endpoint or service pattern
- Changing the LLM integration approach
- Modifying the auth or rate limiting strategy
- Adding new infrastructure (caching, queues, databases)
- Changing deployment or configuration patterns

## Process

1. Find the next ADR number: count existing files in `.claude/docs/adr/`
2. Gather context from the user or current work
3. Write ADR using the template below
4. Save to `.claude/docs/adr/NNN-<slug>.md`

## Template

```markdown
# ADR-NNN: <title>
Date: YYYY-MM-DD
Status: proposed | accepted | deprecated | superseded by ADR-NNN

## Context
<What is the issue that we're seeing that motivates this decision>

## Decision
<What is the change that we're proposing and/or doing>

## Consequences

### Positive
- <benefit>

### Negative
- <tradeoff>

### Risks
- <what could go wrong>

## Implementation Notes
- <key files affected>
- <migration steps if any>
```

WAITING FOR CONFIRMATION before saving the ADR.
