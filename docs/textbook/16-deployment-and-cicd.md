# 16 — Deployment and CI/CD

Three GitHub Actions workflows handle CI, the backend deploy, and the frontend deploy. This chapter walks through each, explains the OIDC pattern that powers deploys, and shows the full code-to-production flow.

## 16.1 — The three workflows

```
.github/workflows/
├── ci.yaml                # lint + mypy + pytest on PR/push
├── deploy.yaml            # build + upload + terraform apply on push to main
└── deploy-frontend.yaml   # Vercel deploy on web/** changes
```

Each workflow has a single responsibility:

- **`ci.yaml`** runs on every PR and every push to `main`. It validates the code (lint, types, tests) but doesn't deploy.
- **`deploy.yaml`** runs on push to `main` (or manual trigger). It builds the artifacts (Lambda zip, worker tarball), uploads them to S3, and applies Terraform.
- **`deploy-frontend.yaml`** runs on changes to `web/**`. It builds the Next.js site and deploys to Vercel.

## 16.2 — CI: the safety net

`ci.yaml` is short and runs on every PR:

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        run: pip install --upgrade pip uv

      - name: Sync deps
        run: uv sync --frozen

      - name: Lint (ruff)
        run: uv run ruff check src tests worker lambda

      - name: Type-check (mypy)
        run: uv run mypy src worker lambda

      - name: Unit tests
        run: uv run pytest tests -q --maxfail=1
```

Six steps:

1. **Checkout** the code.
2. **Set up Python 3.12** — GitHub's hosted runner has system Python; this action installs a specific version in the path.
3. **Install uv** — the modern pip replacement.
4. **Sync deps** with `uv sync --frozen` (uses the lockfile, doesn't update it).
5. **Lint** with ruff.
6. **Type-check** with mypy.
7. **Test** with pytest.

`--maxfail=1` stops at the first failure (faster feedback). The full suite runs in ~10 seconds locally; CI is similar (slightly slower because of runner cold-start).

The `concurrency` block ensures that a new push to a PR cancels the previous run — you don't waste CI minutes on a stale run.

`permissions: contents: read` is the most restrictive GitHub token scope. We don't need write access for CI.

## 16.3 — Deploy: the full pipeline

`deploy.yaml` is the "ship to production" workflow. It runs on push to `main` (auto-deploy) or `workflow_dispatch` (manual run with env choice):

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      env:
        description: "Deployment environment"
        required: true
        default: dev
        type: choice
        options:
          - dev
          - staging
          - prod
```

The `inputs.env` lets you trigger a deploy to a specific env from the GitHub UI. By default, push to `main` deploys to `dev`.

```yaml
concurrency:
  group: deploy-${{ github.event.inputs.env || 'dev' }}
  cancel-in-progress: false
```

`cancel-in-progress: false` is important: we *don't* want to cancel a half-finished deploy. A new commit waits for the old one to finish.

```yaml
permissions:
  id-token: write
  contents: read
```

`id-token: write` is the OIDC scope. The next section explains why we need it.

### The two jobs

The workflow has two jobs:

**`build-and-publish`** — builds the Lambda zip and worker tarball, uploads to S3.

```yaml
- name: Build Lambda zip
  run: |
    set -euo pipefail
    rm -rf build/lambda packages
    mkdir -p build/lambda
    uv export --frozen --no-hashes --format requirements-txt > /tmp/requirements.txt
    uv pip install \
      --python "$(which python)" \
      --target build/lambda/packages \
      --no-cache --no-compile-bytecode \
      -r /tmp/requirements.txt
    cp -r src/wactl build/lambda/packages/wactl
    (cd build/lambda/packages && zip -qr ../../lambda.zip .)
    (cd build/lambda && zip -qr ../lambda.zip lambda)
    echo "Built $(ls -lh build/lambda.zip)"
```

The Lambda zip is built by:
1. Exporting the locked deps to requirements.txt.
2. Installing them into `build/lambda/packages/` (a target directory, not a venv).
3. Copying our package `src/wactl` on top.
4. Zipping the whole thing.

The zip structure mirrors what Lambda expects at runtime:

