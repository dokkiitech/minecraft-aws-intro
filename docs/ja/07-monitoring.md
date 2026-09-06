# 07. 監視とコスト管理 — 壊れる前提で設計する

対応ファイル: `monitoring.tf` / `budget.tf` / `lambda.tf`(EventBridge)/ `server/idle-watchdog.py` / `server/alert.sh`

この構成で一番怖い事故は「自動停止が壊れて、誰も遊んでいないのに動き続ける」ことです。
24 時間稼働だと約 $20/月ペース。そこで**停止まわりは「誰が死んでも別の層が気づく」3 層 + 保険 2 つ**
という過剰なくらいの多層防御にしてあります。分散システム設計の縮図として読んでください。

## 検知の 3 層

| 層 | 検知できるもの | 仕組み |
| --- | --- | --- |
| ① watchdog(EC2 内) | 通常の無人状態 | プレイヤー 0 人が 15 分続いたら、通知 → バックアップ → 自己停止 |
| ② systemd OnFailure | サーバーや watchdog 自体のクラッシュ | `mc-alert@.service` がログの末尾を添えて Discord に通知 |
| ③ EventBridge + Lambda | OS ごと死んだ・手動停止・terminate | **インスタンスの外**から状態変化イベントを拾って通知 |

ポイントは③です。①②はインスタンスの中で動いているので、インスタンスごと死ぬと一緒に死にます。
EventBridge は AWS 内のイベントバスで、「この EC2 が stopped/terminated になった」という
イベントをインスタンスの外で受け取り、notifier Lambda が Discord に流します。

```hcl
event_pattern = jsonencode({
  source      = ["aws.ec2"]
  detail-type = ["EC2 Instance State-change Notification"]
  detail      = { state = ["stopped", "terminated"], ... }
})
```

**監視は監視対象と運命を共にしてはいけない**、という監視設計の基本がここに出ています。

### 正常停止と異常停止の区別 — タグをフラグに使う

③は素朴に作ると、①の正常な自動停止でも「異常停止!」と鳴ってしまいます。
そこで watchdog は停止直前にインスタンスへ `mc:StopReason=idle` タグを付け、
notifier は stopped イベントを受けたらまずこのタグを見ます。あれば正常停止として黙り、タグを消す。
**タグが無いまま stopped = 異常**、という判定です。

EC2 のタグを「プロセス間で状態を伝えるフラグ」として使うテクニックで、`/mc stop`(停止依頼)や
allowlist の再読み込み依頼も同じ仕組みで実装されています。データベースを 1 つも持たずに
コンポーネント間の連携を成立させている点に注目してください。

## 保険①: CloudWatch アラームによる強制停止

watchdog ごと死んで通知も来ない、という最悪ケースへの保険:

```hcl
metric_name         = "NetworkOut"
threshold           = 50000   # bytes/5分
evaluation_periods  = 6       # 30 分継続で発火
alarm_actions       = ["arn:aws:automate:${local.region}:ec2:stop"]
```

「NetworkOut が 30 分ほぼゼロ = 誰も接続していないのに動いている」を CloudWatch メトリクスで検知し、
**アラームアクションで直接 EC2 を止めます**(Lambda すら不要)。閾値の 50KB/5分は
「SSM Agent 等の常時ノイズより上、プレイ中のトラフィックよりはるかに下」に置いた値です。
`treat_missing_data = "notBreaching"` により、停止中(メトリクスが来ない)には鳴りません。
費用はアラーム 1 本 $0.10/月。

## 保険②: AWS Budgets — 金額そのものを見張る最後の砦

ここまでの仕掛けが全部壊れても、**請求額は嘘をつきません**。`budget.tf` では
`Project=Minecraft` タグのコストに月 $5 の予算を張り、2 段階で通知します:

- **実績 80%**($4)到達 → 「今月ちょっと使いすぎでは」に早めに気づく
- **月末予測 100% 超え** → 止め忘れ・自動停止の故障をほぼ確実に検知(24 時間稼働なら月初でも予測が跳ねる)

通知は SNS トピック → notifier Lambda → Discord と流れます。SNS のトピックポリシーで
`budgets.amazonaws.com` からの Publish だけを許可している点も、サービス間連携の定番です。

> 前提: Billing コンソールで cost allocation tag `Project` を有効化しておくこと(01 章)。
> 忘れるとタグフィルタが効かず、予算が常に $0 のままになります。

## まとめ: コストは「設計」で守る

| 仕掛け | 守ってくれるもの |
| --- | --- |
| 自動停止(watchdog) | 日常の消し忘れ |
| NetworkOut アラーム | watchdog の故障 |
| Budgets $5 | 上記すべての想定外 |
| アカウント全体の予算(01 章) | このプロジェクト外の消し忘れ |

「気をつける」ではなく「仕組みで防ぐ」。個人の学習アカウントでも、この姿勢が身につくと
安心して実験できるようになります。

---

前章: [06. Lambda と Discord Bot](06-lambda-discord.md) / 次章: [08. ハンズオン](08-hands-on.md)
