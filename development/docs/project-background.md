# 本プロジェクトの経緯

本書は、`quality-gate-builder` (qgb) プロジェクトの着想の起点、参照している外部成果物、現時点での開発スタンスを整理する。

要件定義の本体は `requirements_and_development.md` を正本とする。本書はその背景文脈を残すための補助文書である。

## 1. 着想の起点

本プロジェクトは、PHPカンファレンス香川2026 (2026/05/09) の wakaba 氏 (@effy_staffs) によるトーク提案「AIの揺らぎに"コシ"を与える階層化品質設計」に強く影響を受けて開始された。

- トーク提案: <https://fortee.jp/phpconkagawa-2026/proposal/9e372768-fbf2-48c2-9f46-e6cec42cdc67>
- スライド: <https://speakerdeck.com/ickx/ainoyao-ragini-kosi-woyu-erujie-ceng-hua-pin-zhi-she-ji>

このトークが提起する中心的な問いは、「ハルシネーションを減らすにはどうするか」ではなく、**「そもそも品質とは何か」** という問い直しである。完成の定義（コードか、実装の正確さか、ある状態が満たされていることなのか）を分け、レイヤごとに検証責務を固定して複数視点から判定する構造を設計するという方向性が示されている。

wakaba 氏は PHP エンジニアであり、参考実装は PHP / Symfony を前提とした構成になっている（後述）。

## 2. quality-gate-builder の位置づけ

`quality-gate-builder` は、wakaba 氏が示した「階層化品質設計」の思想を、**処理系（言語・フレームワーク）非依存の形で再構成する**ことを目的とする。

具体的には：

- 対象プロジェクトの言語・フレームワークに依存しない品質ゲート生成基盤として設計する
- 任意の対象プロジェクト（Python / TypeScript / Go / Rust / .NET / Java / PHP / CLI / バッチ / Web UI / HTTP API / ドキュメント群 / 設定ファイル群 / プロンプト集 / ワークフロー定義 など）に対して、要求・契約・テスト・証跡・判定ゲートからなる品質確認系を生成する
- 最終形態（Phase 5 完了状態）は Claude Code のスキルとして提供される

wakaba 氏の実装 `yaoyorozu-system/core` は PHP / Symfony 向けの直接的な実装であり、参照すべき先行事例である一方、qgb はその思想を抽出し、対象範囲を広げる形で独自の設計を行う。

## 3. クロスレビュー体制

`requirements_and_development.md` v0.2 は ChatGPT 支援のもとで執筆された。Claude Code を導入した時点で、ChatGPT が執筆したスペックと wakaba 氏の参考実装の双方を Claude が読み合わせる「クロスレビュー」体制となっている。

クロスレビューでの主要論点は GitHub Issue として個別に切り出して管理する（`spec-review` ラベル）。

## 4. 開発フェーズと現在地

スペック §13 で定義されているフェーズは以下の通り：

- Phase 1: Python CLI MVP + 導入マニュアル
- Phase 2: 編集安全化（JSON Patch、専用 CLI による policy 編集など）
- Phase 3: adapter 拡張（Go / Rust / .NET / Java / PHP）
- Phase 4: CI 連携
- Phase 5: Skill Creator 化（対象プロジェクト専用スキル生成）

**最終目的は Phase 5 完了状態**、すなわち「対象プロジェクトに証跡ゲートを構築する Claude Code スキル」の提供である。Phase 1〜4 はそのための基盤を順次積み上げる過程と位置づける。

## 5. 思想的な前提

本プロジェクトが共有する中核の前提は以下である。これらは wakaba 氏のトークと直接的に対応する。

1. **LLM の出力や評価は揺らぐ** — 主観評価をそのまま品質保証の根拠にしてはならない
2. **AI は決定装置ではなく探索装置** — 候補生成と補助レビューには使えるが、採用判断には外部化された構造が必要
3. **保証対象の転換** — 「コードの同一性」ではなく「成立すべき状態」を保証する
4. **不易と流行の分離** — コードは流行に近づき、要求・制約・検査・証跡・判定は不易として固定する
5. **DENY は失敗ではない** — 揺らぎを安全に受け止めた結果であり、何度でも再生成できる入口
6. **ALLOW は「定義済み検査に通過した」ことのみを意味する** — 完全な正しさ、業務妥当性、セキュリティ、将来の保証は意味しない

## 6. 参照文書

- `requirements_and_development.md` — 要件定義書・基本設計書 v0.2（本プロジェクトの正本）
- `wakaba-talk-summary.md` — wakaba 氏の発表資料のまとめ
- `yaoyorozu-system-references.md` — wakaba 氏の公開リポジトリ情報
