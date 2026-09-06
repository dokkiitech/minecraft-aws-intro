# 05. S3 と SSM Parameter Store

対応ファイル: `s3.tf` / `main.tf`(SSM パラメータ名の定義)/ `server/mc-sync.sh`

## S3 — オブジェクトストレージ

S3(Simple Storage Service)はファイル(オブジェクト)置き場です。容量は事実上無制限、
耐久性はイレブンナイン(99.999999999%)、料金はワールド数百 MB なら月数セント。
この構成ではバケット 1 つを 3 つの用途に使っています。

```
minecraft-bedrock-<アカウントID>/
├── backups/    ← watchdog が停止前に置くワールドの tar.gz
├── bootstrap/  ← EC2 が起動時に取得する運用スクリプト・systemd unit
└── config/allowlist.json  ← 招待メンバーの一覧(Bot が編集)
```

### バケット名とパブリックアクセスブロック

バケット名は**世界中で一意**である必要があるため、アカウント ID をサフィックスにしています。
そして作ったら即、パブリックアクセスを全ブロックし、SSE-S3 による保存時暗号化を明示します:

```hcl
resource "aws_s3_bucket_public_access_block" "minecraft" {
  block_public_acls   = true
  block_public_policy = true
  # ...
}
```

「S3 の設定ミスで全世界公開」は情報漏えい事故の定番です。公開する理由がないバケットは
機械的に全ブロックが鉄則です。

### ライフサイクルルール — 消し忘れの自動化

バックアップは放っておくと無限に溜まります。`backups/` プレフィックスには
**60 日で自動削除**し、未完了のマルチパートアップロードを 7 日で中止するルールを付けてあり、
人間が掃除を覚えておく必要がありません。

```hcl
rule {
  filter { prefix = "backups/" }
  expiration { days = 60 }
}
```

### bootstrap パターン — スクリプト配布の仕組み

`server/` 以下のスクリプトは Terraform が S3 の `bootstrap/` にアップロードし
(`aws_s3_object.bootstrap` の `for_each`)、EC2 は**毎回の起動時**に `mc-sync.service` で
S3 から取得し直します。

これの何がうれしいかというと、**サーバー上のスクリプトを直したいとき、インスタンスに入らなくてよい**
のです。リポジトリでスクリプトを修正 → `terraform apply`(S3 が更新される)→ 次回起動時に自動反映。
「サーバーの中身も Git で管理する」が実現できています。

スクリプト同期後、`mc-sync.sh` は `install-bds.sh` を実行し、公式 API で Bedrock サーバーの
更新を確認します。更新確認に失敗した場合は systemd の失敗通知を出しますが、
インストール済みのサーバーの起動は妨げません。

### 「唯一の真実」を S3 に置く — allowlist の例

招待メンバー一覧 `config/allowlist.json` は面白い設計です:

- 初期値だけ Terraform が置く
- 以後は Discord の `/mc allow add/remove` で **Bot(Lambda)が直接 S3 を編集**する
- Terraform 側は `ignore_changes = [content]` で、apply が Bot の編集を巻き戻さないようにする

「Terraform が管理する初期状態」と「運用中に動的に変わる状態」の境界をどう引くかという、
IaC 運用の実践的な題材になっています。

## SSM Parameter Store — シークレット管理

Cloudflare の API トークンや Discord の Webhook URL は**コードに書いてはいけない**秘密情報です。
この構成では SSM Parameter Store の SecureString(KMS で暗号化)に置きます:

```sh
aws ssm put-parameter --type SecureString \
  --name /minecraft/cloudflare-token --value 'xxxxxxxx'
```

- 登録は Terraform の**外**で行う(tfstate にも平文を残さないため)
- EC2 は指定した 3 パラメータ、notifier Lambda は Discord Webhook パラメータだけを
  読めるよう IAM で制限(04 章)
- コード・リポジトリ・tfstate のどこにも秘密が現れない

Secrets Manager という上位サービスもありますが(自動ローテーション等。1 シークレット月 $0.40)、
この規模なら無料の Parameter Store で十分です。

---

前章: [04. IAM](04-iam.md) / 次章: [06. Lambda と Discord Bot](06-lambda-discord.md)