```text
lambda.zip
└── packages/
│   ├── wactl/        # our code
│   ├── boto3/        # dep
│   ├── httpx/        # dep
│   └── ... (every dep)
└── lambda/
    └── webhook/
        └── handler.py  # the entry point
```

Lambda's handler is `lambda.webhook.handler.lambda_handler` (set in `lambda.tf`). Lambda unpacks the zip to `/var/task/` and runs the handler with the standard Python import path.

```yaml
- name: Build worker tarball
  run: bash worker/build.sh
```

The worker build runs the Docker-based build (chapter 08). It produces `dist/worker.tar.gz` and `dist/worker.tar.gz.sha256`.

```yaml
- name: Configure AWS credentials (OIDC)
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/${{ github.event.inputs.env || 'dev' }}-gha-deploy
    aws-region: us-east-1
```

The OIDC step. The action assumes an IAM role using the OIDC token issued by GitHub. The role is the one we set up in `infra/iam.tf` (the `gha-deploy` role).

```yaml
- name: Upload Lambda zip to S3
  run: |
    aws s3 cp build/lambda.zip \
      s3://${{ github.event.inputs.env || 'dev' }}-releases-${{ secrets.AWS_ACCOUNT_ID }}/lambda.zip

- name: Upload worker tarball to S3
  run: |
    aws s3 cp dist/worker.tar.gz \
      s3://${{ github.event.inputs.env || 'dev' }}-releases-${{ secrets.AWS_ACCOUNT_ID }}/worker.tar.gz
```

Both artifacts are uploaded to the releases bucket. The Lambda and the worker will pick them up.

**`terraform-apply`** — runs `terraform init` and `terraform apply`.

```yaml
needs: build-and-publish
```

This job depends on `build-and-publish` finishing first. The two jobs run in sequence.

```yaml
- name: Setup Terraform
  uses: hashicorp/setup-terraform@v3
  with:
    terraform_version: 1.10.0
```

Installs the right Terraform version.

```yaml
- name: terraform init
  working-directory: infra
  run: |
    terraform init \
      -backend-config="bucket=wactl-tf-state-${{ secrets.AWS_ACCOUNT_ID }}" \
      -backend-config="region=us-east-1"

- name: terraform apply
  working-directory: infra
  run: |
    terraform apply \
      -var env=${{ github.event.inputs.env || 'dev' }} \
      -auto-approve
```

The init reads the state from S3 (with the lockfile for safety). The apply pushes the diff — no changes if the plan is empty.

`-auto-approve` skips the "are you sure?" prompt. We trust the CI pipeline to only run on reviewed PRs.

## 16.4 — OIDC: short-lived credentials for CI

The deploy job doesn't use AWS access keys. It uses **OpenID Connect** to assume an IAM role.

### The traditional problem

The old way to give CI access to AWS:

1. Create an IAM user.
2. Generate an access key (long-lived secret).
3. Store the access key in GitHub secrets.
4. The CI workflow uses the access key to call AWS.

Problems:

- The access key is a long-lived secret. If GitHub is compromised, the key is in the secrets store.
- The key has whatever permissions the IAM user has, forever.
- Rotation is manual.
- The key is visible in the GitHub Actions logs (potentially).

### The OIDC solution

With OIDC:

1. AWS is configured to trust GitHub's OIDC provider.
2. Each CI run, GitHub issues a JWT signed by its OIDC provider.
3. The JWT is presented to AWS STS (`AssumeRoleWithWebIdentity`).
4. AWS validates the JWT, checks the `sub` claim (e.g. `repo:sathya-narayanan/wactl:ref:refs/heads/main`), and issues short-lived STS credentials.
5. The CI uses those credentials; they expire in 1 hour.

The trust policy in `infra/iam.tf`:

```hcl
data "aws_iam_policy_document" "gha_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:sathya-narayanan/wactl:ref:refs/heads/main"]
    }
  }
}
```

The `sub` condition restricts the role to: only from the `sathya-narayanan/wactl` repo, only from the `main` branch. A PR from a fork has a different `sub` (it includes `:pull_request` and `:refs/pull/N/merge`); it's rejected by the condition.

The result: no long-lived AWS credentials anywhere. The CI assumes a role with scoped permissions for an hour; the credentials expire.

### Why we trust it

