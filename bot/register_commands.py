#!/usr/bin/env python3
"""スラッシュコマンド /mc (start | stop | restart | status | allow add/remove/list) を
ギルドに登録する。コマンド定義を変えたらローカルで再実行する(上書き登録される)。

Bot Token を使うのはここと EC2 の presence クライアントだけ(Lambda には持たせない)。

    APPLICATION_ID=... GUILD_ID=... BOT_TOKEN=... python3 register_commands.py
"""

import json
import os
import urllib.request

APPLICATION_ID = os.environ["APPLICATION_ID"]
GUILD_ID = os.environ["GUILD_ID"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

SUB_COMMAND = 1        # ApplicationCommandOptionType.SUB_COMMAND
SUB_COMMAND_GROUP = 2  # ApplicationCommandOptionType.SUB_COMMAND_GROUP
STRING = 3             # ApplicationCommandOptionType.STRING

command = {
    "name": "mc",
    "description": "Minecraft サーバーの操作",
    "options": [
        {"type": SUB_COMMAND, "name": "start", "description": "サーバーを起動する"},
        {"type": SUB_COMMAND, "name": "stop", "description": "サーバーを保存して停止する(誰かプレイ中は拒否)"},
        {"type": SUB_COMMAND, "name": "restart", "description": "サーバーを保存して再起動する"},
        {"type": SUB_COMMAND, "name": "status", "description": "サーバーの状態を確認する"},
        {
            "type": SUB_COMMAND_GROUP, "name": "allow",
            "description": "allowlist(招待制)の管理",
            "options": [
                {"type": SUB_COMMAND, "name": "add", "description": "gamertag を許可する",
                 "options": [{"type": STRING, "name": "gamertag",
                              "description": "許可する Xbox gamertag", "required": True}]},
                {"type": SUB_COMMAND, "name": "remove", "description": "gamertag の許可を外す",
                 "options": [{"type": STRING, "name": "gamertag",
                              "description": "外す Xbox gamertag", "required": True}]},
                {"type": SUB_COMMAND, "name": "list", "description": "許可メンバーを表示する"},
            ],
        },
    ],
}

req = urllib.request.Request(
    f"https://discord.com/api/v10/applications/{APPLICATION_ID}/guilds/{GUILD_ID}/commands",
    data=json.dumps(command).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bot {BOT_TOKEN}",
        # UA 必須: urllib デフォルト UA は Discord (Cloudflare) に 403 で弾かれる
        "User-Agent": "mc-ondemand/1.0",
    },
    method="POST",
)

with urllib.request.urlopen(req) as resp:
    print(f"registered: HTTP {resp.status}")
    print(json.dumps(json.loads(resp.read()), indent=2, ensure_ascii=False))
