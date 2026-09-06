"""Discord Interactions Endpoint(Lambda Function URL)で /mc start・stop・restart・status・
allow add|remove|list を受ける。

- Gateway 常駐なし。Discord から HTTP で叩かれるだけなので Lambda 無料枠で済む
- Discord は 3 秒以内の応答を要求するので、EC2 の起動待ちは
  type:5(deferred)で ACK してから自分を非同期 invoke してやる
- フォローアップは interaction token で叩けるため Bot Token は不要
  (interaction token の期限は 15 分。BOOT_TIMEOUT はその内側)
- /mc stop は直接 StopInstances せず、mc:StopRequest タグを付けて watchdog に依頼する
  (セーブ → S3 バックアップ → 停止 の安全なフローを必ず通すため)
- 署名検証は必須。Discord はエンドポイント登録時にわざと署名を壊した
  リクエストを送り、401 が返ることを確認する
- 応答はすべて embed(リッチ表示)。username/avatar は上書きしない
"""

import json
import os
import time
import traceback
import urllib.request

import boto3
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from mcstatus import BedrockServer

PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]
APPLICATION_ID = os.environ["APPLICATION_ID"]
INSTANCE_ID = os.environ["INSTANCE_ID"]
PUBLIC_ADDR = os.environ["PUBLIC_ADDR"]
BOOT_TIMEOUT = int(os.environ.get("BOOT_TIMEOUT", "150"))
CONFIG_BUCKET = os.environ["CONFIG_BUCKET"]
ALLOWLIST_KEY = "config/allowlist.json"  # S3 が唯一の真実。/mc allow で編集する

DISCORD_API = "https://discord.com/api/v10"

GREEN = 0x57F287
RED = 0xED4245
YELLOW = 0xFEE75C
GREY = 0x95A5A6

ec2 = boto3.client("ec2")


# ---------- Discord ヘルパー ----------

def verify_signature(event: dict, body: str) -> bool:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    signature = headers.get("x-signature-ed25519", "")
    timestamp = headers.get("x-signature-timestamp", "")
    try:
        VerifyKey(bytes.fromhex(PUBLIC_KEY)).verify(
            (timestamp + body).encode(), bytes.fromhex(signature)
        )
        return True
    except (BadSignatureError, ValueError):
        return False


def embed(title: str, description: str = "", color: int = GREY,
          fields: list | None = None) -> dict:
    e = {"title": title, "description": description, "color": color}
    if fields:
        e["fields"] = fields
    return e


def addr_fields() -> list:
    host, _, port = PUBLIC_ADDR.partition(":")
    return [
        {"name": "サーバーアドレス", "value": f"`{host}`", "inline": True},
        {"name": "ポート", "value": f"`{port or 19132}`", "inline": True},
    ]


def edit_original(token: str, e: dict) -> None:
    """type:5 で deferred にした元メッセージを embed で編集して結果を返す。"""
    # UA 必須: urllib デフォルト UA は Discord (Cloudflare) に 403 で弾かれる
    req = urllib.request.Request(
        f"{DISCORD_API}/webhooks/{APPLICATION_ID}/{token}/messages/@original",
        data=json.dumps({"embeds": [e]}).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "mc-ondemand/1.0"},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10)


# ---------- EC2 / BDS ヘルパー ----------

def instance_state() -> str:
    resp = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
    return resp["Reservations"][0]["Instances"][0]["State"]["Name"]


def ping_server() -> int | None:
    """RakNet unconnected ping。プレイヤー数を返す。応答が無ければ None。"""
    try:
        host, _, port = PUBLIC_ADDR.partition(":")
        status = BedrockServer(host, int(port or 19132), timeout=3).status()
        return status.players.online
    except Exception:
        return None


def wait_for_server(deadline: float) -> bool:
    while time.time() < deadline:
        if ping_server() is not None:
            return True
        time.sleep(5)
    return False


# ---------- コマンド実体(非同期 invoke 側で実行) ----------

