# Minecraft 統合版オンデマンドサーバー
# - 遊ぶときだけ Discord の /mc start で EC2 を起動し、無人 15 分で自動停止
# - EIP は使わず、起動時に EC2 側から Cloudflare の A レコードを書き戻す
# - BDS は起動時に公式ダウンロード API から常に最新版を取得
# - 全リソースに Project=Minecraft タグ → Resource Group「Minecraft」でひとまとめ
# - 月額想定 $4〜4.5(t3a.medium 40h + EBS 20GB)。Budgets $5 で見張る
#
# apply 前に bot/build.sh で bot/function.zip を作っておくこと(README 参照)

terraform {
  required_version = ">= 1.13"

  # state はローカル管理(terraform.tfstate は gitignore 済み)。
  # チームで共有する場合は S3 backend を設定する(docs/02-terraform.md 参照):
  #
  # backend "s3" {
  #   bucket       = "tfstate-<あなたのアカウントID>"
  #   key          = "minecraft/terraform.tfstate"
  #   region       = "ap-northeast-1"
  #   use_lockfile = true
  # }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = "ap-northeast-1"

  default_tags {
    tags = {
      Project = "Minecraft"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region

  public_addr = "${var.record_name}:19132"

  # SSM SecureString(Terraform 外で put-parameter する。README 参照)
  cf_token_param  = "/minecraft/cloudflare-token"
  webhook_param   = "/minecraft/discord-webhook"
  bot_token_param = "/minecraft/discord-bot-token" # presence クライアント用(EC2 のみが読む)
  ssm_param_arns  = "arn:aws:ssm:${local.region}:${local.account_id}:parameter/minecraft/*"

  # Project=Minecraft タグの付いたインスタンスだけ操作できるようにする条件
  minecraft_tag_condition = {
    StringEquals = { "aws:ResourceTag/Project" = "Minecraft" }
  }
}

# コンソールで「Minecraft」1 グループにまとまって見えるようにする
resource "aws_resourcegroups_group" "minecraft" {
  name        = "Minecraft"
  description = "All resources of the on-demand Minecraft Bedrock server" # ASCII のみ許容

  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters = [{
        Key    = "Project"
        Values = ["Minecraft"]
      }]
    })
  }
}
