# 08. ハンズオン — 構築して遊ぶ

前提: [01 章](01-aws-account.md) のアカウント準備(CLI が使える・コスト配分タグ `Project` を有効化済み)が
終わっていること。所要時間はおよそ 1 時間です。

## 0. リポジトリの取得とツール確認

```sh
git clone https://github.com/dokkiitech/minecraft-aws-intro.git
cd minecraft-aws-intro

terraform version   # >= 1.13
aws sts get-caller-identity
python3 --version
```

## 1. シークレットを SSM Parameter Store に置く

**Cloudflare API トークン**: Cloudflare ダッシュボード → My Profile → API Tokens →
Create Token。権限は **Zone → DNS → Edit を対象ドメインだけに絞って**発行します
(Global API Key は使わない。漏れたときの被害範囲を最小にするためです)。

**Discord Webhook**: 通知を流したいチャンネル → 設定 → 連携サービス → Webhook を作成し URL をコピー。

```sh
aws ssm put-parameter --type SecureString \
  --name /minecraft/cloudflare-token --value 'xxxxxxxx'
aws ssm put-parameter --type SecureString \
  --name /minecraft/discord-webhook \
  --value 'https://discord.com/api/webhooks/xxx/yyy'
# presence(Bot のオンライン表示)用。読むのは EC2 のみで Lambda には渡らない
aws ssm put-parameter --type SecureString \
  --name /minecraft/discord-bot-token --value 'xxxxxxxx'
```

(`discord-bot-token` は次のステップで Bot を作ってから登録しても OK)

## 2. Discord アプリを作る

[Discord Developer Portal](https://discord.com/developers/applications) → New Application。

1. **General Information** の **Application ID** と **Public Key** を控える
2. **Bot** タブで Bot Token を発行して控える(コマンド登録と presence 表示に使用)
3. **OAuth2 → URL Generator** で scope `bot` + `applications.commands` を選び、
   生成された URL で自分の Discord サーバーに招待する

## 3. 変数を埋める

```sh
cp minecraft.auto.tfvars.example minecraft.auto.tfvars
```

`minecraft.auto.tfvars`(gitignore 済み)を編集:

- `discord_application_id` / `discord_public_key` — 手順 2 で控えた値
- `record_name` — サーバーの FQDN(例: `mc.example.com`)
- `cf_zone_id` — Cloudflare ダッシュボード → 対象ドメイン → Overview 右下の Zone ID
- 任意: `server_name`(クライアントに表示される名前)、`allowlist`(招待制にする場合の gamertag)

## 4. Bot の zip を作って apply

```sh
./bot/build.sh          # PyNaCl の arm64 wheel を同梱した function.zip を作る
terraform init
terraform plan          # 何が作られるか読んでみる(30 個弱のリソース)
terraform apply
```

apply が終わると EC2 が初回起動し、user_data が Minecraft サーバーをセットアップします(数分)。

## 5. Discord に配線する

1. `terraform output interactions_endpoint_url` の URL を、Developer Portal の
   **General Information → Interactions Endpoint URL** に設定して保存。
   このとき Discord が PING と**わざと署名を壊したリクエスト**を送って検証します
   (06 章参照。失敗する場合は apply が完了しているか、URL のコピペミスがないか確認)
2. スラッシュコマンドを登録(Bot Token を使うのはここと presence だけ。`bot/.env.example` 参照):

```sh
APPLICATION_ID=... GUILD_ID=... BOT_TOKEN=... python3 bot/register_commands.py
```

`GUILD_ID` は Discord サーバーの ID(開発者モードを有効にしてサーバー名を右クリック → ID をコピー)。

## 6. 遊ぶ

Discord で:

```
/mc start    → 60〜90 秒後に「🟢 起動しました mc.example.com:19132」
/mc status   → 状態確認
/mc stop     → 保存して停止(プレイ中の人がいると拒否される)
/mc allow add <gamertag>   → 招待制の管理(稼働中なら約 30 秒で反映)
```

allowlist が空になると制限を無効化して誰でも参加できる状態になります
(`allowlist = []` の初期動作と同じ)。最初の名前を追加すると制限が再び有効になります。

Minecraft(統合版)の「サーバー」タブからサーバーを追加し、アドレスに `record_name` の値、
ポート `19132` で接続します。

全員が退出して 15 分経つと、「🔴 停止します」の通知とともにワールドが S3 にバックアップされ、
自動停止します。**放置して寝てよい**のがこの構成の売りです。

> Switch / PS 版はクライアントからサーバーを追加できないため、その面子が混ざる場合は
> BedrockConnect などの DNS 迂回が別途必要です。

## 7. 中を覗いてみる(おすすめ)

- コンソール → Resource Groups → `Minecraft` で、タグ対応リソースを一覧できる
- SSH の代わりに: `aws ssm start-session --target $(terraform output -raw instance_id)`
  - `journalctl -u bedrock -f` でサーバーログ、`journalctl -u mc-watchdog -f` で watchdog の動きが見える
- S3 バケットの `backups/` に停止のたびに tar.gz が増えていく

## トラブルシューティング

| 症状 | 見るところ |
| --- | --- |
| Interactions Endpoint の保存に失敗 | apply 完了済みか / URL の末尾まで正確か / CloudWatch Logs `/aws/lambda/minecraft-bot` |
| `/mc start` は成功するが接続できない | DNS が **DNS only(グレー雲)** か(プロキシは UDP 不可)/ `journalctl -u mc-dns` |
| Discord に通知が来ない | Webhook URL の SSM 値 / `journalctl -u mc-watchdog` |
| 予算アラートが一生 $0 | cost allocation tag `Project` の有効化(反映まで 24h) |

## 運用メモ

- サーバー(BDS)のアップデート: 稼働中に
  `sudo systemctl stop bedrock && sudo /usr/local/bin/install-bds.sh && sudo systemctl start bedrock`
  (ワールドと server.properties は保持されます)
- インスタンスは `lifecycle.ignore_changes` で作り直しを防いでいます([02 章](02-terraform.md))。
  意図的に作り直す場合は **S3 バックアップを確認してから** `terraform taint aws_instance.bedrock`
  (ワールドが消えます)
- `StopInstances` を直接叩くとセーブが中途半端になりえます。停止は必ず `/mc stop` か watchdog 経由で

## 完全な片付け

学習が済んだら、あるいはしばらく遊ばないなら:

```sh
terraform destroy
```

S3 バケットにオブジェクトが残っていると destroy が失敗するので、その場合は
バケットを空にしてから再実行します(ワールドを残したければ先にダウンロード)。
SSM パラメータは Terraform 管理外なので、別途 `aws ssm delete-parameter` で削除します。

**ここまでやって初めて課金が完全に止まります。** 「作る・使う・きれいに消す」まで一周してこそ入門完了です。

---

前章: [07. 監視とコスト管理](07-monitoring.md) / [README に戻る](../../README.ja.md)
