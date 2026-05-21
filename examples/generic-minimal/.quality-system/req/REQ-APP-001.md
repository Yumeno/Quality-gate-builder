# REQ-APP-001: sample テキスト存在と挨拶キーワード包含

## 目的

`target/sample.txt` がプロジェクトに存在し、その中に挨拶キーワード `"hello"` が含まれることを保証する。

このサンプル REQ は qgb の入門用であり、特定の業務的価値を持つものではない。実プロジェクトで qgb を導入する場合は、保証したい状態 (ビジネス要求、UX 制約、技術契約など) を REQ として書く。

## 要求

- `target/sample.txt` がワークスペース内に存在する
- `target/sample.txt` の中身に `"hello"` という文字列が含まれる

## 受入条件

- `qgb validate` がスキーマ準拠を確認し OK 判定を出す
- `qgb validate-policy` が段階設計と参照整合性を確認し問題なしと判定する (Step 6 以降)
- `qgb run REQ-APP-001` が `ALLOW` を出力する (Step 5 以降)

## 検証

- 段階 S1: ファイル存在検査 (`verification_type: file_exists`)
- 段階 S2: 文字列包含検査 (`verification_type: substring_match`)

## 非目標

- ファイルの最終更新日時の確認 (思想 P7 と相性が悪いため除外、`design-notes.md` 参照)
- 内容のセマンティック検査 (このサンプルでは扱わない)
- 他言語ローカライズ (本 REQ は英語キーワードのみ扱う)

## 関連

- 段階定義: `.quality-system/policy.json`
- 契約: `.quality-system/contracts/REQ-APP-001/S1.json`, `S2.json`
- 設計判断: `../../design-notes.md`
