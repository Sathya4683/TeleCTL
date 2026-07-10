---
name: Feature request
about: Suggest a new command, integration, or capability
title: "[feat] "
labels: ["enhancement"]
assignees: []
---

## What is the request?

<!-- A one-paragraph description of the new capability. -->

## Motivation

<!-- What user problem does this solve? Be specific about the workflow. -->

## Proposed behavior

<!-- End-to-end: what the user types, what the bot does, what it sends back. -->

```
User: /new-command <args> + <attachment>
Bot:  "Processing…"
Bot:  📎 <result>
```

## Alternatives considered

<!-- Why this approach over something simpler / cheaper / more general? -->

## Acceptance criteria

<!-- What "done" looks like. -->

- [ ] Registered under `/new-command`
- [ ] Decides `sync=True` or `sync=False`, with rationale
- [ ] Unit tests cover happy path + at least one error path
- [ ] Documented in [docs/CODEBASE_GUIDE.md](../../blob/main/docs/CODEBASE_GUIDE.md)
- [ ] Listed in [web/lib/site.ts](../../blob/main/web/lib/site.ts) `COMMANDS`

## Out of scope

<!-- Anything you'd want a follow-up to handle. -->

## Additional context

<!-- Links to upstream APIs, similar tools, design references. -->