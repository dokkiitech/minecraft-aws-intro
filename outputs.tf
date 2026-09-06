output "instance_id" {
  description = "Minecraft EC2 のインスタンス ID"
  value       = aws_instance.bedrock.id
}

output "server_address" {
  description = "クライアントから接続するアドレス"
  value       = local.public_addr
}

output "interactions_endpoint_url" {
  description = "Discord Developer Portal の Interactions Endpoint URL に設定する"
  value       = aws_lambda_function_url.bot.function_url
}

output "backup_bucket" {
  description = "ワールドバックアップ + bootstrap スクリプトのバケット"
  value       = aws_s3_bucket.minecraft.bucket
}
