---
name: wactl-test-mock-patterns
description: How command unit tests patch integrations — monkeypatch the integration module's function, not the command's imported reference
metadata:
  type: reference
---

When writing command unit tests in `tests/unit/test_command_<name>.py`:

- DO monkeypatch at the **integration module path**, e.g.
  - `wactl.integrations.whatsapp.messages.send_document`
  - `wactl.integrations.converters.pdf_docx.pdf_to_docx`
  - `wactl.integrations.gemini.text.translate`
  - `wactl.integrations.github.pr_summary.fetch_pr`
- DON'T set attributes on the `fake_whatsapp` mock
  (`fake_whatsapp.send_document = AsyncMock(side_effect=...)` does not work —
  MagicMock caches the original AsyncMock from the fixture and returns it
  forever, ignoring the override).
- For S3 helpers used inside commands (`s3.put_object`, `s3.presigned_get_url`),
  monkeypatch at the command module path: `wactl.commands.<cmd>.s3.put_object`.
- For jobs helpers requiring secrets (e.g. `wactl.integrations.aws.secrets.get_secret`),
  monkeypatch the integration module path: `wactl.integrations.aws.secrets.get_secret`.

The shared `fake_whatsapp` fixture in `tests/unit/conftest_helpers.py` only
provides the low-level `post_json`/`get_bytes` surface; each test patches the
higher-level wrappers in `wactl.integrations.*` directly with monkeypatch.

**Why:** Python resolves imports once at module load. The command holds a
local name that points at the same function object as the integration
module, so `monkeypatch.setattr(integration_module, name, fake)` works,
but `cmd.fake_whatsapp.send_document = ...` only changes the attribute on
the mock, not the function the command actually calls.

Related: [[wactl-conventions]]
