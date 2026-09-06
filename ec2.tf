# ゲームサーバー本体。停止中は EBS 代しかかからない
# - EIP なし(停止中も課金されるため)。動的 Public IP を起動時に Cloudflare へ書き戻す
# - CPU クレジットは unlimited。standard だと停止→起動のたびに残高 0 から始まり、
#   ベースライン(2vCPU 合計 40%)に絞られてプレイ中にカクつく。
#   surplus 課金は自動停止 + Budgets $5 で抑えが効く(最悪でも +$2〜3/月程度)

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "ubuntu_2404" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_security_group" "bedrock" {
  name        = "minecraft-bedrock"
  description = "Minecraft Bedrock (UDP 19132/19133)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description      = "Bedrock IPv4"
    from_port        = 19132
    to_port          = 19132
    protocol         = "udp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    description      = "Bedrock IPv6"
    from_port        = 19133
    to_port          = 19133
    protocol         = "udp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  # SSH は開けない。シェルが要るときは SSM Session Manager を使う
  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = { Name = "minecraft-bedrock" }
}

resource "aws_instance" "bedrock" {
  ami                         = data.aws_ami.ubuntu_2404.id
  instance_type               = var.instance_type
  subnet_id                   = data.aws_subnets.default.ids[0]
  vpc_security_group_ids      = [aws_security_group.bedrock.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.bedrock.name

  credit_specification {
    cpu_credits = "unlimited"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    tags = {
      Project = "Minecraft" # default_tags はボリュームに伝播しないので明示
      Name    = "minecraft-bedrock"
    }
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 のみ。Docker で動かす場合は hop limit を 2 に
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    bootstrap_bucket   = aws_s3_bucket.minecraft.bucket
    cf_zone_id         = var.cf_zone_id
    cf_token_param     = local.cf_token_param
    webhook_param      = local.webhook_param
    bot_token_param    = local.bot_token_param
    record_name        = var.record_name
    server_name        = var.server_name
    public_addr        = local.public_addr
    region             = local.region
    backup_bucket      = "s3://${aws_s3_bucket.minecraft.bucket}/backups"
    idle_minutes       = var.idle_minutes
    boot_grace_minutes = var.boot_grace_minutes
    allow_list         = length(var.allowlist) > 0 ? "true" : "false"
  })

  # 起動スクリプトと allowlist が S3 に揃ってから初回起動させる
  depends_on = [aws_s3_object.bootstrap, aws_s3_object.allowlist]

  lifecycle {
    # AMI 更新や user_data 修正でインスタンスを作り直さない(ワールドデータ保護)。
    # associate_public_ip_address は停止中のインスタンスで false に見えるため、
    # 無視しないと「停止中に apply → 作り直しでワールド消失」の事故になる。
    # 作り直すときは S3 バックアップを確認してから terraform taint する
    ignore_changes = [ami, user_data, associate_public_ip_address]
  }

  tags = { Name = "minecraft-bedrock" }
}
