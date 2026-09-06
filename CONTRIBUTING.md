# Contributing

**English** | [日本語は下にあります](#日本語)

Thank you for your interest in this project! This repository is published as
open source, and contributions of all kinds are welcome — bug reports, typo
fixes, translations, and improvements to the Terraform code or the text.

## Ground rules

- **Do not push directly to `main`.** Direct pushes to the default branch are
  not accepted. All changes go through pull requests.
- **Contribute via fork + PR:**
  1. Fork this repository
  2. Create a topic branch in your fork (`fix/typo-in-ch03`, `feat/route53-variant`, …)
  3. Commit your changes and open a pull request against `main` of this repository
- Keep each PR focused on one thing. Small PRs get reviewed faster.

## Before you open a PR

- For Terraform changes, run `terraform fmt` and `terraform validate`.
- For changes to the text, English (`docs/`) is the primary language.
  Updating the Japanese version (`docs/ja/`) in the same PR is appreciated but
  not required — a maintainer or another contributor can follow up.
- The architecture diagram sources are `docs/images/*.drawio`; please
  re-export the PNGs when you change them.

## License

This project is licensed under the [MIT License](LICENSE). By submitting a
contribution, you agree that your contribution is licensed under the same
MIT License. Do not submit code you do not have the right to license this way.

---

## 日本語

このプロジェクトは OSS として公開しています。バグ報告・誤字修正・翻訳・
Terraform やテキストの改善など、あらゆるコントリビューションを歓迎します。

## 基本ルール

- **`main` への直接 push は禁止**です。変更はすべて Pull Request 経由で受け付けます。
- **fork → PR の流れで**お願いします:
  1. このリポジトリを fork する
  2. fork 側でトピックブランチを切る(`fix/typo-in-ch03` など)
  3. 変更をコミットし、このリポジトリの `main` に向けて Pull Request を作成する
- 1 つの PR には 1 つのテーマだけを入れてください。小さい PR ほど早くレビューできます。

## PR を出す前に

- Terraform の変更は `terraform fmt` と `terraform validate` を通してください。
- テキストは英語版(`docs/`)がメインです。日本語版(`docs/ja/`)も同じ PR で
  更新してもらえると助かりますが、必須ではありません。
- 構成図のソースは `docs/images/*.drawio` です。変更したら PNG も再エクスポートしてください。

## ライセンス

本プロジェクトは [MIT License](LICENSE) です。コントリビューションを提出した時点で、
その内容が同じ MIT License で提供されることに同意したものとみなします。
