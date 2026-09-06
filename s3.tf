# ワールドバックアップ + EC2 起動スクリプト(bootstrap)置き場
# - backups/  : watchdog が停止前に置くワールドの tar.gz(60 日で自動削除)
# - bootstrap/: server/ 以下のスクリプト・unit。user_data が初回起動時に取得

resource "aws_s3_bucket" "minecraft" {
  bucket = "minecraft-bedrock-${local.account_id}"
}

resource "aws_s3_bucket_public_access_block" "minecraft" {
  bucket = aws_s3_bucket.minecraft.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "minecraft" {
  bucket = aws_s3_bucket.minecraft.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "minecraft" {
  bucket = aws_s3_bucket.minecraft.id

  rule {
    id     = "expire-backups"
    status = "Enabled"

    filter {
      prefix = "backups/"
    }

    expiration {
      days = 60
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# allowlist の唯一の真実。初期値だけ Terraform が置き、以後は /mc allow(Bot)が編集する
resource "aws_s3_object" "allowlist" {
  bucket       = aws_s3_bucket.minecraft.id
  key          = "config/allowlist.json"
  content_type = "application/json"
  content = jsonencode([
    for name in var.allowlist : { ignoresPlayerLimit = false, name = name }
  ])

  lifecycle {
    # Bot の編集を apply で巻き戻さない(var.allowlist は初期シードのみ)
    ignore_changes = [content, etag]
  }
}

resource "aws_s3_object" "bootstrap" {
  for_each = fileset("${path.module}/server", "*")

  bucket = aws_s3_bucket.minecraft.id
  key    = "bootstrap/${each.value}"
  source = "${path.module}/server/${each.value}"
  etag   = filemd5("${path.module}/server/${each.value}")
}
