#!/bin/bash
# unit 異常終了時に journal の末尾を Discord Webhook へ送る(mc-alert@.service から呼ばれる)
# 通知の失敗でさらに OnFailure が連鎖しないよう、失敗しても 0 で返す
set -uo pipefail

unit="${1:?usage: alert.sh <unit-name>}"

webhook=$(aws ssm get-parameter --name "$WEBHOOK_PARAM" --with-decryption \
  --query Parameter.Value --output text) || exit 0

log=$(journalctl -u "$unit" -n 20 --no-pager -o cat | tail -c 1500)

jq -n --arg title "⚠️ $unit が異常終了しました" --arg desc "\`\`\`
$log
\`\`\`" '{embeds: [{title: $title, description: $desc, color: 15548997}]}' \
  | curl -fsS -m 10 -H "Content-Type: application/json" -d @- "$webhook" >/dev/null

exit 0
