# Issue #35: Windows の .cmd shim 診断 hint (qgb 本体) + skill v0.1.8

- 実施日: 2026-10-22 / 仕様: [Issue #35](https://github.com/Yumeno/Quality-gate-builder/issues/35)、prejournal `phase6-issue35-prejournal.md`
- 由来: Issue #33 (PR #34) の動作確認で `examples/node-cli-vitest` の S1 (`npx`) が Windows で一度も通らない状態だったことが判明。example 側 (B1) は PR #34 で修正済み
- 編成: Fable 5 指揮 (方針・仕様固定・文言・検収) + sonnet 実装 (B3) + sonnet 独立レビュー 2 本 + Codex 横断 1 回

## 実装内容

- **B3 (qgb 本体、診断のみ)**: `qgb/core/command.py` に `_windows_shim_hint` を追加。`FileNotFoundError` 時、Windows で argv[0] が bare name (区切り文字・`:`・拡張子なし) かつ PATH の絶対パスエントリ上に `<name>.cmd` / `<name>.bat` があれば、stage log に `hint:` 行を 1 行出す。判定 (failed / exit_code=None)・gate.json schema・reason enum は不変。`shutil.which` は使わず PATH を自前で決定論的に探索、例外は握りつぶす
- **B2 (skill v0.1.8)**: command contract protocol step 4 に Windows shim の注意と推奨順 (① `node` + CLI エントリ直指定 ② Windows 専用なら `.cmd` 明示 ③ 拡張子なし shim 名は使わない)、hint の発火条件と「hint が出なくても shim 起因の可能性は残る」。Node.js checklist に「npm 系 CLI の起動」行 (CLI エントリは `package.json` の `bin` と実在を確認してから書く)
- 文書: `framework-shape.md` §4 runner 契約に 1 bullet、`phase1-manual.md` トラブルシュートに 1 行。version lockstep 0.1.8 + golden 再生成

## レビュー

- **段 1 を 5 本並列 → 2 本 (レンズ統合) に縮退**: 本体コード変更が約 55 行で局所的なため。① correctness / NF-004 / P9、② philosophy / spec-drift / few-shot hazard。Codex も縮退を妥当と判定
- 段 1 の結果: Critical/Major なし。対応 5 件 — ドライブ相対 argv0 (`C:foo`) の除外、PATH 相対エントリを探索しない (子の cwd と qgb の cwd で基準が曖昧)、skill の hint 条件記述を実装に合わせて限定、CLI エントリ推測の抑止、argv[1] 以降の `/` 区切り可の明記。許容: 引用符付き PATH エントリ (CreateProcess も剥がさない)、到達不能 UNC エントリの is_file() ブロック (failed 経路のみ)
- 段 3 Codex 横断 r1: **新規 finding ゼロ**。hint の絶対パス表示は既存 log (`resolved cwd:`) と同じ信頼境界で問題なし、detailed-design.md への追記は不要 (Issue #32 短期対応と同粒度) と判定
- **K=2 の縮退**: r1 がゼロで r1 以降に変更がないため、同一入力の r2 は行わず r1 で収束とした

## 検証

- `pytest`: 857 passed / 1 failed / 3 skipped。失敗は `test_no_false_positive_timeout_when_child_exits_near_deadline` のみで、手元 Python 3.13.1 で子の 0.9s sleep + 起動時間が timeout 1.0s に収まらないタイミング依存 (本変更前から再現、main の CI は green)
- `py -3.10 tools/build_skill.py --check` OK、`py -3.10` で helper が実 PATH 上の `npx.cmd` を検出し hint を返すことを確認 (3.10 環境に pytest は未導入)
- Windows e2e テストで、偽 shim を PATH 先頭に置いた `qgb run` が DENY + hint 行 + `result: failed (command not found)` 最終行になることを確認

## 関連

- examples の実行検証の欠如 (手書き evidence-reference + CI が examples の command を実行しない) → Issue #36
- 上記タイミング依存テストの手元失敗は未起票 (CI では未再現)
