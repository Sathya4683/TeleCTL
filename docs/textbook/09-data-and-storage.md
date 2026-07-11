# 09 — Data and Storage

WACTL uses three AWS storage services: **S3** for files, **DynamoDB** for the dedup table, and **SSM Parameter Store** for secrets. Each is chosen for a specific reason, and each has its own Terraform config in `infra/`. This chapter walks through all three.

## 9.1 — The big picture

```text
┌────────────────────────┐    ┌────────────────────────┐
│  Inbound attachment    │    │  Outbound artifact     │
│  (user → WhatsApp)     │    │  (command → WhatsApp)  │
└───────────┬────────────┘    └──────────┬─────────────┘
            │                            ▲
            │ download (5-min URL)       │ upload + presign
            ▼                            │
   ┌────────────────────────────────────────────┐
   │     S3 media bucket                        │
   │     (1-day lifecycle, no public access)    │
   │     s3://wactl-dev-media-<account-id>      │
   └────────────────────────────────────────────┘
            ▲                            ▲
            │ download on first boot     │ upload by CI
            │                            │
   ┌────────┴────────────────────────────┴─────┐
   │  S3 releases bucket                       │
   │  s3://wactl-dev-releases-<account-id>     │
   │  • worker.tar.gz + .sha256 (CI → worker)  │
   │  • lambda.zip (CI → Lambda)               │
   │  • terraform.tfstate + .lock (TF backend) │
   └───────────────────────────────────────────┘

┌──────────────────────────────────────┐    ┌──────────────────────────────────────┐
│  DynamoDB table                      │    │  SSM Parameter Store                │
│  wactl-dev-dedup                     │    │  /wactl/whatsapp/access-token        │
│  • pk = wamid... (string)            │    │  /wactl/whatsapp/app-secret          │
│  • expires_at (TTL, 7 days)          │    │  /wactl/whatsapp/verify-token        │
│  • Pay-per-request                   │    │  /wactl/gemini/api-key               │
└──────────────────────────────────────┘    └──────────────────────────────────────┘
```

Three services, three purposes. Let's walk through each.

## 9.2 — S3: the media and releases buckets

### What S3 is

S3 is **object storage**. You put files (objects) in buckets (top-level folders); each object has a key (its path within the bucket) and arbitrary metadata. S3 is designed for "store a lot of files, retrieve them sometimes" — petabytes of data, eleven 9s of durability, pay only for what you store.

The trade-off vs. a filesystem: no real directories (slashes in keys are convention), no file locking, no in-place updates. You `PUT` an object, you `GET` an object. That's basically it.

### Why S3 for media

Two reasons we can't just stream files between Lambda and WhatsApp directly:

1. **WhatsApp's media URLs expire in 5 minutes.** If a user sends a 30-page PDF, the worker takes 60 seconds to convert it, and the original URL is long dead. The worker has to re-download from Meta at the moment of processing (within the 5-minute window).
2. **Outbound artifacts need a stable URL.** When the command finishes (`/pdf-docx` returns DOCX bytes), we need somewhere to put the file before sending the link to WhatsApp. S3 with a presigned URL is the standard pattern.

The media bucket also holds the presigned URL recipients: WhatsApp's servers fetch from S3 using the URL. We don't push bytes to WhatsApp's API; we hand it a URL it can pull from.

### The two buckets, in detail

We have **two** S3 buckets, not one. They serve different purposes and have different lifecycles.

#### `wactl-dev-media-<account_id>`

The user-facing bucket. Holds:
- Inputs that the worker re-downloads from Meta (defensive copy in case the URL expired).
- Outputs (the converted PDF, the resized image, the audio file).

Configured in `infra/s3.tf`:

```hcl
resource "aws_s3_bucket" "media" {
  bucket = "${local.suffix}-media-${local.account_id}"
  force_destroy = false
  tags = local.tags
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    id     = "expire-old-media"
    status = "Enabled"
    expiration {
      days = 1
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
```

Five things to notice:

- **`block_public_*` (all four)** — the most important security setting. Public access is blocked at the bucket level; even an accidental `public-read` ACL on a single object is denied.
- **Lifecycle: 1-day expiration.** Outputs are only needed while a job is in flight. After 24 hours, S3 deletes them. This caps storage costs (a busy system could accumulate a lot of MP3s).
- **Server-side encryption with AES256.** All objects are encrypted at rest. The cost is negligible (no per-object charge) and the security benefit is significant.
- **`force_destroy = false`.** Terraform won't delete a bucket that has objects in it. This is a safety belt: you can't accidentally `terraform destroy` and lose everything.
- **Bucket name includes the AWS account ID.** This makes the bucket globally unique (bucket names are a global namespace) without needing random suffixes.

