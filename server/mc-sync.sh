#!/bin/bash
# 起動のたびに S3 の bootstrap/ から運用スクリプトを取り直す(mc-sync.service から呼ばれる)。
# スクリプト修正は terraform apply で S3 に上がり、次回起動から自動反映される。
# systemd unit は対象外(unit の変更はインスタンス作り直しか手動反映)。
set -euo pipefail

# BACKUP_BUCKET=s3://bucket/backups → s3://bucket/bootstrap
src="${BACKUP_BUCKET%/*}/bootstrap"

aws s3 sync "$src/" /tmp/bootstrap/
for f in idle-watchdog.py cloudflare-update.sh alert.sh install-bds.sh mc-sync.sh presence-client.py; do
  if [ -f "/tmp/bootstrap/$f" ]; then
    install -m 755 "/tmp/bootstrap/$f" /usr/local/bin/
  fi
done

# allowlist は S3 の config/allowlist.json が唯一の真実(/mc allow で編集される)
if [ -d /opt/bedrock ]; then
  if aws s3 cp "${BACKUP_BUCKET%/*}/config/allowlist.json" /opt/bedrock/allowlist.json; then
    chown bedrock:bedrock /opt/bedrock/allowlist.json 2>/dev/null || true
  fi
fi

echo "synced scripts from $src"
