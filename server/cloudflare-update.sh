#!/bin/bash
# 起動のたびに変わる Public IP を Cloudflare の A レコードに書き戻す。
# EIP(停止中も課金)を使わないための仕組み。bedrock.service より先に走る。
# プロキシは必ず OFF(オレンジ雲は UDP 19132 を通さない)。TTL 60。
set -euo pipefail

# /etc/mc-ondemand.env: CF_ZONE_ID / CF_TOKEN_PARAM / RECORD_NAME / AWS_DEFAULT_REGION
[ -f /etc/mc-ondemand.env ] && . /etc/mc-ondemand.env

# IMDSv2 で自分の Public IP を取る
imds_token=$(curl -fsS -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
public_ip=$(curl -fsS -H "X-aws-ec2-metadata-token: $imds_token" \
  "http://169.254.169.254/latest/meta-data/public-ipv4")

cf_token=$(aws ssm get-parameter --name "$CF_TOKEN_PARAM" --with-decryption \
  --query Parameter.Value --output text)

api="https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records"
# 起動直後はネットワークが安定しないことがあるのでリトライ付き。
# --retry だけだと POST/PUT はリトライされないので --retry-all-errors も付ける
# (DNS の upsert は冪等なので再送しても安全)
auth=(--retry 3 --retry-delay 5 --retry-all-errors \
  -H "Authorization: Bearer $cf_token" -H "Content-Type: application/json")
payload=$(jq -n --arg name "$RECORD_NAME" --arg ip "$public_ip" \
  '{type: "A", name: $name, content: $ip, ttl: 60, proxied: false}')

record_id=$(curl -fsS "${auth[@]}" "$api?type=A&name=$RECORD_NAME" \
  | jq -r '.result[0].id // empty')

if [ -n "$record_id" ]; then
  curl -fsS "${auth[@]}" -X PUT "$api/$record_id" --data "$payload" >/dev/null
else
  curl -fsS "${auth[@]}" -X POST "$api" --data "$payload" >/dev/null
fi

echo "updated $RECORD_NAME -> $public_ip"