The threat model: if a malicious PR comes in, it can run CI but can't assume the deploy role (different `sub`). The deploy only runs on `push to main` after the PR is merged; at that point, the code is reviewed and approved.

The remaining risk: a compromised GitHub repo could push a commit to `main` (e.g. via a hijacked maintainer account). The deploy would run. The IAM role's permissions are scoped to specific actions on specific resources, so the blast radius is bounded.

## 16.5 — The deploy flow, end to end

```text
PR merged to main
   │
   ▼
deploy.yaml triggers (build-and-publish job)
   │
   ├─ uv sync (install deps)
   ├─ Build Lambda zip (uv pip install --target build/lambda/packages + cp + zip)
   ├─ Build worker tarball (worker/build.sh → Docker)
   ├─ Configure AWS credentials (OIDC: assume gha-deploy role)
   ├─ aws s3 cp build/lambda.zip s3://...releases/lambda.zip
   └─ aws s3 cp dist/worker.tar.gz s3://...releases/worker.tar.gz
   │
   ▼
deploy.yaml triggers (terraform-apply job)
   │
   ├─ terraform init (read state from S3)
   ├─ terraform apply -auto-approve
   │     │
   │     ├─ aws_lambda_function.webhook: source_code_hash changes → forces redeploy
   │     │     (Lambda downloads the new zip, runs the new handler)
   │     │
   │     └─ (other resources unchanged unless modified)
   │
   ▼
End-to-end deploy complete
```

The Lambda redeploy is "magic" in a good way: the `source_code_hash` attribute changes when the zip changes, and Terraform automatically calls `UpdateFunctionCode` to push the new code. No separate step.

The worker, by contrast, requires an **instance refresh** to pick up the new tarball. New instances download the new code on boot; old instances keep running the old code until they're replaced. The ASG has `min_size = 1, max_size = 2`, so an instance refresh launches a new instance, waits for it to be healthy, then terminates the old one.

For a more aggressive refresh, you can add a step to the deploy workflow that calls `aws autoscaling start-instance-refresh` after the S3 upload. We don't currently do this; manual refresh is fine for personal scale.

## 16.6 — Frontend deploy: Vercel

`deploy-frontend.yaml` is similar but for the Next.js site:

```yaml
on:
  push:
    branches: [main]
    paths:
      - "web/**"
      - ".github/workflows/deploy-frontend.yaml"
  pull_request:
    paths:
      - "web/**"
  workflow_dispatch:
```