#### `wactl-dev-releases-<account_id>`

The CI/infra bucket. Holds:
- `worker.tar.gz` and `worker.tar.gz.sha256` — uploaded by CI, downloaded by the worker on first boot.
- `terraform.tfstate` and `terraform.tfstate.lock` — the Terraform state and lockfile (see `infra/backend.tf`).
- (Eventual) `lambda.zip` — the Lambda deployment package.

Configured similarly, but with a different lifecycle: it keeps the *latest* of each file, and expires noncurrent versions after 30 days.

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "releases" {
  bucket = aws_s3_bucket.releases.id
  rule {
    id     = "keep-latest-50"
    status = "Enabled"
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload_days = 7
  }
}
```

The releases bucket doesn't expire current objects — they're meant to be permanent. It just cleans up the messy bits (orphan multipart uploads, old noncurrent versions if versioning is on).

### The S3 helper module

`src/wactl/integrations/aws/s3.py` wraps boto3 with five functions:

```python
def put_object(bucket, key, body, *, content_type=None, metadata=None) -> None: ...
def get_object(bucket, key) -> bytes: ...
def object_exists(bucket, key) -> bool: ...
def presigned_get_url(bucket, key, *, expires_in=900) -> str: ...
def make_key(*parts) -> str: ...
```

The crucial one is `presigned_get_url`:

```python
def presigned_get_url(bucket, key, *, expires_in=900) -> str:
    return cast(
        str,
        _get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        ),
    )
```

A **presigned URL** is a normal S3 URL with a query string that includes an AWS signature. Anyone with the URL can `GET` the object for the next N seconds (default 900s = 15 min). After that, the URL is invalid.

The signature is computed from the bucket owner's credentials. We don't share the AWS access keys; we just give WhatsApp a URL it can use. The pattern is the standard way to give temporary access to private S3 objects.

### The key layout

We use a structured prefix scheme for the media bucket:

```text
s3://wactl-dev-media-<id>/
├── out/                         # outbound artifacts
│   └── <last-10-digits-of-phone>/
│       └── <wamid>.<suffix>     # the converted file
└── in/                          # inbound attachments (re-downloaded)
    └── <last-10-digits-of-phone>/
        └── <wamid>.<suffix>
```

`output_key` in `src/wactl/commands/_helpers.py` builds the outbound key:

```python
def output_key(ctx, suffix):
    safe_user = ctx.user.phone[-10:]
    return s3.make_key("out", safe_user, f"{ctx.user.message_id}{suffix}")
```

Why last 10 digits of the phone and not the whole thing? Phone numbers in keys are a minor PII leak. The last 10 digits are unique enough for object lookup (no collision risk in a personal-scale system) and don't reveal country codes or area codes.

### S3 costs

S3 charges for:
- **Storage:** ~$0.023/GB/month for the standard tier. With 1-day lifecycle on the media bucket, the steady-state is tiny (kilobytes per user per day).
- **Requests:** $0.0004 per 1,000 PUTs, $0.0004 per 10,000 GETs. Free tier includes 2,000 PUTs and 20,000 GETs per month.
- **Data transfer out:** $0.09/GB to the internet. The outbound artifacts (via presigned URLs) flow to WhatsApp's servers, which counts as internet transfer.

For personal scale (a few hundred users, a few thousand commands/month), the S3 bill is under $0.50/month, often well under the free tier.

## 9.3 — DynamoDB: the dedup table

### What DynamoDB is

DynamoDB is a **NoSQL key-value store** with predictable performance at any scale. You define a table with a primary key; you `PutItem` (write), `GetItem` (read), `Query` (range query on a partition key), `Scan` (full table scan — avoid). It's schemaless: each item can have different attributes.

The big idea: you don't think about servers, replication, sharding. AWS handles all of that. You pick a primary key, you pick a billing mode (on-demand vs. provisioned), you pay per request.

### Why DynamoDB for dedup

The dedup problem: "have I seen this `wamid` before?" A simple `if wamid in seen_set` works for one Lambda invocation, but the Lambda is short-lived and we need dedup to survive across invocations. We need a database.

The two real options are:

| Service | Why we'd pick it | Why we don't |
|---|---|---|
| **DynamoDB** | Single-digit-ms reads/writes; pay-per-request is free-tier-friendly; TTL is built in. | — |
| **RDS Postgres** | Familiar SQL; transactional. | Always-on instance ($$); need to write a TTL cleanup job. |
| **ElastiCache (Redis)** | Fastest possible. | Always-on instance ($$); no built-in persistence. |
| **S3 + listing** | Cheap storage. | `ListObjectsV2` on every webhook is slow and expensive. |

DynamoDB is the obvious choice. It's also free-tier-friendly: 25 GB of storage and 25 WCU/RCU per month. The dedup table never gets large (a few KB per message × a few thousand messages/month = a few MB), so we stay well within the free tier.

### The conditional write

The dedup is implemented as a single atomic write:

```python
def try_claim(table, message_id, *, ttl_seconds, metadata=None) -> bool:
    expires_at = int(time.time()) + ttl_seconds
    item = {
        "pk": {"S": message_id},
        "expires_at": {"N": str(expires_at)},
    }
    try:
        _get_client().put_item(
            TableName=table,
            Item=item,
            ConditionExpression="attribute_not_exists(pk)",
        )
        return True   # first time we've seen this wamid
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False  # already exists → duplicate
        raise AWSIntegrationError(...) from exc
