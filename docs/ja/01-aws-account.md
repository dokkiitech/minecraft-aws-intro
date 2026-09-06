# 01. AWS アカウントの準備

すでに AWS CLI で作業できる環境がある人は、[請求アラート](#請求アラートを設定する)だけ確認して
次章へ進んで構いません。

## アカウントを作る

[aws.amazon.com](https://aws.amazon.com/jp/) からアカウントを作成します。
クレジットカードと電話番号(SMS 認証)が必要です。

作成直後に必ずやること:

1. **ルートユーザーに MFA(多要素認証)を設定する。**
   ルートユーザーは何でもできる最強アカウントなので、乗っ取られると請求も削除もやり放題になります。
   IAM コンソール → ルートユーザーの MFA から、スマホの認証アプリ(Authenticator 系)を登録します。
2. **ルートユーザーは以後使わない。** 日常作業は次に作る IAM の権限で行います。

## 作業用の認証情報を作る

AWS を操作する主体には「人間(コンソール / CLI)」と「AWSのリソース自身(EC2 や Lambda)」があり、
どちらも IAM(Identity and Access Management)で権限を管理します。
リソース側のロール設計は [04 章](04-iam.md) で扱うとして、ここでは人間用の設定をします。

**推奨: IAM Identity Center(旧 AWS SSO)**

個人アカウントでも Identity Center を使うと、有効期限つきの一時credentialで CLI を使えます
(長期のアクセスキーを PC に置かなくて済む)。

1. コンソールで「IAM Identity Center」を有効化(リージョンは東京 `ap-northeast-1` でOK)
2. ユーザーを 1 人作り、`AdministratorAccess` の権限セットを割り当てる
3. ローカルで CLI を設定:

```sh
aws configure sso
# SSO start URL / region を入力 → ブラウザで認証
aws sso login --profile <プロファイル名>
export AWS_PROFILE=<プロファイル名>
aws sts get-caller-identity   # 自分のアカウントIDが返れば OK
```

**簡易: IAM ユーザー + アクセスキー**

学習用に手早く始めるなら、IAM ユーザー(`AdministratorAccess`)を作りアクセスキーを発行して
`aws configure` でも動きます。ただしキーは漏れたら終わりの長期credentialなので、
git にコミットしない・不要になったら無効化する、を徹底してください。

> この教材の Terraform は「管理者相当の権限で apply する」前提です。
> 一方、**作られるリソース(EC2 / Lambda)自身の権限は最小限に絞ってあります**。
> この非対称が実務でも普通で、詳しくは 04 章で説明します。

## デフォルトリージョンを決める

この教材は東京リージョン `ap-northeast-1` 前提で費用を書いています。
ゲームサーバーは ping(遅延)が体感に直結するので、プレイヤーに近いリージョンを選びます。

```sh
aws configure set region ap-northeast-1
```

## 請求アラートを設定する

この構成自体にも予算監視($5、[07 章](07-monitoring.md))が入っていますが、それは
`Project=Minecraft` タグの付いたリソース限定です。**アカウント全体**の見張りを別途用意しておくと、
実験で作った別のリソースの消し忘れにも気づけます。

1. コンソール → Billing → Budgets → 「予算を作成」
2. テンプレート「月次コスト予算」で、たとえば $10 を設定し、メール通知先を入れる

5 分で終わるので、AWS を学ぶ人全員に最初にやってほしい設定です。

## コスト配分タグの有効化(この教材で必須)

この構成の予算監視は「`Project=Minecraft` タグが付いたリソースのコスト」でフィルタします。
タグをコスト集計に使うには、アカウント側での有効化が必要です:

1. Billing コンソール → **Cost allocation tags**
2. `Project` を選んで **Activate**

反映に最大 24 時間かかるため、**ハンズオン前日までにやっておく**のがおすすめです。
これを忘れると Budgets のタグフィルタが常に $0 になり、予算アラートが機能しません。

---

前章: [00. はじめに](00-intro.md) / 次章: [02. Terraform 入門](02-terraform.md)
