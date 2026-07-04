<!--
  GENERATED FILE - DO NOT EDIT.
  これは生成物。skills/source/body.md を編集すること。
  converter_version: 0.1.0
  build_input_digest: fd3eb4afcb7b1c88
-->
# qgb skill インストールガイド (codex / split)

## 配置先

- 個人全プロジェクト共通: `~/.agents/skills/qgb/`
- プロジェクト単位: `.agents/skills/qgb/`

## コピーするファイル

- `SKILL.md` (本体。helper の位置に `@see <helper-path>` の参照行が入る)
- helper files (`workflow.md` / `references.md` / `prompts/*.md` 等、SKILL.md と同じディレクトリに配置)

## hooks (任意, opt-in)

`hooks/` 配下に hook テンプレと `README.md` を同梱しています。利用する場合は `hooks/README.md` の手順に従って opt-in / dry-run / validate / 非破壊の後で既存設定へ merge してください。

## lint (verification_type=command 契約作成時)

`lint/` 配下に `check-command-contract.py` / `check-command-contract.ps1` を同梱しています。skill agent は `verification_type=command` の contract を起草・編集した直後にこの lint を実行し、fix-required の finding がないことを確認してから `qgb design-stages adopt` へ進むこと。詳細は `lint/README.md` を参照。

## Windows についての注意

Windows native 環境では symlink race 防御 (`O_NOFOLLOW` 相当) が POSIX より弱いことがあります。clean build + exclusive create の防御は有効ですが、信頼できない共有環境での build は推奨しません (詳細: `development/docs/journal/phase5-step5-a-2.md` §6.3 item 5)。
