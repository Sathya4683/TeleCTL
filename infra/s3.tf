# Media bucket — stores downloaded attachments and rendered outputs.
# Public access blocked (read/write via IAM only); short lifecycle so we
# don't accumulate stale jobs.
resource "aws_s3_bucket" "media" {
  bucket        = "${local.suffix}-media-${local.account_id}"
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

# Releases bucket — holds worker.tar.gz that the EC2 cloud-init pulls
# on first boot. SSE on by default; no lifecycle (artefacts are tiny
# and rotated by CI upload + overwrite, not by S3 expiry).
resource "aws_s3_bucket" "releases" {
  bucket        = "${local.suffix}-releases-${local.account_id}"
  force_destroy = false

  tags = local.tags
}

resource "aws_s3_bucket_public_access_block" "releases" {
  bucket = aws_s3_bucket.releases.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "releases" {
  bucket = aws_s3_bucket.releases.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
