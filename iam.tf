# 最小権限の 3 ロール(EC2 / Bot Lambda / 通知 Lambda)
# EC2 系の操作はすべて Project=Minecraft タグ付きリソースに限定する
# (自分自身の ARN を参照すると循環依存になるためタグ条件で縛る)

# ---------- EC2 インスタンスロール ----------
# watchdog が使う: SSM シークレット読み取り / S3 バックアップ / 自己 stop + StopReason タグ

resource "aws_iam_role" "bedrock" {
  name = "minecraft-bedrock"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# SSH の代わりに SSM Session Manager でシェルを取る
resource "aws_iam_role_policy_attachment" "bedrock_ssm_core" {
  role       = aws_iam_role.bedrock.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "bedrock" {
  name = "minecraft-bedrock"
  role = aws_iam_role.bedrock.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadSecrets"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = local.secret_param_arns
      },
      {
        Sid       = "SelfStopAndTag"
        Effect    = "Allow"
        Action    = ["ec2:StopInstances", "ec2:CreateTags", "ec2:DeleteTags"]
        Resource  = "arn:aws:ec2:${local.region}:${local.account_id}:instance/*"
        Condition = local.minecraft_tag_condition
      },
      {
        Sid      = "ReadStopRequestTag" # Describe 系はリソース指定不可
        Effect   = "Allow"
        Action   = ["ec2:DescribeTags"]
        Resource = "*"
      },
      {
        Sid      = "Backup"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "${aws_s3_bucket.minecraft.arn}/*"
      },
      {
        Sid      = "ListBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.minecraft.arn
      }
    ]
  })
}

resource "aws_iam_instance_profile" "bedrock" {
  name = "minecraft-bedrock"
  role = aws_iam_role.bedrock.name
}

# ---------- Bot Lambda ロール ----------
# /mc start が使う: インスタンス起動 + 状態確認 + 非同期の自己 invoke

resource "aws_iam_role" "bot" {
  name = "minecraft-bot"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "bot_logs" {
  role       = aws_iam_role.bot.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "bot" {
  name = "minecraft-bot"
  role = aws_iam_role.bot.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "StartInstance"
        Effect    = "Allow"
        Action    = ["ec2:StartInstances"]
        Resource  = "arn:aws:ec2:${local.region}:${local.account_id}:instance/*"
        Condition = local.minecraft_tag_condition
      },
      {
        Sid       = "RequestStopViaTag" # /mc stop: watchdog への停止依頼タグ
        Effect    = "Allow"
        Action    = ["ec2:CreateTags"]
        Resource  = "arn:aws:ec2:${local.region}:${local.account_id}:instance/*"
        Condition = local.minecraft_tag_condition
      },
      {
        Sid      = "DescribeInstances" # Describe 系はリソース指定不可
        Effect   = "Allow"
        Action   = ["ec2:DescribeInstances"]
        Resource = "*"
      },
      {
        Sid      = "AsyncSelfInvoke"
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:${local.region}:${local.account_id}:function:minecraft-bot"
      },
      {
        Sid      = "EditAllowlist" # /mc allow の読み書き対象は allowlist だけに限定
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.minecraft.arn}/config/allowlist.json"
      }
    ]
  })
}

# ---------- 通知 Lambda ロール ----------
# EC2 状態変化イベントと Budgets SNS を受けて Discord に流す

resource "aws_iam_role" "notifier" {
  name = "minecraft-notifier"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "notifier_logs" {
  role       = aws_iam_role.notifier.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "notifier" {
  name = "minecraft-notifier"
  role = aws_iam_role.notifier.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadWebhook"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = local.webhook_param_arn
      },
      {
        Sid      = "ReadStopReasonTag" # Describe 系はリソース指定不可
        Effect   = "Allow"
        Action   = ["ec2:DescribeTags"]
        Resource = "*"
      },
      {
        Sid       = "ClearStopReasonTag"
        Effect    = "Allow"
        Action    = ["ec2:DeleteTags"]
        Resource  = "arn:aws:ec2:${local.region}:${local.account_id}:instance/*"
        Condition = local.minecraft_tag_condition
      }
    ]
  })
}
