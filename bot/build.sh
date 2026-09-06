#!/usr/bin/env bash
# Bot Lambda のデプロイ zip(function.zip)を作る。terraform apply の前に実行する。
# PyNaCl がネイティブ拡張なので、Lambda(arm64 / python3.12)向け wheel を
# platform 指定で取ってくる必要がある。
set -euo pipefail
cd "$(dirname "$0")"

rm -rf package function.zip
pip3 install \
  --target package \
  --platform manylinux2014_aarch64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  "PyNaCl>=1.5,<2" "mcstatus>=11,<15"

cp lambda_function.py package/
(cd package && zip -qr ../function.zip .)
rm -rf package

echo "created $(pwd)/function.zip"
