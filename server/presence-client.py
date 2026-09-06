#!/usr/bin/env python3
"""Discord Gateway に常駐して Bot のステータスをサーバー状態と連動させる(mc-presence.service)。

表示の対応:
- 起動処理中(BDS がまだ応答しない)  → 🟡 退席中「サーバー起動処理中…」
- 稼働中(RakNet ping が通る)        → 🟢 オンライン「mcサーバーオンライン」
- 停止処理中(watchdog が目印を書く) → 🔴 取り込み中「サーバー停止処理中…」
- インスタンス停止                    → オフライン(Gateway 接続ごと消える)

- やることは IDENTIFY と heartbeat と presence 更新(op 3)だけ。intents は 0
- 切断されたら指数バックオフで再接続。presence は飾りなので失敗しても騒がない
"""

import asyncio
import json
import logging
import os
import random
import subprocess
import time

import boto3
import websockets
from mcstatus import BedrockServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mc-presence")

GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
BOT_TOKEN_PARAM = os.environ["BOT_TOKEN_PARAM"]
PRESENCE_TEXT = os.environ.get("PRESENCE_TEXT", "mcサーバーオンライン")
STATE_FILE = "/run/mc-ondemand.state"  # watchdog が停止フェーズで "stopping" を書く
UPDATE_INTERVAL = 10

_token = None


def bot_token() -> str:
    global _token
    if _token is None:
        _token = boto3.client("ssm").get_parameter(
            Name=BOT_TOKEN_PARAM, WithDecryption=True
        )["Parameter"]["Value"]
    return _token


def current_presence() -> tuple[str, str]:
    """(status, カスタムステータス文言) を今のサーバー状態から決める。"""
    try:
        with open(STATE_FILE) as f:
            phase = f.read().strip()
        if phase == "stopping":
            return ("dnd", "サーバー停止処理中…")
        if phase == "restarting":
            return ("dnd", "サーバー再起動処理中…")
    except OSError:
        pass

    try:
        BedrockServer("127.0.0.1", 19132, timeout=2).status()
        return ("online", PRESENCE_TEXT)
    except Exception:
        pass

    bedrock_active = subprocess.run(
        ["/usr/bin/systemctl", "is-active", "--quiet", "bedrock"]
    ).returncode == 0
    if bedrock_active:
        return ("idle", "サーバー起動処理中…")
    return ("idle", "サーバー停止中")


def presence_payload(status: str, text: str) -> dict:
    return {
        "status": status,
        "since": None,
        "afk": False,
        # type 4 = カスタムステータス。表示されるのは state の文言
        "activities": [{"type": 4, "name": "Custom Status", "state": text}],
    }


async def session() -> None:
    """1 セッション分。切断・heartbeat ack 欠落で戻り、呼び出し側が再接続する。"""
    state = await asyncio.to_thread(current_presence)

    # ping_interval=None: WS レベルの ping は使わず、Discord の heartbeat (op 1/11) に任せる
    async with websockets.connect(GATEWAY, max_size=2**20, ping_interval=None) as ws:
        hello = json.loads(await ws.recv())
        interval = hello["d"]["heartbeat_interval"] / 1000

        await ws.send(json.dumps({
            "op": 2,  # IDENTIFY
            "d": {
                "token": bot_token(),
                "intents": 0,
                "properties": {"os": "linux", "browser": "mc-ondemand", "device": "mc-ondemand"},
                "presence": presence_payload(*state),
            },
        }))
        log.info("presence -> %s / %s", *state)

        seq = None
        acked = True

        async def heartbeat() -> None:
            nonlocal acked
            await asyncio.sleep(interval * random.random())  # 初回はジッタを入れる決まり
            while True:
                if not acked:  # 前回の ack が無い = ゾンビ接続
                    log.warning("heartbeat ack missing, reconnecting")
                    await ws.close(code=4000)
                    return
                acked = False
                await ws.send(json.dumps({"op": 1, "d": seq}))
                await asyncio.sleep(interval)

        async def presence_updater() -> None:
            nonlocal state
            while True:
                await asyncio.sleep(UPDATE_INTERVAL)
                new_state = await asyncio.to_thread(current_presence)
                if new_state != state:
                    state = new_state
                    await ws.send(json.dumps({"op": 3, "d": presence_payload(*state)}))
                    log.info("presence -> %s / %s", *state)

        tasks = [asyncio.create_task(heartbeat()),
                 asyncio.create_task(presence_updater())]
        try:
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("s") is not None:
                    seq = msg["s"]
                op = msg["op"]
                if op == 11:  # HEARTBEAT ACK
                    acked = True
                elif op == 1:  # サーバーからの heartbeat 要求
                    await ws.send(json.dumps({"op": 1, "d": seq}))
                elif op in (7, 9):  # RECONNECT / INVALID SESSION
                    log.info("gateway asked to reconnect (op=%s)", op)
                    return
                elif op == 0 and msg.get("t") == "READY":
                    log.info("connected as %s", msg["d"]["user"]["username"])
        finally:
            for t in tasks:
                t.cancel()
            # cancel しただけだと "Task exception was never retrieved" 警告が残る
            await asyncio.gather(*tasks, return_exceptions=True)


async def main() -> None:
    backoff = 5
    while True:
        started = time.monotonic()
        try:
            await session()
        except Exception as exc:
            log.warning("gateway session ended: %s", exc)
        # 長生きしたセッションのあとはバックオフをリセット
        if time.monotonic() - started > 120:
            backoff = 5
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    asyncio.run(main())