def do_start(token: str) -> None:
    state = instance_state()

    if state == "running":
        if ping_server() is not None:
            edit_original(token, embed("✅ もう起動してるよ", color=GREEN, fields=addr_fields()))
            return
        edit_original(token, embed("⏳ サーバーの応答を待っています…",
                                   "インスタンスは起動済みです", YELLOW))
    elif state == "pending":  # 他の誰かが直前に /mc start した
        edit_original(token, embed("⏳ すでに起動処理中…", "60〜90 秒くらいかかります", YELLOW))
    elif state in ("stopped", "stopping"):
        # 停止処理中なら止まりきるのを待つ(Lambda timeout まで粘らないよう上限付き。
        # 万一超えたら start_instances が IncorrectInstanceState を投げてエラー応答になる)
        deadline = time.time() + 90
        while instance_state() == "stopping" and time.time() < deadline:
            time.sleep(5)
        ec2.start_instances(InstanceIds=[INSTANCE_ID])
        edit_original(token, embed("⏳ サーバーを起動中…", "60〜90 秒くらいかかります", YELLOW))
    else:
        edit_original(token, embed("⚠️ 起動できません",
                                   f"インスタンスが `{state}` 状態です", RED))
        return

    if wait_for_server(time.time() + BOOT_TIMEOUT):
        edit_original(token, embed("🟢 起動完了!", color=GREEN, fields=addr_fields()))
    else:
        edit_original(token, embed(
            "⚠️ 起動確認がタイムアウトしました",
            f"{BOOT_TIMEOUT} 秒以内に応答がありませんでした。"
            "もう少し待ってから `/mc status` で確認してください", YELLOW))


def do_stop(token: str) -> None:
    state = instance_state()
    if state == "stopped":
        edit_original(token, embed("🔴 もう停止しています", "EC2 は `stopped` です", GREY))
        return
    if state == "stopping":
        edit_original(token, embed("⏳ すでに停止処理中です", "EC2 は `stopping` です", GREY))
        return
    if state == "pending":
        edit_original(token, embed("⏳ まだ起動処理中です",
                                   "起動が終わってから `/mc stop` してください", YELLOW))
        return
    if state != "running":
        edit_original(token, embed("⚠️ 停止できません", f"EC2 は `{state}` です", RED))
        return

    players = ping_server()
    if players:  # 1 人以上
        edit_original(token, embed("⚠️ 停止しません",
                                   f"まだ {players} 人プレイ中です。全員退出すると"
                                   f" {os.environ.get('IDLE_MINUTES', '15')} 分後に自動停止もされます", YELLOW))
        return

    # watchdog への停止依頼タグ。直接 StopInstances するとセーブ・バックアップが飛ぶ
    ec2.create_tags(
        Resources=[INSTANCE_ID],
        Tags=[{"Key": "mc:StopRequest", "Value": "manual"}],
    )
    note = ("サーバーがまだ応答していません(起動途中かも)が、" if players is None else "")
    edit_original(token, embed(
        "🛑 停止要求を受け付けました",
        f"{note}ワールドの保存と S3 バックアップを始めます(1〜2 分)。"
        "終わると「🔴 サーバーを停止しました」の通知が流れます", RED))


def do_restart(token: str) -> None:
    state = instance_state()
    if state != "running":
        edit_original(token, embed("🔴 サーバーは停止中です",
                                   f"EC2: `{state}`。再起動ではなく `/mc start` で起動してください", GREY))
        return

    players = ping_server()
    # watchdog への再起動依頼タグ(保存を伴う安全な再起動をしてくれる)
    ec2.create_tags(
        Resources=[INSTANCE_ID],
        Tags=[{"Key": "mc:RestartRequest", "Value": "manual"}],
    )
    note = f"⚠️ {players} 人プレイ中のため一時切断されます。" if players else ""
    edit_original(token, embed(
        "🔄 再起動要求を受け付けました",
        f"{note}ワールドを保存して再起動します(30 秒〜1 分)。"
        "完了すると「✅ 再起動が完了しました」の通知が流れます", YELLOW))


def load_allowlist() -> list:
    s3 = boto3.client("s3")
    try:
        obj = s3.get_object(Bucket=CONFIG_BUCKET, Key=ALLOWLIST_KEY)
        return json.loads(obj["Body"].read())
    except s3.exceptions.NoSuchKey:
        return []


def save_allowlist(entries: list) -> None:
    boto3.client("s3").put_object(
        Bucket=CONFIG_BUCKET, Key=ALLOWLIST_KEY,
        Body=json.dumps(entries, ensure_ascii=False, indent=2).encode(),
        ContentType="application/json",
    )


def request_allowlist_sync() -> bool:
    """稼働中なら watchdog に反映を依頼する。稼働中だったかを返す。"""
    if instance_state() != "running":
        return False
    ec2.create_tags(
        Resources=[INSTANCE_ID],
        Tags=[{"Key": "mc:AllowlistSync", "Value": "1"}],
    )
    return True


