# 06. Lambda と Discord Bot

対応ファイル: `lambda.tf` / `bot/lambda_function.py` / `bot/register_commands.py` / `bot/build.sh`

## サーバーレスという選択

Discord Bot は普通、Gateway(WebSocket)に常時接続するプロセスとして作ります。
しかし常駐プロセスには置き場所が要り、Fargate や小さな EC2 でも月 $8〜10 かかります。
**ゲームサーバー本体より Bot のほうが高い**という本末転倒になりかねません。

そこで Discord の **Interactions Endpoint** 方式を使います。スラッシュコマンドが打たれると
Discord が指定 URL に HTTP POST してくる方式で、受け口を **Lambda** にすれば
「コマンドが打たれた瞬間だけコードが動く」構成になります。この使用頻度なら無料枠に収まり月 $0 です。

「イベントが起きたときだけ計算資源を借りる」——これがサーバーレスの発想で、
月に数十回しか呼ばれない処理に常駐サーバーを持つのは無駄、という判断ができるようになると
AWS のコスト設計は一段うまくなります。

## Function URL — API Gateway なしの HTTP 受け口

```hcl
resource "aws_lambda_function_url" "bot" {
  function_name      = aws_lambda_function.bot.function_name
  authorization_type = "NONE"
}
```

Lambda には Function URL という「その関数専用の HTTPS エンドポイント」を直接生やせます
(API Gateway を挟むより簡単・無料)。`NONE` = 誰でも叩ける URL ですが、無認証ではありません。
**認証はアプリケーション層の Ed25519 署名検証で行います**(次節)。

## 署名検証 — なりすましリクエストを弾く

Discord は全リクエストに署名(`X-Signature-Ed25519`)を付けます。Bot は Developer Portal で
控えた Public Key で検証し、署名が不正なら 401 を返します(`bot/lambda_function.py` 冒頭)。

面白いのは Discord 側の検証で、Interactions Endpoint URL を登録・保存する瞬間に
**わざと署名を壊したリクエストを送ってきて、ちゃんと 401 を返すか試されます**。
署名検証をサボった Bot はそもそも登録できない仕組みです。

## 「3 秒ルール」と非同期の自己 invoke

Discord はコマンドへの応答を **3 秒以内**に要求します。しかし EC2 の起動完了まで待つと
60〜90 秒かかります。そこで:

1. 同期側: 署名検証 → 「あとで返すね」という ACK(type:5)を**即返す**
2. その直前に、**自分自身を非同期で invoke** する(`InvocationType='Event'`)
3. 非同期側: `ec2:StartInstances` → サーバーに RakNet ping が通るまで待つ →
   Discord の follow-up API で元メッセージを「🟢 起動しました `mc.example.com:19132`」に編集する

「重い処理は ACK してからバックグラウンドで」という、Webhook 連携全般で使える定番パターンです。
なお interaction token の有効期限は 15 分なので、待ち時間の上限(`BOOT_TIMEOUT=150 秒`)は
Lambda の timeout(180 秒)ともどもその内側に収めてあります。

## デプロイパッケージと arm64

Bot は署名検証に PyNaCl(ネイティブ拡張)を使うため、Lambda の実行環境
(arm64 / Python 3.12)に合った wheel を同梱した zip を作る必要があります。それが `bot/build.sh` です:

```sh
pip3 install --target package \
  --platform manylinux2014_aarch64 --python-version 3.12 --only-binary=:all: \
  "PyNaCl>=1.5,<2" "mcstatus>=11,<15"
```

手元の Mac/PC 用のバイナリを入れると Lambda 上で ImportError になる、というのは
Lambda あるあるの筆頭です。なお Lambda 自体は arm64(Graviton)を選んでいます。
x86 より安く、Python コードは何の変更もなく動くからです(x86_64 必須なのは BDS 本体だけ)。

## ロググループは Terraform で先に作る

```hcl
resource "aws_cloudwatch_log_group" "bot" {
  name              = "/aws/lambda/minecraft-bot"
  retention_in_days = 30
}
```

Lambda に任せて自動作成させるとログの保持期間が**無期限**になり、ゴミが永遠に溜まります。
Terraform で先に作って保持期間を付けるのが定石です。

## もう 1 つの Lambda — notifier

`notifier_lambda.py` は EC2 の異常停止(07 章)と予算アラートを Discord に流す通知専用関数です。
こちらは依存ライブラリなし(boto3 + urllib)なので、`archive_file` データソースで
Terraform が直接 zip を作ります。依存の有無でデプロイ方法を使い分ける例になっています。

---

前章: [05. S3 と SSM Parameter Store](05-s3-ssm.md) / 次章: [07. 監視とコスト管理](07-monitoring.md)
