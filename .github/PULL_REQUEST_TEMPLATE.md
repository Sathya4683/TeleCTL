---
name: Pull request
about: Submit a change to WACTL
---

## What does this PR do?

<!-- One-paragraph summary. Mention the affected command(s) / integration(s) /
     infra component(s). -->

## Related issues

<!-- Link any issues this PR closes or references. Use `Closes #123` /
     `Fixes #456` so they're auto-closed on merge. -->

Closes #

## How to test

<!-- Step-by-step verification. For code changes, paste the exact pytest
     invocation. For Terraform changes, paste the plan output. -->

```bash
uv run pytest tests -q
```

- [ ] I ran the test suite locally and it passed
- [ ] I ran `uv run ruff check src tests worker lambda`
- [ ] I ran `uv run mypy src worker lambda`

## Checklist

- [ ] I read [CONTRIBUTING.md](../../blob/main/CONTRIBUTING.md)
- [ ] I branched off `main` and rebased onto it before opening
- [ ] The diff is focused — one concern per PR
- [ ] New commands live under `src/wactl/commands/` and are registered
      in `src/wactl/commands/__init__.py`
- [ ] New commands do **not** import `httpx`, `boto3`, or the WhatsApp
      API directly — they go through `CommandContext`
- [ ] New commands have unit tests with happy-path + error-path coverage
- [ ] I updated [docs/SETUP.md](../../blob/main/docs/SETUP.md),
      [docs/CODEBASE_GUIDE.md](../../blob/main/docs/CODEBASE_GUIDE.md),
      or [docs/DECISIONS.md](../../blob/main/docs/DECISIONS.md) if the
      change is user-facing or architectural
- [ ] I added a `CHANGELOG.md` entry under `[Unreleased]`

## Screenshots / logs

<!-- If your PR changes UI behaviour or log output, paste before/after.
     Redact secrets before pasting anything from production logs. -->

<!-- ──────────────────────────────────────────────────────────────
     Reviewer note (delete before submitting):

     We review for: production-readiness (retries, idempotency,
     logging), adherence to the plugin architecture, error-path test
     coverage, and whether the change fits the ADRs in docs/DECISIONS.md.
     ────────────────────────────────────────────────────────────── -->