```

The `ConditionExpression="attribute_not_exists(pk)"` makes the `PutItem` atomic: it succeeds only if no item with that primary key exists. Two simultaneous webhooks for the same `wamid` (extremely rare, but possible) race on the write; one wins, the other gets `ConditionalCheckFailedException` and we treat it as a duplicate.

The `expires_at` attribute enables DynamoDB's TTL feature: items auto-delete 7 days after creation. The Terraform `infra/dynamodb.tf` configures TTL on this attribute:

```hcl
resource "aws_dynamodb_table" "dedup" {
  name         = "${local.suffix}-dedup"
  billing_mode = "PAY_PER_REQUEST"   # pay per request, not provisioned
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true   # 35-day backup, free for tables < 10 GB
  }
}
```

Three things to notice:

- **`PAY_PER_REQUEST`** — on-demand pricing. We pay only for the requests we make. The free tier covers 25 WCU + 25 RCU which is 2.5M writes + 2.5M reads per month. Way more than we need.
- **TTL on `expires_at`** — DynamoDB's TTL is a *background delete*, not a query filter. Items past their expiry are deleted within ~48 hours (eventually consistent). For dedup, this is fine: if we somehow read an expired item, our `try_claim` still works correctly (the conditional write is the source of truth, not a `GetItem` first).
- **Point-in-time recovery** — 35-day rolling backup of the table. Costs only apply if you restore. Defense in depth against a bug that wipes the table.

### Why fail-open

```python
def _is_duplicate(message_id):
    try:
        claimed = dynamodb.try_claim(...)
    except WactlError:
        return False   # dedup unavailable → process anyway
    return not claimed
```

If DynamoDB is unavailable, we process the message anyway. The alternative is to drop it (return 500 → Meta retries → flood the queue). For dedup, the cost of a duplicate send is low (annoying) compared to the cost of a dropped message (real user request gone).

This is a deliberate "availability over consistency" choice. Documented in chapter 06 as a property of the system.

### DynamoDB costs

For personal scale, the dedup table is essentially free:
- 25 GB storage (we use kilobytes) — free
- 25 WCU + 25 RCU on-demand (≈ 2.5M writes + 2.5M reads/month) — free
- Point-in-time recovery — free for tables < 10 GB

The first year of an AWS account gets extra free-tier benefits; after that, on-demand pricing is ~$1.25/M writes + $0.25/M reads. At our scale, that's cents per month.

## 9.4 — SSM Parameter Store: the secrets

### What Parameter Store is

SSM Parameter Store is a **secure key-value store** for configuration. It supports three parameter types: `String` (plain), `StringList` (comma-separated), and `SecureString` (encrypted with KMS). The free tier includes 10,000 Standard-tier parameters forever.

### Why Parameter Store (and not Secrets Manager or env vars)

The three real options:

| Option | Why we'd pick it | Why we don't |
|---|---|---|
| **SSM Parameter Store (SecureString)** | Free; integrates with IAM; per-parameter access control; KMS encryption. | 10k param limit (not a problem for us). |
| **AWS Secrets Manager** | Automatic rotation; cross-account replication. | $0.40/secret/month + $0.05/10k API calls. 3 secrets = $1.20/month minimum. |
| **Lambda env vars** | Free; simple. | Visible in the Lambda console; no audit trail; no rotation; no IAM. |

We chose SSM. It's free, integrates with IAM for access control, and the API is simple enough to wrap in 30 lines of Python.

### The three (or four) parameters

`infra/secrets.tf` creates placeholder parameters:

```hcl
resource "aws_ssm_parameter" "whatsapp_access_token" {
  name        = "wactl/whatsapp/access-token"
  description = "WhatsApp Cloud API system-user access token."
  type        = "SecureString"
  value       = "CHANGEME-populate-via-aws-ssm-put-parameter"
  tags = local.tags
}
```

We have:

| Parameter | What it is | Where it's used |
|---|---|---|
| `/wactl/whatsapp/access-token` | The system-user access token from Meta's developer portal. | The `WhatsAppClient` authorization header. |
| `/wactl/whatsapp/app-secret` | The app secret from Meta's developer portal. | HMAC signature verification. |
| `/wactl/whatsapp/verify-token` | A self-chosen random string. | The GET handshake echo. |
| `/wactl/gemini/api-key` | (Used by the worker) Gemini API key. | Gemini TTS for `/pdf-audio`. |

**Terraform creates the parameters with a placeholder value.** Real values are populated out-of-band:

```bash
aws ssm put-parameter --name "/wactl/whatsapp/access-token" \
    --type SecureString --value "EAAxxxx..." --overwrite
