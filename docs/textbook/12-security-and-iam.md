# 12 — Security and IAM

Security in a WhatsApp-integration platform is non-negotiable: the system has access to your users' phone numbers, can send messages on their behalf, and reads their attachments. This chapter covers the threat model, what we do about it, and what we explicitly do *not* do.

## 12.1 — The threat model

WACTL handles these categories of sensitive data:

| Data | Where it lives | Who can see it |
|---|---|---|
| User phone numbers | In webhook payloads (transient), in CommandContext. | Lambda + worker (and their CloudWatch logs). |
| User names | In webhook payloads. | Same as above. |
| Inbound attachments | WhatsApp servers (5-min URL); S3 media bucket (1-day lifecycle). | Lambda + worker. |
| Outbound artifacts | S3 media bucket (1-day lifecycle). | Same as above. |
| WhatsApp access token | SSM Parameter Store. | Lambda + worker IAM. |
| WhatsApp app secret (HMAC key) | SSM Parameter Store. | Lambda + worker IAM. |
| Gemini API key | SSM Parameter Store. | Lambda + worker IAM. |

The threats to defend against:

1. **An attacker sending fake webhooks** — POSTing to our API Gateway URL with someone else's wamid, triggering commands as a different user.
2. **An attacker reading webhook payloads** — capturing traffic between Meta and us.
3. **An attacker using our credentials** — stealing the access token and sending messages from our bot.
4. **An attacker using our S3 bucket** — uploading malicious files or downloading other users' files.
5. **An attacker using our SQS queue** — injecting fake jobs.
6. **An attacker compromising the worker** — RCE via a malicious PDF (most likely path).
7. **A supply-chain attack** — a compromised dep in `pyproject.toml` adding a backdoor.

The defenses, in order of importance:

## 12.2 — HMAC verification: rejecting fake webhooks

The first line of defense. Every inbound POST must have a valid `X-Hub-Signature-256` header. Without it, the request is dropped (with a 200 status so the attacker learns nothing).

Already covered in detail in chapter 06. To summarize:

```python
def verify_signature(raw_body, signature_header, app_secret) -> None:
    if not signature_header or not signature_header.startswith("sha256="):
        raise SignatureVerificationError(...)
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header[len("sha256="):].strip()
    if not hmac.compare_digest(expected, provided):
        raise SignatureVerificationError(...)
```

Why this is robust:

- **The secret never leaves Meta's servers or our SSM.** It exists only in the X-Hub-Signature-256 computation; we never log it or write it to a file.
- **Constant-time comparison** prevents timing attacks.
- **Raw body verification** prevents the "re-parse and compare" class of attacks.
- **The Meta side is also doing the same.** They sign with the same shared secret.

What's not robust:

- **Replay attacks within the 5-minute window.** An attacker who captures a valid webhook payload can re-send it; the signature is still valid. The dedup table (chapter 09) catches this: the wamid is already in the table, so the second copy is dropped.
- **An attacker who steals the app secret.** We rely on SSM access control to keep the secret safe. See section 12.4.

## 12.3 — TLS: rejecting in-flight eavesdroppers

API Gateway provides a TLS endpoint by default. Every webhook from Meta to our `/webhook` URL is HTTPS; a passive eavesdropper sees encrypted bytes.

The certificate is an Amazon-issued cert (no custom domain). For a custom domain (`webhook.example.com`), you'd attach an ACM cert to the API Gateway domain — that's the `var.domain` input in Terraform (currently empty).

What TLS does *not* protect:

- **The application layer.** If a packet reaches the Lambda, the JSON is decrypted and processed. So the threat model assumes the Lambda is trusted; if the EC2 worker is compromised, all bets are off.
- **Logs.** If you log the request body, the body is now in CloudWatch. CloudWatch logs are encrypted at rest, but a human with read access can see the body. We don't log request bodies.

## 12.4 — IAM least-privilege: limiting blast radius

Every IAM role in WACTL has the *narrowest* set of permissions it needs to do its job. This is the "principle of least privilege" — if any role's credentials leak, the damage is bounded.

### Lambda execution role

The Lambda can:

- Write to CloudWatch Logs (for its own log group).
- Read the three SSM parameters (`/wactl/whatsapp/*`).
- Read/write/delete in the media bucket.
- Read/write on the dedup table (one specific table).
- Send to the jobs queue (one specific queue).

It cannot:

