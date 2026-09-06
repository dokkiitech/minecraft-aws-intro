# 02. Terraform 入門

## IaC(Infrastructure as Code)とは

AWS コンソールをポチポチして作ったインフラは、

- 何をどう設定したか記録が残らない(再現できない)
- 消し忘れ・設定ミスに気づきにくい
- 同じ環境をもう 1 つ作るのに同じ作業を繰り返す

という問題があります。Terraform は「あるべきインフラの状態」をコードで書き、
実際の AWS をその状態に**収束**させるツールです。この教材の全リソース
(EC2、Lambda、IAM、S3、アラーム、予算…)は `.tf` ファイルに書かれていて、
`terraform apply` 一発で構築、`terraform destroy` 一発で全削除できます。

## 基本の 3 コマンド

```sh
terraform init    # 初回のみ: プラグイン(AWS プロバイダ等)の取得
terraform plan    # 差分確認: 「今から何を作る/変える/消すか」を表示するだけ
terraform apply   # 実行: plan の内容を AWS に適用する
```

**plan を読んでから apply する**癖をつけてください。`+` が作成、`~` が変更、
`-/+` は「作り直し(destroy して create)」です。特に `-/+` は要注意で、
この教材では EC2 が作り直されるとワールドデータが消えます(対策は後述)。

## リソースの書き方

`.tf` ファイルの基本単位は `resource` ブロックです。`s3.tf` から抜粋:

```hcl
resource "aws_s3_bucket" "minecraft" {
  bucket = "minecraft-bedrock-${local.account_id}"
}
```

- `aws_s3_bucket` がリソースの種類、`minecraft` がコード内での名前
- 他のリソースから `aws_s3_bucket.minecraft.bucket` のように参照できる。
  **この参照が依存関係になり、Terraform が作成順序を自動で決めます**
- `data` ブロックは「既存のものを読むだけ」。この教材ではデフォルト VPC や
  最新の Ubuntu AMI を `data` で引いています(`ec2.tf`)

## variables / outputs / tfvars

- `variables.tf` — 利用者ごとに変わる値(ドメイン名、インスタンスタイプ、自動停止までの分数など)。
  `default` のないものは必須入力
- `minecraft.auto.tfvars` — 変数への実際の値。`*.auto.tfvars` は apply 時に自動で読まれる。
  個人の値が入るので **gitignore 済み**(`.example` をコピーして使う)
- `outputs.tf` — apply 後に表示される値。この教材では Discord に設定する URL などを出力します

```sh
terraform output interactions_endpoint_url
```

## state(状態ファイル)

Terraform は「自分が作ったリソースの一覧と実際の ID」を `terraform.tfstate` に記録します。
これが**コードと実物の対応表**であり、消すと Terraform は自分が何を作ったか分からなくなります。

- state はローカルに置く設定です(1 人で使う分にはこれで十分)
- `terraform.tfstate` は gitignore 済み。**リソース ID などが入るため公開リポジトリに上げない**
- チームや複数マシンで共有するなら S3 backend を使います(`main.tf` にコメントで例あり)

## この教材ならではの Terraform テクニック

**`default_tags` で全リソースにタグを付ける**(`main.tf`)

```hcl
provider "aws" {
  region = "ap-northeast-1"
  default_tags {
    tags = { Project = "Minecraft" }
  }
}
```

プロバイダに書いておくと全リソースに `Project=Minecraft` が付きます。このタグが
「コンソールでひとまとめに見る(Resource Groups)」「IAM の権限をこのプロジェクトに限定する」
「予算をこのプロジェクトだけで区切る」の 3 つを支える、この構成の背骨です。

**`lifecycle.ignore_changes` で作り直しを防ぐ**(`ec2.tf`)

AMI は日々更新されるため、素朴に書くと apply のたびに「新しい AMI があるので EC2 を作り直します」
となり、**ワールドデータが消えます**。`ignore_changes = [ami, user_data, ...]` で
「初回作成後はこの属性の差分を無視する」と宣言して事故を防いでいます。

**`templatefile` でスクリプトに値を埋め込む**(`ec2.tf` → `user_data.sh.tftpl`)

EC2 の初回起動スクリプト(user_data)に、S3 バケット名やドメイン名などの Terraform の値を
テンプレートとして埋め込んでいます。インフラの値とサーバー内の設定を一元管理できます。

## IaC リポジトリの構成の育て方

このリポジトリは、`.tf` ファイルをすべて**リポジトリ直下に平置き**しています。
スタック(まとめて apply する単位)が 1 つしかない教材では、これが一番シンプルだからです。

では実際の運用でプロジェクトが増えたらどうするか。答えは「**スタックごとにディレクトリを分けた
モノレポ**」で、この教材の元になった構成は次のような形をしています:

```
infra/
├── aws/
│   ├── minecraft/     ← 本リポジトリの原型。ここで terraform apply
│   ├── portfolio/     ← 別プロジェクト。独立した state を持つ
│   └── ...
├── cloudflare/
│   └── dns/           ← プロバイダ(クラウド)単位でも分ける
└── docs/              ← 構成図など
```

押さえるべき原則は 3 つ:

1. **スタック = state = 影響範囲。** ディレクトリごとに独立した state を持たせると、
   `minecraft/` での apply ミスが `portfolio/` を壊すことは絶対にありません。
   「全部入りの巨大な state」は plan が遅くなり、事故の爆風半径も最大になります
2. **分け方は「一緒に作って一緒に消すか」で決める。** この教材の EC2・Lambda・IAM・予算は
   運命共同体なので 1 スタックが正解。逆に、複数プロジェクトから参照される DNS ゾーンや
   共有 VPC は別スタックに切り出します
3. **複数スタックになったら state をリモート(S3 backend)に置く。** ローカル state は
   スタック 1 つ・作業者 1 人までが限界です(`main.tf` のコメント参照)

つまり本リポジトリの平置きは「手抜き」ではなく、**モノレポの 1 ディレクトリを
そのまま切り出した形**です。fork して自分のインフラが増えてきたら、
`aws/minecraft/` のような階層に移して育てていってください。

---

前章: [01. AWS アカウントの準備](01-aws-account.md) / 次章: [03. EC2](03-ec2.md)