def do_allow(token: str, action: str, gamertag: str | None) -> None:
    entries = load_allowlist()
    names = [e["name"] for e in entries]

    def members() -> str:
        return "\n".join(f"- `{n}`" for n in names) if names else "(空 = 誰も入れません)"

    if action == "list":
        edit_original(token, embed("🔑 allowlist", members(), GREY))
        return

    gamertag = (gamertag or "").strip()
    if not (1 <= len(gamertag) <= 32):
        edit_original(token, embed("⚠️ gamertag が不正です",
                                   "1〜32 文字で指定してください", RED))
        return

    if action == "add":
        if gamertag.lower() in (n.lower() for n in names):
            edit_original(token, embed("ℹ️ すでに登録されています",
                                       f"`{gamertag}` は allowlist に入っています", GREY))
            return
        entries.append({"ignoresPlayerLimit": False, "name": gamertag})
        names.append(gamertag)
        title = f"✅ `{gamertag}` を許可しました"
    else:  # remove
        matched = [e for e in entries if e["name"].lower() == gamertag.lower()]
        if not matched:
            edit_original(token, embed("⚠️ 見つかりません",
                                       f"`{gamertag}` は allowlist にいません\n{members()}", YELLOW))
            return
        entries = [e for e in entries if e["name"].lower() != gamertag.lower()]
        names = [e["name"] for e in entries]
        title = f"🗑️ `{gamertag}` の許可を外しました"

    save_allowlist(entries)
    applied = "サーバー稼働中のため 30 秒以内に反映されます" if request_allowlist_sync() \
        else "サーバーの次回起動時に反映されます"
    edit_original(token, embed(title, f"{applied}\n{members()}", GREEN))


def do_status(token: str) -> None:
    state = instance_state()
    if state != "running":
        edit_original(token, embed("🔴 サーバーは停止中です",
                                   f"EC2: `{state}`。`/mc start` で起動できます", GREY))
        return
    players = ping_server()
    if players is None:
        edit_original(token, embed("🟡 起動処理中かも",
                                   "EC2 は起動していますが、サーバーがまだ応答しません", YELLOW))
    else:
        edit_original(token, embed(
            "🟢 稼働中", color=GREEN,
            fields=addr_fields() + [{"name": "プレイヤー", "value": f"{players} 人", "inline": True}]))


# ---------- エントリポイント ----------

def handle_async_task(task: dict) -> None:
    token = task["token"]
    subcommand = task["subcommand"]
    args = task.get("args") or {}
    try:
        if subcommand.startswith("allow "):
            do_allow(token, subcommand.split()[1], args.get("gamertag"))
        else:
            handlers = {"start": do_start, "stop": do_stop,
                        "restart": do_restart, "status": do_status}
            handlers.get(subcommand, do_status)(token)
    except Exception as exc:  # 失敗を黙殺すると「考え中」のまま固まるので必ず返す
        # raise はしない: 非同期 invoke は失敗すると Lambda が自動リトライするため、
        # do_start の再実行・重複メッセージにつながる。ログに残して正常終了する
        traceback.print_exc()
        try:
            edit_original(token, embed("⚠️ エラーが発生しました", f"`{exc}`", RED))
        except Exception:
            traceback.print_exc()


def lambda_handler(event, context):
    # 非同期の自己 invoke(EC2 起動待ちはこちらでやる)
    if "async_task" in event:
        handle_async_task(event["async_task"])
        return {"ok": True}

    # 以降は Function URL 経由(Discord からのインタラクション)
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body).decode()

    if not verify_signature(event, body):
        return {"statusCode": 401, "body": "invalid request signature"}

    interaction = json.loads(body)

    if interaction["type"] == 1:  # PING(エンドポイント登録時の疎通確認)
        return respond({"type": 1})

    if interaction["type"] == 2:  # APPLICATION_COMMAND
        options = interaction["data"].get("options") or []
        opt = options[0] if options else {"name": "status", "type": 1}
        if opt.get("type") == 2:  # サブコマンドグループ(/mc allow add など)
            sub = opt["options"][0]
            subcommand = f"{opt['name']} {sub['name']}"
            args = {o["name"]: o["value"] for o in (sub.get("options") or [])}
        else:
            subcommand = opt["name"]
            args = {}

        # 3 秒制限内に ACK(type:5)し、実処理は自分を非同期 invoke して継続
        boto3.client("lambda").invoke(
            FunctionName=context.function_name,
            InvocationType="Event",
            Payload=json.dumps({
                "async_task": {
                    "subcommand": subcommand,
                    "args": args,
                    "token": interaction["token"],
                }
            }).encode(),
        )
        return respond({"type": 5})  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE

    return respond({"type": 4, "data": {"content": "unsupported interaction"}})


def respond(payload: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }
