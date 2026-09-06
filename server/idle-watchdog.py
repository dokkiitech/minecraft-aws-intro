#!/usr/bin/env python3
"""Minecraft 統合版の無人検知 watchdog(障害検知①)。

- RakNet unconnected ping(mcstatus)で 30 秒ごとにプレイヤー数を見る
- 初回 ping 成功 → Discord Webhook へ「起動しました」(embed)
- 0 人が IDLE_MINUTES 続く → 「停止します」通知 → bedrock 停止 → S3 バックアップ
  → mc:StopReason タグ(notifier の異常停止通知を抑制)→ 自分を StopInstances
- Bot からの依頼タグを受ける: mc:StopRequest(/mc stop、同じ安全な停止フロー)、
  mc:RestartRequest(/mc restart、保存を伴う再起動)、
  mc:AllowlistSync(/mc allow、S3 から取得しコンソール reload で即反映)
- bedrock のログを journald 経由で follow し、プレイヤーの入退室を通知
- 起動直後は誰も居ないので BOOT_GRACE_MINUTES は停止判定しない
- Discord 通知の失敗でサーバー運用が止まらないよう、通知系の例外は握りつぶす
  (通知が来ないときはまず journalctl -u mc-watchdog を見る)
"""

import json
import logging
import os
import re
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request

import boto3
from mcstatus import BedrockServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mc-watchdog")

PUBLIC_ADDR = os.environ["PUBLIC_ADDR"]
WEBHOOK_PARAM = os.environ["WEBHOOK_PARAM"]
BACKUP_BUCKET = os.environ["BACKUP_BUCKET"]  # s3://bucket/prefix
IDLE_SECONDS = int(os.environ.get("IDLE_MINUTES", "15")) * 60
BOOT_GRACE_SECONDS = int(os.environ.get("BOOT_GRACE_MINUTES", "10")) * 60
CHECK_INTERVAL = 30
BEDROCK_DIR = "/opt/bedrock"
IMDS = "http://169.254.169.254/latest"
STATE_FILE = "/run/mc-ondemand.state"  # presence クライアントが読む停止フェーズの目印

GREEN = 0x57F287
RED = 0xED4245
YELLOW = 0xFEE75C
BLURPLE = 0x5865F2
GREY = 0x95A5A6

_webhook_url = None
ec2 = boto3.client("ec2")


def imds(path: str) -> str:
    req = urllib.request.Request(
        f"{IMDS}/api/token", method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"},
    )
    token = urllib.request.urlopen(req, timeout=5).read().decode()
    req = urllib.request.Request(
        f"{IMDS}/{path}", headers={"X-aws-ec2-metadata-token": token}
    )
    return urllib.request.urlopen(req, timeout=5).read().decode()


def notify(title: str, description: str = "", color: int = YELLOW,
           fields: list | None = None) -> None:
    """Discord Webhook へ embed を投げる。失敗しても運用を止めない。"""
    global _webhook_url
    try:
        if _webhook_url is None:
            _webhook_url = boto3.client("ssm").get_parameter(
                Name=WEBHOOK_PARAM, WithDecryption=True
            )["Parameter"]["Value"]
        embed = {"title": title, "description": description, "color": color}
        if fields:
            embed["fields"] = fields
        # UA 必須: urllib デフォルト UA は Discord (Cloudflare) に 403 で弾かれる
        req = urllib.request.Request(
            _webhook_url,
            data=json.dumps({"embeds": [embed]}).encode(),
            headers={"Content-Type": "application/json",
                     "User-Agent": "mc-ondemand/1.0"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        log.exception("Discord notification failed (continuing)")


def player_count() -> int | None:
    """RakNet unconnected ping。応答が無ければ None。"""
    try:
        status = BedrockServer("127.0.0.1", 19132, timeout=3).status()
        return status.players.online
    except Exception:
        return None


def pending_request(instance_id: str) -> str | None:
    """Bot が付ける依頼タグを見る。"stop" / "restart" / "allowlist" / None。
    読めないときは何もしない側に倒す。"""
    try:
        tags = ec2.describe_tags(Filters=[
            {"Name": "resource-id", "Values": [instance_id]},
            {"Name": "key",
             "Values": ["mc:StopRequest", "mc:RestartRequest", "mc:AllowlistSync"]},
        ])["Tags"]
    except Exception:
        log.exception("failed to check request tags")
        return None
    keys = {t["Key"] for t in tags}
    if "mc:StopRequest" in keys:  # 複数あるときは停止を優先
        return "stop"
    if "mc:RestartRequest" in keys:
        return "restart"
    if "mc:AllowlistSync" in keys:
        return "allowlist"
    return None


def sync_allowlist(instance_id: str) -> None:
    """/mc allow の変更を S3 から取り込み、コンソール経由で再起動なしに反映する。"""
    try:
        ec2.delete_tags(Resources=[instance_id], Tags=[{"Key": "mc:AllowlistSync"}])
    except Exception:
        log.exception("failed to clear mc:AllowlistSync tag")

    try:
        bucket = BACKUP_BUCKET.removeprefix("s3://").partition("/")[0]
        boto3.client("s3").download_file(
            bucket, "config/allowlist.json", f"{BEDROCK_DIR}/allowlist.json")
        subprocess.run(["chown", "bedrock:bedrock", f"{BEDROCK_DIR}/allowlist.json"],
                       check=False)
        with open(f"{BEDROCK_DIR}/allowlist.json") as f:
            names = [e["name"] for e in json.load(f)]
    except Exception:
        log.exception("allowlist sync failed")
        notify("⚠️ allowlist の反映に失敗しました",
               "`journalctl -u mc-watchdog` を確認してください", YELLOW)
        return

    # bedrock の FIFO 標準入力に有効/無効と reload を送る(再起動なしで反映)
    reloaded = False
    try:
        fd = os.open("/run/bedrock/stdin", os.O_WRONLY | os.O_NONBLOCK)
        enabled = "on" if names else "off"
        os.write(fd, f"allowlist {enabled}\nallowlist reload\n".encode())
        os.close(fd)
        reloaded = True
    except OSError:
        log.exception("failed to send allowlist reload (applies on next boot)")

    members = ", ".join(f"`{n}`" for n in names) if names else "(空 = 誰でも参加できます)"
    suffix = "" if reloaded else "\n(サーバーの次回起動時に反映されます)"
    notify("🔑 allowlist を更新しました", f"現在の許可: {members}{suffix}", BLURPLE)


# ---------- 入室・退室通知(BDS のログを journald 経由で監視) ----------

JOIN_RE = re.compile(r"Player connected: (.+?)(?:,|$)")
LEAVE_RE = re.compile(r"Player disconnected: (.+?)(?:,|$)")


def announce_player(name: str, joined: bool) -> None:
    time.sleep(1)  # ping のプレイヤー数に反映されるのを少し待つ
    count = player_count()
    suffix = f"現在 {count} 人がプレイ中" if count is not None else ""
    if joined:
        notify(f"👋 {name} さんが参加しました", suffix, GREEN)
    else:
        notify(f"🚪 {name} さんが退出しました", suffix, GREY)


def player_log_watcher() -> None:
    """bedrock unit のログを follow して入退室を通知する常駐スレッド。"""
    while True:
        proc = None
        try:
            proc = subprocess.Popen(
                ["/usr/bin/journalctl", "-u", "bedrock", "-f", "-n", "0", "-o", "cat"],
                stdout=subprocess.PIPE, text=True, bufsize=1,  # 行バッファで即時読み取り
            )
            for line in proc.stdout:
                if m := JOIN_RE.search(line):
                    announce_player(m.group(1).strip(), joined=True)
                elif m := LEAVE_RE.search(line):
                    announce_player(m.group(1).strip(), joined=False)
        except Exception:
            log.exception("player log watcher error (restarting)")
        finally:
            if proc is not None:  # 例外時に journalctl を残さない(wait でゾンビ化も防ぐ)
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        time.sleep(5)


def backup_world() -> int:
    """ワールドを tar.gz にして S3 へ。アーカイブのサイズ(バイト)を返す。"""
    include = [
        "worlds", "server.properties", "allowlist.json", "permissions.json",
        "behavior_packs", "resource_packs",  # アドオン利用時の保全
    ]
    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp:
        with tarfile.open(tmp.name, "w:gz") as tar:
            for name in include:
                path = os.path.join(BEDROCK_DIR, name)
                if os.path.exists(path):
                    tar.add(path, arcname=name)
        bucket, _, prefix = BACKUP_BUCKET.removeprefix("s3://").partition("/")
        key = f"{prefix}/world-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
        boto3.client("s3").upload_file(tmp.name, bucket, key)
        size = os.path.getsize(tmp.name)
        log.info("backup uploaded to s3://%s/%s (%d bytes)", bucket, key, size)
        return size


def restart_bedrock(instance_id: str) -> None:
    """/mc restart の処理。保存を伴う再起動をして完了を通知する。"""
    try:
        # 先にタグを消す(失敗・再起動ループの防止)
        ec2.delete_tags(Resources=[instance_id], Tags=[{"Key": "mc:RestartRequest"}])
    except Exception:
        log.exception("failed to clear mc:RestartRequest tag")

    notify("🔄 サーバーを再起動します", "ワールドを保存して再起動中…", YELLOW)

    # presence クライアントが「再起動処理中…」を表示できるように目印を置く
    try:
        with open(STATE_FILE, "w") as f:
            f.write("restarting")
    except OSError:
        log.exception("failed to write state file")

    try:
        try:
            subprocess.run(["/usr/bin/systemctl", "restart", "bedrock"],
                           check=False, timeout=180)
        except subprocess.TimeoutExpired:
            log.exception("systemctl restart bedrock timed out")
            notify("⚠️ 再起動コマンドがタイムアウトしました",
                   "`/mc status` で確認してください", YELLOW)
            return

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if player_count() is not None:
                notify("✅ 再起動が完了しました", "接続できます", GREEN)
                return
            time.sleep(5)
        notify("⚠️ 再起動後の応答確認がタイムアウトしました",
               "`/mc status` で確認してください", YELLOW)
    finally:
        try:
            os.remove(STATE_FILE)
        except OSError:
            pass


def shutdown(instance_id: str, reason: str) -> None:
    # presence クライアントに停止フェーズを伝える(Bot のステータスが「停止処理中」になる)
    try:
        with open(STATE_FILE, "w") as f:
            f.write("stopping")
    except OSError:
        log.exception("failed to write state file")

    cause = ("Discord の `/mc stop` を受け付けました" if reason == "manual"
             else f"{IDLE_SECONDS // 60} 分間無人だったため自動停止します")
    notify("⏳ 停止処理を開始しました", f"{cause}。ワールドを保存してバックアップ中…", YELLOW)

    # StopInstances だけだとセーブが中途半端になりうるので、必ず bedrock を先に止める
    try:
        subprocess.run(["/usr/bin/systemctl", "stop", "bedrock"], check=False, timeout=120)
    except subprocess.TimeoutExpired:
        # 止まりきらなくてもバックアップ→電源断は続行する(EBS にワールドは残る)
        log.exception("systemctl stop bedrock timed out (continuing shutdown)")

    backup_ok = True
    try:
        size = backup_world()
        notify("💾 ワールドをバックアップしました",
               f"S3 に保存済み({size / 1024 / 1024:.1f} MB、60 日間保持)", BLURPLE)
    except Exception:
        backup_ok = False
        log.exception("backup failed (stopping anyway; world persists on EBS)")
        notify("⚠️ S3 バックアップに失敗しました",
               "ワールドは EBS に残っています", YELLOW)

    try:
        # notifier(障害検知③)がこのタグを見て「正常停止」と判定する。
        # StopRequest は消しておかないと次回起動直後に即停止してしまう
        ec2.create_tags(
            Resources=[instance_id],
            Tags=[{"Key": "mc:StopReason", "Value": reason}],
        )
        ec2.delete_tags(Resources=[instance_id], Tags=[{"Key": "mc:StopRequest"}])
    except Exception:
        # タグ操作に失敗しても通知が重複するだけで実害はない
        log.exception("failed to update stop tags")

    # 完了通知は StopInstances の直前に出す(電源断後は通知できないため)
    result = "" if backup_ok else "(⚠️ バックアップ失敗、ワールドは EBS に残っています)"
    notify("🔴 サーバーを停止しました",
           f"また遊ぶときは `/mc start` で起動できます{result}", RED)

    log.info("stopping instance %s (reason=%s)", instance_id, reason)
    ec2.stop_instances(InstanceIds=[instance_id])


def main() -> None:
    instance_id = imds("meta-data/instance-id")

    # 停止フェーズの目印が残っていたら消す(/run は再起動で消えるが、途中失敗に備えて)
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass

    # 前回の停止失敗・異常終了などで依頼タグが残っていると
    # 起動直後に即停止・再起動してしまうので、監視を始める前に掃除しておく
    try:
        ec2.delete_tags(Resources=[instance_id], Tags=[
            {"Key": "mc:StopRequest"}, {"Key": "mc:RestartRequest"},
        ])
    except Exception:
        log.exception("failed to clear stale request tags")

    started = time.monotonic()
    booted = False
    idle_since = None

    log.info("watchdog started for %s (idle=%ss, grace=%ss)",
             instance_id, IDLE_SECONDS, BOOT_GRACE_SECONDS)

    threading.Thread(target=player_log_watcher, daemon=True).start()

    if player_count() is None:
        # BDS がまだ応答しない = 起動フェーズなので、チャンネルにも開始を知らせる
        notify("🟡 サーバーを起動しています…", "準備ができたらお知らせします", YELLOW)
    else:
        # watchdog の再起動などで BDS が既に稼働中。「起動しました」は出さない
        booted = True
        log.info("bedrock is already up")

    while True:
        request = pending_request(instance_id)
        if request == "stop":
            shutdown(instance_id, "manual")
            return
        if request == "restart":
            restart_bedrock(instance_id)
            idle_since = None  # 再起動直後の無人カウントを仕切り直す
        elif request == "allowlist":
            sync_allowlist(instance_id)

        players = player_count()

        if not booted:
            if players is not None:
                booted = True
                log.info("bedrock is up")
                host, _, port = PUBLIC_ADDR.partition(":")
                notify(
                    "🟢 サーバーが起動しました",
                    color=GREEN,
                    fields=[
                        {"name": "サーバーアドレス", "value": f"`{host}`", "inline": True},
                        {"name": "ポート", "value": f"`{port or 19132}`", "inline": True},
                    ],
                )
            elif time.monotonic() - started < BOOT_GRACE_SECONDS:
                time.sleep(CHECK_INTERVAL)
                continue
            # grace を過ぎても ping が通らない場合は無人扱いで停止カウントに入る
            # (起きっぱなし事故の防止。BDS 側の異常は OnFailure 通知が別途飛ぶ)

        if players:  # 1 人以上
            idle_since = None
        else:
            idle_since = idle_since or time.monotonic()
            idle_for = time.monotonic() - idle_since
            log.info("no players for %ds", int(idle_for))
            if idle_for >= IDLE_SECONDS:
                shutdown(instance_id, "idle")
                return

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
