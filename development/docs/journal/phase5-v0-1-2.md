# Phase 5 v0.1.2 skill 文言改善バッチ (canary #1 反映)

- 実施日: 2026-07-04 / 仕様: [Issue #28](https://github.com/Yumeno/Quality-gate-builder/issues/28) (canary #1 journal `phase5-step5-d-canary1.md` §4 の 4 件を集約)
- 編成: Fable 5 指揮 (文言起草・検収) + sonnet 実装 (適用・golden 再生成・テスト) + sonnet 独立レビュー 1 レンズ
- 変更対象: `skills/source/body.md` + `skills/source/metadata.yaml` (version 0.1.2) のみ。qgb 本体コード変更なし

## 1. 実装内容 (Issue #28 の 4 件 + 派生 2 件)

1. **§3.5 決定の所有権ブロック新設**: 「説明の深さの適応」と「決定の所有権」を区別。設計の分岐点は自信があっても必ず提示して選ばせる。既成事実 + 形式的承認関門 = ゴム印と同構造、と明文化 (canary #1 で検査観点を相談なしに高速設定した実測への対処)
2. **§3.5 話題単位の理解度観察**: 人物単位でなく話題単位で調整 (対象領域の専門家 ≠ qgb / 品質保証の専門家)
3. **argv[0] は OS ネイティブ区切り**: §6.5 step 4 に一般則 + §12 Python checklist に行追加 (Windows CreateProcess は `/` 区切り相対 path を解決しない — canary #1 実測)
4. **§6.6 新設「記録の規律: knowledge.jsonl は利用者プロジェクトの journal」**: gate = 何が通ったか (P7) / knowledge = なぜそう決めたか (P12 評価系の設計記録)。記録トリガ 4 種 (設計分岐 / 実地トラブル / 外部情報 P8 / waiver 自動) + 比例原則 (判断が発生したときだけ、官僚的記録を強いない)。canary #1 で knowledge.jsonl が空だった根本原因 (能動的記録を促す文言の欠落) への対処
5. (派生) §6.2 step 4 に §6.6 への 1 行ポインタ
6. (派生) §6.6 のクロスファイル参照に full/split 所在注記 — 独立レビューの must-fix 反映 (下記)

## 2. レビュー (比例縮退の判断を明記)

prose-only バッチ (コード変更ゼロ、仕様は Issue #28 で user 承認済、機械検証は golden 決定論 + 844 tests) のため、通常の 5 レンズ + Codex 横断を **1 レンズ (相互参照 / 矛盾混入 / §3.5 内部整合 / 技術的正確性) に縮退**。Codex 横断はセッション内 wrapper 不在も理由。縮退でも成果あり: **must-fix 1 件検出** — §6.6 の「レビュー観点プロンプト §5 を参照」が full/split 所在注記を欠き、split ビルド (workflow.md) の読者が参照先ファイル (prompts/review-policy.md) に到達できない。既存のクロスファイル参照慣習 (全箇所に注記あり) からの逸脱だった。→ 修正済。他 3 観点は発見ゼロ (argv[0] 記述は「相対 path」限定で過剰一般化なしを確認済)。

## 3. 機械検証

- golden 再生成: 48 files、digest `14924a4088439977` (v0.1.1) → `a9597890ff883282` (v0.1.2 最終)
- テスト: 844 passed, 3 skipped (POSIX-only 既知 skip)
- 決定論: `.venv` (Python 3.13) と `py -3.10` の実ビルドで全 4 セル digest 一致 (検収の環境整合ルール準拠)
- 差分は body.md / metadata.yaml + golden 再生成出力のみ (`git diff --stat` で確認)

## 4. リリース手順 (このバッチの残作業)

1. commit + push → CI 4 matrix + golden-integrity + lock-integrity green 確認
2. user が `skill-v0.1.2` タグを作成・push → release workflow (two-lineage 検証 + 4 zip)
3. Issue #28 close

## 5. 次工程との接続

canary #2 (Sonnet 運転 × user 初心者演技 × ネガティブコントロール、設営は user 側) は v0.1.2 配布物で実施し、本バッチの §3.5 決定所有権 / §6.6 記録規律の効果を測定する。canary #2 の install は漏洩対策のため全手動 (skill zip 展開 + INSTALL.md / setup script 削除 + ローカル path `pip install`、Web 系ツール不許可) — 手順は 2026-07-04 セッション記録参照。
