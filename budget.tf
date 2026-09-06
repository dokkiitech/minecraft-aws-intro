# 予算 $5(Project=Minecraft タグのコストのみ)
# 自動停止が効かなくなって 24 時間回りっぱなし(約 $20/月ペース)になったら
# 予測超過の時点で Discord に通知が飛ぶ
#
# 注意: タグでコストを絞るには Billing コンソールで cost allocation tag
# 「Project」を有効化しておく必要がある(反映まで最大 24h)。README 参照

resource "aws_sns_topic" "budget_alerts" {
  name = "minecraft-budget-alerts"
}

resource "aws_sns_topic_policy" "budget_alerts" {
  arn = aws_sns_topic.budget_alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowBudgetsPublish"
      Effect    = "Allow"
      Principal = { Service = "budgets.amazonaws.com" }
      Action    = "SNS:Publish"
      Resource  = aws_sns_topic.budget_alerts.arn
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account_id }
      }
    }]
  })
}

resource "aws_sns_topic_subscription" "budget_to_notifier" {
  topic_arn = aws_sns_topic.budget_alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.notifier.arn
}

resource "aws_lambda_permission" "sns_budget" {
  statement_id  = "AllowSNSBudget"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notifier.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.budget_alerts.arn
}

resource "aws_budgets_budget" "minecraft" {
  name        = "minecraft"
  budget_type = "COST"
  time_unit   = "MONTHLY"

  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Project$Minecraft"]
  }

  # 実績 80% 到達($4)で早めに気付く
  notification {
    notification_type         = "ACTUAL"
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    subscriber_sns_topic_arns = [aws_sns_topic.budget_alerts.arn]
  }

  # 月末予測が 100% 超え = 止め忘れ・自動停止の故障をほぼ確実に検知
  notification {
    notification_type         = "FORECASTED"
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    subscriber_sns_topic_arns = [aws_sns_topic.budget_alerts.arn]
  }

  depends_on = [aws_sns_topic_policy.budget_alerts]
}
