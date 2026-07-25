# Contributing

## Setup

```bash
uv sync
cp .env.example .env
uv run pytest
```

## Branches, commits, PRs

- Branch off `main` as `feat/<name>` or `fix/<name>`.
- Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`).
- PRs against `main`. CI runs ruff, mypy (strict), and pytest.

## Adding a command

A command is one file, one decorator, one test:

1. `src/wactl/commands/<name>.py` subclassing `Command` from `base.py`.
2. Register with `@register`.
3. Test in `tests/` using `CommandContext` with fake clients.
4. Open a PR. New AWS resources go in `infra/` in the same PR.
