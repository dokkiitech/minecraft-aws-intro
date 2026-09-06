variable "record_name" {
  description = "サーバーの FQDN(Cloudflare の A レコード名。EC2 起動時に動的更新される)例: mc.example.com"
  type        = string
}

variable "cf_zone_id" {
  description = "record_name が属する Cloudflare ゾーン ID(Cloudflare ダッシュボード → 対象ドメイン → Overview 右下)"
  type        = string
}

variable "server_name" {
  description = "クライアントのサーバー一覧に表示されるサーバー名(server.properties の server-name)"
  type        = string
  default     = "my-minecraft-server"
}

variable "discord_application_id" {
  description = "Discord Developer Portal の Application ID"
  type        = string
}

variable "discord_public_key" {
  description = "Discord Developer Portal の Public Key(インタラクション署名検証用。秘密情報ではない)"
  type        = string
}

variable "instance_type" {
  description = "BDS は x86_64 ビルドのみなので x86 系から選ぶ(Graviton は Box64 エミュになるので非推奨)"
  type        = string
  default     = "t3a.medium" # 4GB。3 人同時プレイ想定(small の 2GB だと余裕がない)
}

variable "idle_minutes" {
  description = "プレイヤー 0 人がこの分数続いたら自動停止"
  type        = number
  default     = 15
}

variable "boot_grace_minutes" {
  description = "起動直後に無人でも停止しない猶予(分)"
  type        = number
  default     = 10
}

variable "allowlist" {
  description = "接続を許可する gamertag(招待制)。空リストにすると誰でも入れる(allow-list=false)"
  type        = list(string)
  default     = []
}

variable "monthly_budget_usd" {
  description = "Project=Minecraft タグの月額予算(USD)。超過見込みで Discord に通知"
  type        = number
  default     = 5
}
