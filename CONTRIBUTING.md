# Contributing to WACTL

Thanks for your interest in WACTL. The project is a portfolio piece but
the codebase is structured to be extensible — please read this before
opening a PR.

---

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By
participating you agree to its terms.

---

## Development setup

### Prerequisites

- Python 3.12 (matches `.python-version`)
- [`uv`](https://github.com/astral-sh/uv) — package manager
- Node 20+ — only for the frontend (`web/`)
- Terraform 1.10+ — only if you're touching `infra/`

### Bootstrap

```bash
git clone https://github.com/sathya-narayanan/wactl
cd wactl
uv sync                 # Python deps + virtualenv
cd web && npm install   # frontend deps
```

### Running tests

```bash
uv run pytest tests -q         # all tests, no AWS needed
uv run pytest tests/unit -q    # unit tests only
uv run pytest tests/integration -q  # end-to-end tests
```

The full suite runs in ~10 s and uses **no AWS credentials**.

### Lint + type-check

```bash
uv run ruff check src tests worker lambda
uv run mypy src worker lambda
```

Both must pass before opening a PR.

---

## Project structure

See [docs/CODEBASE_GUIDE.md](docs/CODEBASE_GUIDE.md) for the full tour.
The short version:

- `src/wactl/` — shared Python package (Lambda + worker)
- `lambda/` — thin Lambda entry points
- `worker/` — EC2 long-poll process
- `infra/` — Terraform
- `web/` — Next.js 16 frontend
- `tests/` — unit + integration
- `docs/` — SETUP + CODEBASE_GUIDE + this directory

---

## Adding a new command

The plugin architecture is the whole point of this codebase — please
follow it. The recipe:

1. Pick a name (`/your-command`) and decide `sync=True` or `sync=False`.
2. Create `src/wactl/commands/your_command.py`:

   ```python
   from wactl.commands.base import Command, CommandContext
   from wactl.commands.registry import register
   from wactl.models.command import CommandResponse

   @register("/your-command", sync=True, description="...")
   class YourCommand(Command):
       async def run(self, ctx: CommandContext) -> CommandResponse:
           # Use ctx.whatsapp / ctx.s3 / ctx.gemini / etc.
           return CommandResponse(success=True)
   ```

3. Register the module in `src/wactl/commands/__init__.py`.
4. Add `tests/unit/test_command_your_command.py` that mocks every
   integration the command uses. **Commands MUST NOT import httpx,
   boto3, or call the WhatsApp API directly** — go through the
   `ctx.*` dependencies.
5. Update `web/lib/site.ts` (`COMMANDS` array) so it appears in the docs
   page.

No router, dispatcher, or Terraform changes are needed.

---

## Adding a new integration

Pick the right sub-package (`aws/`, `whatsapp/`, `converters/`,
`gemini/`, `github/`) and keep files small (<200 lines). Wire it into
`WebhookDeps` in [src/wactl/webhook.py](src/wactl/webhook.py). Tests
should use `respx` to mock HTTP, or `moto` for AWS.

---

## Pull request process

1. **Branch off `main`.** Use a descriptive branch name
   (`feat/audiobook-v2`, `fix/webhook-timeout`, etc.).
2. **Keep the diff focused.** One PR = one concern. If you're fixing a
   bug and want to refactor something adjacent, do it in a separate PR.
3. **Tests are required.** Bug fixes need a regression test; new
   commands need at least happy-path + one error-path test.
4. **Lint and mypy must pass.** CI runs both.
5. **Update docs if user-facing.** If your change adds a command,
   touches an env var, or alters the deployment steps, update
   [docs/SETUP.md](docs/SETUP.md) and / or
   [docs/CODEBASE_GUIDE.md](docs/CODEBASE_GUIDE.md).
6. **No AI co-author trailers.** Maintain the project's git hygiene.
7. **Fill out the PR template.** Reviewers will use it as a checklist.

Reviewers will look for:

- Adherence to existing conventions (see [`.claude/conventions.md`](.claude/conventions.md))
- Test coverage of error paths, not just happy paths
- Production concerns: retries, idempotency, logging, observability
- Whether the change matches the architectural intent in
  [docs/CODEBASE_GUIDE.md §5](docs/CODEBASE_GUIDE.md#5-design-decisions)

---

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
Include:

- WACTL version / commit SHA
- Python version (`python --version`)
- The exact command you ran
- Expected vs actual behavior
- Relevant log lines (with secrets redacted)

---

## Suggesting features

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).
For large changes, please open an issue first to discuss before sending
a PR — saves everyone time.

---

## License

By contributing, you agree that your contributions will be licensed
under the project's [MIT License](LICENSE).