Triggers on changes to `web/**` or the workflow file. PRs get a preview deploy; main gets a production deploy.

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment:
      name: ${{ github.event_name == 'pull_request' && 'preview' || 'production' }}
      url: ${{ steps.deploy.outputs.preview-url }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: web/package-lock.json

      - name: Install frontend deps
        run: npm ci

      - name: Lint + type-check
        run: npm run lint

      - name: Build
        run: npm run build
        env:
          NEXT_TELEMETRY_DISABLED: 1

      - name: Deploy to Vercel
        id: deploy
        uses: amondnet/vercel-action@v25
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
          vercel-args: ${{ github.event_name == 'pull_request' && '--yes' || '--prod --yes' }}
          working-directory: web
```

The Vercel action:

1. Runs `npm ci` (clean install from lockfile).
2. Runs `npm run lint` (catches lint errors before deploy).
3. Runs `npm run build` (catches build errors before deploy).
4. Calls the Vercel API to deploy.

The `vercel-args` is conditional: PRs get a preview deploy (`--yes`), main gets a production deploy (`--prod --yes`). The `id: deploy` and `outputs.preview-url` capture the deployed URL.

```yaml
- name: Comment preview URL on PR
  if: github.event_name == 'pull_request'
  uses: marocchino/sticky-pull-request-comment@v2
  with:
    header: vercel-preview
    message: |
      ✅ Vercel preview deployed.

      **URL:** ${{ steps.deploy.outputs.preview-url }}
```

The `sticky-pull-request-comment` action adds (or updates) a comment on the PR with the preview URL. "Sticky" means subsequent runs update the existing comment rather than adding a new one.

The `permissions: pull-requests: write` allows the bot to write the comment.

## 16.7 — The Vercel secrets

The deploy needs three secrets (configured in GitHub repo settings):

- **`VERCEL_TOKEN`** — an API token from <https://vercel.com/account/tokens>. Treat it like any long-lived secret.
- **`VERCEL_ORG_ID`** — your Vercel org id (or user id for personal accounts).
- **`VERCEL_PROJECT_ID`** — the project's id in Vercel.

Run `vercel link` in `web/` to populate `.vercel/project.json`, which has these IDs.

These are stored in GitHub secrets, not in the code. If they leak, you can rotate them from the Vercel dashboard without changing the code.

## 16.8 — Manual deploys

Both backend and frontend can be triggered manually:

- **Backend:** GitHub → Actions → "Deploy" → "Run workflow" → pick the env. Useful for promoting a tested change to staging or prod.
- **Frontend:** GitHub → Actions → "Deploy frontend" → "Run workflow". Rarely needed; the auto-deploy covers most cases.

The env choice (`dev` / `staging` / `prod`) is passed via the workflow's `inputs.env`. The Terraform apply then runs with `-var env=...` so the resources are namespaced correctly.

## 16.9 — What we don't do

A few common CI/CD features we deliberately skip:

- **No blue/green deploys.** Lambda is already "blue/green" — it shifts traffic to new versions automatically. The worker is single-instance; refreshes are good enough.
- **No canary deploys.** For personal scale, the cost of a canary is high (need 2 ASGs, traffic splitting). We accept the risk of a bad deploy.
- **No rollback automation.** If a deploy is bad, the fix is to push a revert commit. The deploy workflow will pick it up and deploy the fix.
- **No deployment notifications.** The CloudWatch alarms (chapter 17) tell us if something is wrong; we don't need a Slack message saying "deployed."
- **No PR preview environments for the backend.** Vercel gives us preview deploys for the frontend; the backend is shared infrastructure and previews would require per-PR AWS accounts.

Each of these is a deliberate simplification. For a production system with paying users, we'd add them in priority order: notifications → rollback → canary.

## 16.10 — Common issues

### "The OIDC assume-role failed"

The role trust policy doesn't allow the repo/branch. Check `infra/iam.tf`:

```hcl
values   = ["repo:sathya-narayanan/wactl:ref:refs/heads/main"]
```

If you forked the repo, change the values to your own.

### "terraform init: backend reinitialization required"

The state file is in a different region or bucket. Check `infra/backend.tf` and the `terraform init` step in the workflow.

### "Lambda is using the old code"

The deploy didn't include the latest changes. Check the GitHub Actions log for the deploy that corresponds to your commit. If the deploy didn't run, check the workflow triggers.

The Lambda also has a 5-minute cache for SSM parameter fetches. If you rotated a secret, wait 5 minutes for the new value to be picked up.

### "Worker is using the old code"

The ASG is running an instance that was launched before the latest deploy. Trigger an instance refresh:

```bash
aws autoscaling start-instance-refresh \
  --auto-scaling-group-name wactl-dev-worker \
  --strategy Rolling
```

Or just terminate the instance manually and let ASG launch a new one.

## 16.11 — The deployment contract

What the system promises:

- **Every push to `main` is deployable.** CI must pass before merge; the deploy workflow runs on every push to `main`.
- **Deploys are atomic at the Lambda level.** `UpdateFunctionCode` is a single API call; either it succeeds or it doesn't.
- **Deploys don't drop in-flight jobs.** The worker's SQS visibility timeout means a job in flight is re-delivered if the worker is replaced mid-job.
- **Deploys can be reverted by reverting the commit.** No special tooling needed; just push the revert.

What's not promised:

- **Zero-downtime worker deploys.** During an instance refresh, there's a brief window where the old instance is being terminated and the new one is starting. The SQS visibility timeout makes this safe (in-flight jobs are re-queued) but not instant.
- **Rollback within seconds.** A bad Lambda deploy takes ~30 seconds to roll back (the new code is replaced). A bad worker deploy takes 1-2 minutes (instance launch time).

For a personal-scale system, these trade-offs are fine. For production-scale, you'd add automated rollback on alarm.

## Next

→ [`17-observability.md`](17-observability.md) — structured logging, CloudWatch, and the alarms that page you.
