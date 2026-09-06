# Discord Bot(Interactions Endpoint 方式)と異常停止通知の 2 関数
# Gateway 常駐(Fargate/EC2 で月 $8〜10)は使わず Lambda 無料枠内に収める

# ---------- Bot: /mc start・/mc stop・/mc status ----------
# PyNaCl(署名検証)と mcstatus(RakNet ping)を同梱するため、
# apply 前に bot/build.sh で function.zip を作っておく必要がある

resource "aws_lambda_function" "bot" {
  function_name    = "minecraft-bot"
  role             = aws_iam_role.bot.arn
  runtime          = "python3.12"
  architectures    = ["arm64"] # BDS と違い Bot は ARM で問題ない(安い方)
  handler          = "lambda_function.lambda_handler"
  filename         = "${path.module}/bot/function.zip"
  source_code_hash = filebase64sha256("${path.module}/bot/function.zip")
  timeout          = 180 # interaction token の期限 15 分より十分内側
  memory_size      = 256
  depends_on       = [aws_cloudwatch_log_group.bot]

  environment {
    variables = {
      DISCORD_PUBLIC_KEY = var.discord_public_key
      APPLICATION_ID     = var.discord_application_id
      INSTANCE_ID        = aws_instance.bedrock.id
      PUBLIC_ADDR        = local.public_addr
      BOOT_TIMEOUT       = "150" # 秒。Lambda timeout の内側に収める
      IDLE_MINUTES       = tostring(var.idle_minutes)
      CONFIG_BUCKET      = aws_s3_bucket.minecraft.bucket # /mc allow が編集する allowlist の置き場
    }
  }
}

# ロググループは Terraform で先に作って保持期間を付ける(Lambda 任せだと無期限)。
# 既存環境の自動作成分は取り込み済み(2026-09)。新規 apply ではそのまま作成される
resource "aws_cloudwatch_log_group" "bot" {
  name              = "/aws/lambda/minecraft-bot"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "notifier" {
  name              = "/aws/lambda/minecraft-notifier"
  retention_in_days = 30
}

# 認証は Discord の Ed25519 署名検証で行うので URL 自体は NONE。
# AWS provider が Function URL に必要な 2 つの公開 invoke 権限を作成する
resource "aws_lambda_function_url" "bot" {
  function_name      = aws_lambda_function.bot.function_name
  authorization_type = "NONE"
}

# ---------- 通知: EC2 状態変化・予算超過 → Discord ----------
# 依存ライブラリなし(boto3 + urllib)なので archive_file で直接 zip

data "archive_file" "notifier" {
  type        = "zip"
  source_file = "${path.module}/bot/notifier_lambda.py"
  output_path = "${path.module}/bot/notifier.zip"
}

resource "aws_lambda_function" "notifier" {
  function_name    = "minecraft-notifier"
  role             = aws_iam_role.notifier.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "notifier_lambda.lambda_handler"
  filename         = data.archive_file.notifier.output_path
  source_code_hash = data.archive_file.notifier.output_base64sha256
  timeout          = 30
  memory_size      = 128
  depends_on       = [aws_cloudwatch_log_group.notifier]

  environment {
    variables = {
      WEBHOOK_PARAM = local.webhook_param
      INSTANCE_ID   = aws_instance.bedrock.id
    }
  }
}

# 障害検知③: インスタンス外から stopped / terminated を拾う
# (watchdog の正常停止は mc:StopReason=idle タグで抑制。notifier 側で読んで消す)
resource "aws_cloudwatch_event_rule" "ec2_state" {
  name        = "minecraft-ec2-state"
  description = "Minecraft EC2 の停止イベントを Discord に通知(正常停止はタグで抑制)"

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["EC2 Instance State-change Notification"]
    detail = {
      state         = ["stopped", "terminated"]
      "instance-id" = [aws_instance.bedrock.id]
    }
  })
}

resource "aws_cloudwatch_event_target" "ec2_state_to_notifier" {
  rule = aws_cloudwatch_event_rule.ec2_state.name
  arn  = aws_lambda_function.notifier.arn
}

resource "aws_lambda_permission" "eventbridge_ec2_state" {
  statement_id  = "AllowEventBridgeEC2State"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notifier.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ec2_state.arn
}
