# Security policy

## Supported versions

WACTL is a portfolio project maintained on a best-effort basis. The
following table lists which versions receive security updates.

| Version | Supported          |
|---------|--------------------|
| `main`  | ✅ active development |
| tagged releases | 🟡 best-effort, 90 days after release |

There are no "LTS" branches — `main` is the supported line.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security bugs.**

Email **security@wactl.example** with:

- A description of the vulnerability
- A proof-of-concept (logs, screenshots, or a minimal reproducer)
- The commit SHA / release affected

You'll get an acknowledgement within **3 business days**. A fix (or a
decision not to fix) follows within **30 days**. Critical issues are
triaged faster.

## Scope

The following are **in scope**:

- Anything that lets a third party read / write / delete data they
  shouldn't have access to.
- Anything that lets a third party execute code on the Lambda, the
  worker, or in the user's browser.
- Anything that bypasses HMAC signature verification, the dedup table,
  or the command registry.
- Secrets leaked in logs, Terraform state, or the GitHub Actions OIDC
  trust policy.

The following are **out of scope**:

- Denial-of-service against the WhatsApp Cloud API itself (Meta's
  problem, not ours).
- Theoretical attacks against pdf2docx / pymupdf / Pillow — please
  report upstream.
- Spam sent via the bot by an authenticated user (rate-limit, don't
  file a CVE).

## Hardening notes (for operators)

The Terraform in `infra/` already implements:

- HMAC signature verification on every webhook (rejects unsigned /
  forged requests).
- DynamoDB TTL-based dedup (prevents webhook replay storms).
- Least-privilege IAM for Lambda, worker, and GitHub Actions roles.
- Secrets stored in AWS Secrets Manager, never in env vars or source.
- S3 media bucket has public access blocked + 24h lifecycle.
- OIDC trust policy restricted to the `sathya-narayanan/wactl`
  repository + `main` branch.

When you fork or copy this project, **review the OIDC trust policy**
and the `repo:` condition in [infra/iam.tf](infra/iam.tf).

## Coordinated disclosure

We follow a 90-day coordinated disclosure window. If we haven't
responded within that window, feel free to disclose publicly — but
please give us a heads-up first.