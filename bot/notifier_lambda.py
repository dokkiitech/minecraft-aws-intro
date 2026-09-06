"""EC2 状態変化・予算アラートを Discord に流す通知 Lambda(障害検知③)。

- EventBridge: EC2 が stopped / terminated になったら通知。ただし watchdog の
  正常停止(mc:StopReason=idle タグ)は抑制し、読んだらタグを消す。
  タグが無いまま stopped になった = OS ごとの死・OOM・手動停止・terminate。
- SNS: AWS Budgets の予算超過通知($5)をそのまま流す。
- 依存ライブラリなし(boto3 + urllib)。zip に本ファイルを入れるだけでデプロイできる。
"""

import json
import os
import urllib.request

import boto3

WEBHOOK_PARAM = os.environ["WEBHOOK_PARAM"]

RED = 0xED4245
YELLOW = 0xFEE75C

_webhook_url = None


def notify(title: str, description: str = "", color: int = RED) -> None:
    global _webhook_url
    if _webhook_url is None:
        _webhook_url = boto3.client("ssm").get_parameter(
            Name=WEBHOOK_PARAM, WithDecryption=True
        )["Parameter"]["Value"]
    # UA 必須: urllib デフォルト UA は Discord (Cloudflare) に 403 で弾かれる
    req = urllib.request.Request(
        _webhook_url,
        data=json.dumps({"embeds": [
            {"title": title, "description": description, "color": color}
        ]}).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "mc-ondemand/1.0"},
    )
    urllib.request.urlopen(req, timeout=10)


def stop_reason_tag(instance_id: str) -> str | None:
    # タグが読めない・消せない場合は「異常停止」側に倒す(通知の重複はあっても見逃さない)
    try:
        ec2 = boto3.client("ec2")
        tags = ec2.describe_tags(Filters=[
            {"Name": "resource-id", "Values": [instance_id]},
            {"Name": "key", "Values": ["mc:StopReason"]},
        ])["Tags"]
        if not tags:
            return None
        # 次回の停止判定のために読んだら消す
        ec2.delete_tags(Resources=[instance_id], Tags=[{"Key": "mc:StopReason"}])
        return tags[0]["Value"]
    except Exception as exc:
        print(f"failed to read/clear mc:StopReason tag: {exc}")
        return None


def handle_ec2_event(event: dict) -> None:
    instance_id = event["detail"]["instance-id"]
    state = event["detail"]["state"]

    reason = stop_reason_tag(instance_id)
    if state == "stopped" and reason in ("idle", "manual"):
        # watchdog の正常停止(自動 or /mc stop)。watchdog が通知済みなので二重に鳴らさない
        print(f"{instance_id} stopped by watchdog ({reason}), suppressing alert")
        return

    notify(
        f"🚨 Minecraft サーバーが異常{'終了(terminated)' if state == 'terminated' else '停止'}しました",
        f"インスタンス `{instance_id}` が watchdog を経由せず `{state}` になりました。"
        "OS ごとの死・OOM・手動停止のいずれかです。"
        "ワールドの最終バックアップは前回の正常停止時のものになります。",
    )


def handle_sns_records(records: list) -> None:
    for record in records:
        message = record["Sns"]["Message"]
        notify("💸 AWS Budgets アラート(Minecraft)",
               f"```\n{message[:1500]}\n```", YELLOW)


def lambda_handler(event, context):
    if "Records" in event:  # SNS(Budgets)
        handle_sns_records(event["Records"])
    elif event.get("source") == "aws.ec2":  # EventBridge
        handle_ec2_event(event)
    else:
        print(f"unknown event: {json.dumps(event)[:500]}")
    return {"ok": True}
