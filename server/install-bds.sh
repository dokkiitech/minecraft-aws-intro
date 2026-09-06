#!/bin/bash
# Bedrock Dedicated Server の最新版を公式ダウンロード API から取得して /opt/bedrock に展開する。
# 再実行するとアップデートになる(worlds/ と設定ファイルは保持)。
# minecraft.net は UA なしのリクエストを弾くので curl に UA を付ける。
set -euo pipefail

BEDROCK_DIR=/opt/bedrock
LINKS_API="https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
UA="Mozilla/5.0 (X11; Linux x86_64) mc-ondemand-installer"

# first(): 万一 API が同 downloadType を複数返しても 1 件に絞る
# --retry: 初回起動時に API が一時的に落ちていても user_data ごと失敗させない
url=$(curl -fsSL --retry 3 --retry-delay 10 --retry-all-errors -A "$UA" "$LINKS_API" \
  | jq -r 'first(.result.links[] | select(.downloadType == "serverBedrockLinux") | .downloadUrl) // empty')
[ -n "$url" ] || { echo "failed to resolve serverBedrockLinux download url" >&2; exit 1; }

version=$(basename "$url" .zip | sed 's/^bedrock-server-//')
installed=$(cat "$BEDROCK_DIR/.bds-version" 2>/dev/null || echo "none")

if [ "$version" = "$installed" ]; then
  echo "BDS $version is already installed"
  exit 0
fi

echo "installing BDS $version (installed: $installed)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL --retry 3 --retry-delay 10 -A "$UA" -o "$tmp/bds.zip" "$url"

mkdir -p "$BEDROCK_DIR"
if [ "$installed" = "none" ]; then
  unzip -q "$tmp/bds.zip" -d "$BEDROCK_DIR"
else
  # アップデート: ワールドとサーバー設定は上書きしない
  unzip -qo "$tmp/bds.zip" -d "$BEDROCK_DIR" \
    -x "worlds/*" "server.properties" "allowlist.json" "permissions.json"
fi

echo "$version" > "$BEDROCK_DIR/.bds-version"
chmod +x "$BEDROCK_DIR/bedrock_server"
id bedrock >/dev/null 2>&1 && chown -R bedrock:bedrock "$BEDROCK_DIR"
echo "BDS $version installed"
