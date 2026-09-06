# 障害検知の最後の保険(watchdog ごと死んで起きっぱなしになる事故を月 $0.10 で防ぐ)
# NetworkOut が 30 分間ほぼゼロ = 誰も繋いでいないのに watchdog が止めていない
# → アラームアクションで直接 stop する(Lambda 不要)

resource "aws_cloudwatch_metric_alarm" "idle_force_stop" {
  alarm_name        = "minecraft-idle-force-stop"
  alarm_description = "NetworkOut が 30 分ほぼゼロなら Minecraft EC2 を強制停止(watchdog 死亡時の保険)"

  namespace   = "AWS/EC2"
  metric_name = "NetworkOut"
  statistic   = "Sum"
  period      = 300
  dimensions = {
    InstanceId = aws_instance.bedrock.id
  }

  comparison_operator = "LessThanThreshold"
  threshold           = 50000 # bytes/5分。SSM Agent 等のノイズより上、プレイ中よりはるかに下
  evaluation_periods  = 6     # 5分 × 6 = 30分

  # 停止中はメトリクスが来ないが、それでアラームを鳴らさない
  treat_missing_data = "notBreaching"

  alarm_actions = ["arn:aws:automate:${local.region}:ec2:stop"]
}
