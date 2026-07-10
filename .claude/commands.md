---
name: commands
description: Recipes for adding a new command, a new integration, and a new Terraform resource in WACTL
metadata:
  type: reference
---

# Adding things to WACTL

## Add a new command (the canonical recipe)

1. **Pick a name + decide sync/async.**
   - `/<kebab-name>`. Sync if p99 <10s and total payload <25 MB.
   - Sync examples: `/image-resize`, `/translate`.
   - Async examples: `/pdf-docx`, `/pdf-audio`.

2. **Identify integrations you need.** If you need a new one, see below.
   Otherwise just import from `wactl.integrations.<area>.<thing>`.

3. **Write `src/wactl/commands/<name>.py`:**

   ```python
   """<one-line description>."""

   from wactl.commands.base import Command, CommandContext
   from wactl.commands.registry import register
   from wactl.models.command import CommandResponse

   @register("/<name>", sync=True, requires_media=False)
   class FooCommand(Command):
       """<docstring>."""

       async def run(self, ctx: CommandContext) -> CommandResponse:
           # Call integrations only — no httpx, no boto3.
           result = await ctx.integrations.whatsapp.send_text(
               to=ctx.user.phone,
               body="Done!",
           )
           return CommandResponse(success=True, message_id=result.message_id)
   ```

4. **Register the import** in `src/wactl/commands/__init__.py` so the
   `@register` decorator runs at package import time:

   ```python
   from wactl.commands import foo  # noqa: F401 — registers the command
   ```

5. **Add a test** at `tests/unit/test_<name>.py` that mocks every
   integration the command calls and asserts the integration call order
   + payload.

6. **(If user-facing) Document it** in `docs/SETUP.md` and
   `docs/CODEBASE_GUIDE.md`.

7. **Update `.claude/commands.md` § "Active commands"** with the new name.

## Add a new integration

1. **Pick the provider folder.** If it's a new provider, create a new
   sub-folder under `src/wactl/integrations/`.

2. **Write `src/wactl/integrations/<area>/<thing>.py`:**

   ```python
   """<One-line summary>."""

   from __future__ import annotations

   import httpx

   async def fetch(client: httpx.AsyncClient, url: str) -> bytes:
       resp = await client.get(url, timeout=30.0)
       resp.raise_for_status()
       return resp.content
   ```

   - Take `httpx.AsyncClient` as a parameter (testable; injected).
   - Return typed values; raise typed exceptions (`WactlError` subclasses).
   - Never block; if CPU-bound, accept that and let the caller wrap it
     in `asyncio.to_thread(...)`.

3. **Add a unit test** at `tests/unit/test_<thing>.py`. Use `respx` for
   HTTP, `moto` for AWS.

4. **Re-export** in `src/wactl/integrations/<area>/__init__.py` if it's a
   "public" function of that area.

5. **Document** in `docs/CODEBASE_GUIDE.md`.

## Add a new Terraform resource

1. **Choose the right `.tf` file** by concern (sqs.tf, lambda.tf, ec2.tf,
   iam.tf, etc.). If it's a new concern, add a new file and reference it
   in `infra/README.md`.

2. **Add the resource** with at least:
   - `tags = local.common_tags` for cost allocation.
   - Naming suffix `local.name_suffix` (= env) so dev/prod don't clash.
   - IAM scopes resource ARNs, never `"*"`.

3. **Add outputs** for anything other modules should reference (use
   `outputs.tf`).

4. **Add variables** to `variables.tf` for anything a caller might
   override (region, env, instance type, etc.).

5. **Document the resource** in `infra/README.md`.

## Active commands

| Name           | Sync | File                                |
| -------------- | ---- | ----------------------------------- |
| `/pdf-docx`    | ❌   | `src/wactl/commands/pdf_docx.py`    |
| `/pdf-audio`   | ❌   | `src/wactl/commands/pdf_audio.py`   |
| `/merge-pdf`   | ❌   | `src/wactl/commands/merge_pdf.py`   |
| `/split-pdf`   | ❌   | `src/wactl/commands/split_pdf.py`   |
| `/image-resize`| ✅   | `src/wactl/commands/image_resize.py`|
| `/image-compress`| ✅ | `src/wactl/commands/image_compress.py` |
| `/web-summary` | ✅   | `src/wactl/commands/web_summary.py` |
| `/github-pr`   | ✅   | `src/wactl/commands/github_pr.py`   |
| `/translate`   | ✅   | `src/wactl/commands/translate.py`   |

Add new commands to this table when you ship them.

---

Related: [[architecture]], [[conventions]], [[repo-structure]]