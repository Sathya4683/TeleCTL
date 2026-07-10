# GitHub Actions OIDC bootstrap

The GitHub Actions deploy workflow authenticates to AWS via OIDC — there
are **no long-lived AWS access keys** in the repo. The Terraform in
`infra/iam.tf` provisions:

- An `aws_iam_openid_connect_provider.github` resource pointed at
  `https://token.actions.githubusercontent.com`.
- An `aws_iam_role.github_actions` whose trust policy restricts the
  `sub` claim to a single repo/branch:
  `repo:sathya-narayanan/wactl:ref:refs/heads/main`.

## Repository secret

After the first `terraform apply`, configure **one** repository secret:

| Name              | Value                                                        |
|-------------------|--------------------------------------------------------------|
| `AWS_ACCOUNT_ID`  | Your 12-digit AWS account id (used to assemble role ARNs).  |

No `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` are needed — OIDC issues
short-lived STS credentials per workflow run.

## One-time manual steps

If you're standing up a brand-new account:

1. Bootstrap the S3 state bucket (see `infra/README.md`).
2. Apply Terraform with an admin credential (locally):
   ```bash
   cd infra
   terraform init \
     -backend-config="bucket=wactl-tf-state-$AWS_ACCOUNT_ID" \
     -backend-config="region=us-east-1"
   terraform apply -var env=dev -auto-approve
   ```
3. Set `AWS_ACCOUNT_ID` in the repo's *Settings → Secrets → Actions*.
4. Push to `main` — the deploy workflow will run end-to-end.

The OIDC thumbprint in `infra/iam.tf` is the canonical one for GitHub's
production token service. AWS automatically rotates this for
`token.actions.githubusercontent.com`, so it does **not** require manual
maintenance.
