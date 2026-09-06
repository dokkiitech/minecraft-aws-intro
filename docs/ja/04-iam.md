# 04. IAM — 最小権限のロール設計

対応ファイル: `iam.tf`

IAM(Identity and Access Management)は「誰が・何に・何をしてよいか」を決める仕組みで、
AWS のセキュリティの中核です。この構成には **3 つのロール**があり、それぞれが
「自分の仕事に必要な操作しかできない」ように絞ってあります(最小権限の原則)。

## ロールとは — アクセスキーを配らない仕組み

EC2 上のスクリプトが S3 にバックアップを置くには AWS の権限が要ります。
素朴にはアクセスキーをサーバーに置きたくなりますが、漏えいリスクの塊です。

代わりに **IAM ロール**を使います。ロールは「AWS のサービス自身が引き受ける(AssumeRole)権限の束」で、
EC2 にはインスタンスプロファイル経由で、Lambda には実行ロールとして紐づけます。
credentialは AWS が自動発行・自動ローテーションする一時的なもので、**コードにも設定ファイルにも
キーが登場しません**。

```hcl
assume_role_policy = jsonencode({
  Statement = [{
    Effect    = "Allow"
    Principal = { Service = "ec2.amazonaws.com" }  # EC2 だけがこのロールを引き受けられる
    Action    = "sts:AssumeRole"
  }]
})
```

## 3 つのロールの守備範囲

| ロール | 使う人 | できること |
| --- | --- | --- |
| `minecraft-bedrock` | EC2(watchdog) | SSM のシークレット読み取り / S3 バックアップ / **自分を停止** / タグ操作 |
| `minecraft-bot` | Bot Lambda | インスタンス**起動** / 状態確認 / 停止依頼タグ付け / allowlist の編集 / 自己の非同期 invoke |
| `minecraft-notifier` | 通知 Lambda | Webhook の読み取り / 停止理由タグの読み取り・削除 |

たとえば Bot Lambda は起動(`ec2:StartInstances`)はできても停止(`ec2:StopInstances`)は
**できません**。停止はワールドの保存を伴うため、必ず EC2 内の watchdog に「タグでお願いする」
設計です(権限の分離が、そのまま安全な停止フローの強制になっています)。

## タグ条件 — 「このプロジェクトのリソースだけ」に縛る

`ec2:StartInstances` を許可するとき、リソースを `instance/*`(全インスタンス)にすると
アカウント内の無関係なインスタンスまで起動できてしまいます。かといって対象インスタンスの
ARN を直接書くと、「ロールがインスタンスを参照し、インスタンスがロールを参照する」循環依存になります。

そこで**タグ条件**を使います:

```hcl
{
  Action    = ["ec2:StartInstances"]
  Resource  = "arn:aws:ec2:${local.region}:${local.account_id}:instance/*"
  Condition = {
    StringEquals = { "aws:ResourceTag/Project" = "Minecraft" }
  }
}
```

「`Project=Minecraft` タグの付いたインスタンスに限り操作できる」という縛り方です。
02 章の `default_tags` が全リソースにこのタグを付けているので、権限は自動的に
このプロジェクト内に閉じます。実務でもよく使う、覚えて損のないパターンです。

> `ec2:DescribeInstances` などの Describe 系だけ `Resource = "*"` なのは、
> AWS の仕様上リソースレベル制限に対応していないためです(読み取りのみなので許容)。

## SSM Session Manager — SSH の代わり

EC2 ロールには AWS 管理ポリシー `AmazonSSMManagedInstanceCore` を付けてあります。
これで **SSH なし・ポート開放なし・鍵管理なし**でシェルが取れます:

```sh
aws ssm start-session --target <インスタンスID>
```

- 22 番ポートを開けないので、世界中からの SSH 総当たり攻撃と無縁
- 誰がいつ接続したかが CloudTrail に残る(監査)
- 鍵ファイルの配布・失効管理が不要

トラブルシューティング(`journalctl -u mc-watchdog` など)もすべてこれで行います。

---

前章: [03. EC2](03-ec2.md) / 次章: [05. S3 と SSM Parameter Store](05-s3-ssm.md)