- Read SSM parameters outside `/wactl/whatsapp/*` (e.g. not AWS-managed parameters, not other teams' parameters).
- List S3 buckets.
- Read or write the releases bucket.
- Receive from the jobs queue.
- Modify the dedup table schema.
- Invoke other Lambda functions.

If an attacker gets the Lambda's credentials (e.g. via SSRF in a dependency that reaches the IMDS endpoint), they can: send messages as our bot (bad), read other users' files in the media bucket (very bad), and try to claim duplicate wamids (which would cause us to drop legit messages — annoying but not data exfiltration). They can't, e.g., spin up EC2 instances or read other teams' SSM parameters.

### Worker instance role

The worker can:

- Write to CloudWatch Logs (for the worker log group).
- Receive from, delete from, and read attributes of the jobs queue.
- Read/write the media bucket.
- Read the two SSM parameters (access token + app secret).

It cannot:

- Send to the jobs queue (only the Lambda can).
- Read the verify token from SSM (only the Lambda uses it for the GET handshake).
- Touch the dedup table.

The worker has fewer permissions than the Lambda. If the worker is compromised (e.g. via a malicious PDF that escapes the pdf2docx sandbox), the attacker can: read and overwrite the media bucket (data tampering/exfiltration within 24h-old files), and send messages as the bot. They can't enqueue jobs or affect the dedup table.

The most likely compromise path is pdf2docx or pymupdf, which parse complex PDF structures. We rely on:

- Process isolation (worker is a separate process from the rest of the system).
- Egress-only security group (no inbound traffic; an attacker can't pivot).
- systemd hardening (`NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`).
- Container-style isolation in the future (run the worker in a Firecracker microVM or a container with seccomp).

The hardening directives in `worker/systemd/wactl-worker.service` are:

```ini
NoNewPrivileges=true       # can't escalate to root
ProtectSystem=strict       # /usr, /boot, /efi are read-only
ProtectHome=true           # /home, /root are invisible
ReadWritePaths=/var/log/wactl /tmp  # only these are writable
PrivateTmp=true            # /tmp is private to this process
```

A compromised worker process can't modify system binaries, can't see other users' files, can't escape into the host's `/tmp`. The blast radius is "this process and its logs."

### GitHub Actions OIDC role

The GHA role can:

- Read/write the state bucket (for Terraform).
- Read/write the releases bucket (for upload of `worker.tar.gz`).
- Update the webhook Lambda's code and config.
- Describe EC2 instances and use the autoscaling APIs.

It cannot:

- Read SSM parameters.
- Read the media bucket.
- Receive from the jobs queue.
- Invoke Lambda functions other than the webhook.

The trust policy is restricted to a single repo + branch:

```hcl
condition {
  test     = "StringLike"
  variable = "token.actions.githubusercontent.com:sub"
  values   = ["repo:sathya-narayanan/wactl:ref:refs/heads/main"]
}
```

A PR from a fork has a different `sub` and is rejected by AWS before the role is ever assumed. So a malicious PR can't use the OIDC credentials to deploy.

What the role *can* do is still significant: it can update the Lambda's environment variables. If the role's trust policy is ever loosened (e.g. to allow PRs from forks), an attacker could swap the SSM parameter names in the env, and the Lambda would call a different parameter. Defense in depth: even if the GHA role is compromised, the Lambda's IAM only allows reading the three specific parameters we declared — not arbitrary ones.

## 12.5 — SSM for secrets: the only place they're allowed

The three WhatsApp secrets and the Gemini API key are stored as `SecureString` SSM parameters. They're encrypted at rest with KMS; only callers with the right IAM policy can read them; the access is logged in CloudTrail.

Why not Lambda environment variables directly?

- **No audit trail.** Lambda env vars are visible in the console and via `GetFunctionConfiguration`; reading them doesn't generate a CloudTrail event.
- **No rotation.** Changing a Lambda env var requires a function update (or a new deploy).
- **Plain text.** Lambda env vars are encrypted at rest, but the encryption key is AWS-managed; the values are in the function's configuration object.

SSM SecureString is the right answer for "secret that needs to be in process memory but never in code or config files."

The cache (`src/wactl/integrations/aws/secrets.py`) is in-memory only; the values never touch disk. Cache TTL is 5 minutes; rotation takes effect after that.

## 12.6 — S3 public access blocks: defending the bucket

Both S3 buckets have all four public-access blocks enabled:

```hcl
resource "aws_s3_bucket_public_access_block" "media" {
  bucket = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

This is the most paranoid S3 setting. Even if you accidentally attach a `public-read` policy to a single object, the bucket-level block rejects the access. Even if a well-meaning teammate enables ACLs for the bucket, the `ignore_public_acls` setting prevents them from taking effect.

The cost of this paranoid setting: zero. AWS doesn't charge for blocked requests.

## 12.7 — IMDSv2: defending the metadata service

The EC2 instance's metadata service is at `169.254.169.254` (link-local). It returns the instance's IAM credentials. SSRF attacks (server-side request forgery) often target the metadata service to steal credentials.

The launch template enforces IMDSv2:

```hcl
metadata_options {
  http_endpoint               = "enabled"
  http_tokens                 = "required"   # IMDSv2 enforced
  http_put_response_hop_limit = 1
}
```

IMDSv2 requires a `PUT` request with a token in the header. The token is generated by a `PUT` to `/latest/api/token` (also on the metadata service) and is valid for a few hours. A simple SSRF that does `GET http://169.254.169.254/latest/meta-data/iam/security-credentials/...` returns nothing — you need the token.

`http_put_response_hop_limit = 1` means: the token request can only traverse one hop. If the request goes through a proxy (e.g. the SSRF is via an internal load balancer that adds a hop), the token isn't returned.

This is a meaningful defense for an EC2 instance that processes untrusted data (PDFs, images) — the worker could be the SSRF target.

## 12.8 — The always-200 response: hiding internals

A subtle but important choice: **the Lambda always returns 200 to Meta, regardless of internal success or failure.** This was discussed in chapter 06, but the security angle is worth re-stating.

If we returned:

- **401 on bad signature** — an attacker probing the endpoint would learn "this URL exists and validates signatures."
- **500 on internal error** — Meta would retry forever on a permanently broken message, flooding the queue.
- **Specific error codes** — would let an attacker map the system.

200-with-log is the standard webhook-receiver pattern (Stripe, GitHub, Slack all do this). It hides the internal state from the outside world.

## 12.9 — Input validation at boundaries

Every user-supplied input is validated at the boundary before it touches the system:

| Input | Validation | Where |
|---|---|---|
| Webhook body | Pydantic model validation. Unknown fields ignored; missing required fields rejected. | `whatsapp/parser.py` |
| Slack-style URL | Scheme must be http(s); host must be present. | `web/fetcher.py::_validate_url` |
| GitHub PR URL | Strict regex match. | `github/pr_summary.py::parse_pr_url` |
| Image size spec | Positive integers; "WxH", "W", or "xH" format. | `commands/image_resize.py::_parse_args` |
| Translate language code | Non-empty string. | `commands/translate.py` |
| Job body from SQS | Pydantic model validation; unparseable messages are dropped. | `worker/main.py::_process_message` |

The pattern: every entry point assumes its input is hostile. Pydantic catches the structural problems; manual checks catch the semantic ones.

What's not validated:

- **Image bytes.** The image-resize and image-compress commands pass the bytes straight to Pillow. Pillow has had RCE vulnerabilities in the past; we accept the risk (Pillow is a hard dependency; the worker is hardened; the SSM parameter access is limited).
- **PDF bytes.** Same as images — passed to `pdf2docx` and `pymupdf`. Both libraries have had CVEs; we rely on keeping the libraries current and the worker hardened.

This is a deliberate trade-off: stronger input validation would mean re-implementing parts of the parsers. We accept the library risk because the libraries are well-maintained and the worker is hardened.

## 12.10 — Dependency pinning

`pyproject.toml` declares dependency version ranges; `uv.lock` pins exact versions. We commit `uv.lock` to the repo, so every deploy uses the same versions.

This is the simplest supply-chain defense: if a new release of `httpx` ships a backdoor, we don't get it on the next deploy. The pin is explicit.

We don't use `pip-audit` or `safety` to scan for known vulnerabilities in CI (yet). That's a future improvement.

## 12.11 — What we explicitly do NOT do

A non-goal is sometimes more important than a goal. Here are things we deliberately don't do:

- **No authentication on the webhook URL.** The HMAC *is* the authentication. A `Bearer` token would be redundant.
- **No rate limiting on inbound webhooks.** Meta already rate-limits their side; we don't need to. If we did, we'd use API Gateway usage plans.
- **No encryption-at-rest for messages.** CloudWatch Logs and S3 are encrypted by AWS; we don't add another layer.
- **No multi-tenant isolation.** This is a personal-scale system. Adding per-user encryption would be massive overhead.
- **No SOC 2 / HIPAA / PCI compliance.** The system processes personal messages but no payment data. The threat model is "don't leak my files," not "pass an audit."
- **No pen testing.** Manual code review + automated tests + the security primitives above. A pen test would be valuable but is out of scope.
- **No Web Application Firewall.** API Gateway has some WAF rules built in, but we don't add a `wafv2` resource. For personal scale, the surface area is small.

The principle: **layered, pragmatic defense.** HMAC + IAM + SSM + S3 blocks + IMDSv2 + the always-200 response. Each layer is cheap; together they bound the damage from any single failure.

## Next

→ [`13-frontend.md`](13-frontend.md) — the Next.js marketing site.
