# Vercel deployment setup

The frontend (Next.js in [`web/`](../../web/)) deploys to Vercel via
[`.github/workflows/deploy-frontend.yaml`](workflows/deploy-frontend.yaml).
This doc covers the one-time setup.

## 1. Create a Vercel account

Sign up at https://vercel.com — the hobby (free) tier is enough for
WACTL's traffic.

## 2. Create a token

1. Go to https://vercel.com/account/tokens
2. Click **Create Token**
3. Name it `wactl-gha-deploy`
4. Scope: whatever scope covers the project (usually full account is
   fine for a personal project)
5. Copy the token — you'll only see it once

## 3. Link the project (gets the IDs)

Run this on your dev machine, inside the repo:

```bash
cd web
npm install -g vercel          # if you don't have it
vercel login
vercel link                    # creates web/.vercel/project.json
```

`vercel link` will ask:

- **Scope**: your account (or a team you own)
- **Which project**: **Link to existing project** if you already created
  one in the Vercel dashboard, OR **Create new project** with the name
  `wactl-web` (or whatever you want the URL prefix to be)

After linking, `cat web/.vercel/project.json` shows:

```json
{
  "orgId": "team_xxxxxxxxxxxxx",
  "projectId": "prj_xxxxxxxxxxxxx"
}
```

**Add a `.vercel/` entry to `.gitignore`** — never commit this file, it
contains project-local metadata.

## 4. Configure the project settings in Vercel

In the Vercel dashboard, under the project:

- **Root Directory**: `web`  ← important, otherwise Vercel builds from
  repo root and fails on `pyproject.toml`.
- **Build Command**: `next build` (default — leave it)
- **Install Command**: `npm install` (default)
- **Output Directory**: `.next` (default)
- **Node Version**: 20

Set an environment variable if you want a non-default `wa.me` link:

| Key                    | Value                                  |
|------------------------|----------------------------------------|
| `NEXT_PUBLIC_WA_ME_LINK` | `https://wa.me/<your-number>?text=%2Fhelp` |

## 5. Add GitHub secrets

In your GitHub repo → **Settings → Secrets and variables → Actions**,
add three secrets:

| Secret name          | Value                                |
|----------------------|--------------------------------------|
| `VERCEL_TOKEN`       | the token from step 2                |
| `VERCEL_ORG_ID`      | the `orgId` from step 3              |
| `VERCEL_PROJECT_ID`  | the `projectId` from step 3          |

(If the project is in a team, also add `VERCEL_TEAM_SLUG` = your team
slug.)

## 6. Test it

Two ways:

**Manual** — on the GitHub repo, go to **Actions → Deploy frontend →
Run workflow**. This triggers a production deploy.

**Automatic** — push a commit that touches anything under `web/`:

```bash
echo "// touch" >> web/lib/site.ts
git add . && git commit -m "ci: trigger frontend deploy"
git push origin feat/creationV1   # → opens a PR
```

PRs get a preview URL commented automatically. Merging the PR to `main`
triggers the production deploy.

## Optional: skip the GitHub Actions route

If you'd rather use Vercel's native GitHub integration:

1. In the Vercel dashboard → **Settings → Git → Connect Git Repo**
2. Point it at `sathya-narayanan/wactl`, set root to `web/`.
3. Every push to `main` deploys automatically — no secrets needed.

In that case you can delete
[`.github/workflows/deploy-frontend.yaml`](workflows/deploy-frontend.yaml)
and the Vercel secrets. The two setups are mutually exclusive.

## Cost

Vercel hobby tier:

- 100 GB-seconds of build minutes / month
- 100 GB of bandwidth / month
- Unlimited preview deployments

For a static-ish Next.js app with ≤15 users, **you stay in the free
tier indefinitely.**