```

Why? Because if Terraform held the real value in state, anyone with read access to the state file would have the secret. The `infra/SETUP.md` doc walks through populating each parameter.

### The accessor module

`src/wactl/integrations/aws/secrets.py` provides `get_secret(name)` with a 5-minute in-memory cache:

```python
def get_secret(name, *, cache_ttl=DEFAULT_CACHE_TTL_SECONDS) -> str:
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(name)
        if cached is not None and cached[1] > now:
            return cached[0]

    try:
        client = _get_client()
        resp = client.get_parameter(Name=name, WithDecryption=True)
    except ClientError as exc:
        raise AWSIntegrationError(...) from exc

    param = cast(dict | None, resp.get("Parameter"))
    value = cast(str | None, param.get("Value")) if param else None
    if value is None:
        raise AWSIntegrationError(f"Parameter '{name}' has no Value")

    with _cache_lock:
        _cache[name] = (value, now + cache_ttl)
    return value
```

The cache matters for the Lambda. Without it, every webhook invocation would make one SSM `GetParameter` call per secret (3 calls). With it, the first invocation populates the cache, and subsequent invocations in the same container hit the cache. SSM API calls are not free ($0.05 per 10k), and the round trip adds ~30ms to each invocation.

Cache invalidation: the cache lives for 5 minutes, then expires. If you rotate a secret, you wait up to 5 minutes for the new value to take effect. For personal use, that's fine. For production, you'd want a `clear_cache()` call on a config-change event.

The cache is per-process. The Lambda container has its own; the worker has its own. They don't share. A rotation in SSM is observed in both after the cache TTL.

### IAM for SSM access

The Lambda's execution role and the worker's instance role both have `ssm:GetParameter` on the `/wactl/*` path. See `infra/iam.tf`. Least-privilege: the role can only read the WACTL parameters, not other parameters in the account.

### SSM costs

- **Standard tier:** free up to 10,000 parameters. We have 4. Free forever.
- **API calls:** $0.05 per 10,000 `GetParameter` calls. With the 5-minute cache, that's ~30k calls/month for a busy system. ~$0.15/month.

Negligible.

## 9.5 — What we don't use (and why)

Other AWS storage services you might expect to see:

- **RDS / Aurora** — too heavy for a personal-scale system. We don't have relational data; everything is either files (S3), key-value (DynamoDB), or secrets (SSM).
- **S3 Glacier** — cold storage. Our media lifecycle is 1 day, not "forever" or "10 years." Standard S3 is fine.
- **EBS** — block storage for EC2. The worker is too small to need persistent disk; everything it processes is in-memory or fetched fresh.
- **EFS** — shared filesystem. We don't have a use case.
- **Backup** — point-in-time recovery on DynamoDB is the only backup we have. The S3 buckets are versioned (via Terraform) but not backed up separately. State can be rebuilt from code + the running system.

The principle: **use the simplest primitive that solves the problem.** S3 for files, DynamoDB for key-value, SSM for secrets. Resist the urge to add a database "just in case."

## Next

→ [`10-external-services.md`](10-external-services.md) — WhatsApp Cloud API, Gemini, GitHub: every external system WACTL talks to, and how.
