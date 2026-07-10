---
name: Bug report
about: Something that worked before is broken, or expected behavior is missing
title: "[bug] "
labels: ["bug"]
assignees: []
---

## Summary

<!-- One-sentence description of what broke. -->

## Steps to reproduce

1.
2.
3.

## Expected behavior

<!-- What you expected to happen. -->

## Actual behavior

<!-- What actually happened. Paste the relevant log lines if any. -->

```
<log output here, with secrets redacted>
```

## Environment

- WACTL version / commit SHA:
- Python version (`python --version`):
- Deployment:
  - [ ] Local
  - [ ] AWS (env: dev / staging / prod)
- AWS region:
- Webhook URL (if applicable):

## Input

<!-- What message did you send to the bot? Include the slash command and
     (where relevant) a stripped-down version of the payload. -->

## Severity

- [ ] Critical — bot is unreachable, no responses at all
- [ ] High — one specific command broken
- [ ] Medium — degraded behavior, workaround exists
- [ ] Low — cosmetic, typo, docs

## Checklists

- [ ] I searched [existing issues](../../issues) and didn't find this
- [ ] I can reproduce on `main`
- [ ] I'm not reporting a [security vulnerability](../../security/advisories/new)
      (those should go to security@wactl.example — see [SECURITY.md](../../blob/main/SECURITY.md))
- [ ] I redacted all secrets from logs and config snippets above