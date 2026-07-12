# Issue #32 短期対応 (A+C) + skill v0.1.7

- 実施日: 2026-07-12 / 仕様: [Issue #32](https://github.com/Yumeno/Quality-gate-builder/issues/32) のオプション検討 (A〜I + 理念ガードレール) から user が **短期 = A+C** を採択
- 位置づけ: Phase 6 判断 (D+E: gate.json provenance + verify-evidence) は保留のまま、qgb 本体を凍結して実害を下げる層

## 実装内容

- **A. 限界の正直な開示** (skill v0.1.7): §6.1 step 9 に「gate.json はどの時点のソースへの判定かを自己記述しない / 対応づけは運用 / qgb は崩れを検証しない」の機構事実を追加。§7.3 に「ALLOW は実行時点の検査通過であり、以後のソース変更を検出しない」を追加
- **C. ラッパー参考実装**: `ci-examples.md` Pattern F 新設 — git 用スナップショット wrapper (PowerShell / bash、`-RequireClean` opt-in) + 非 git 用 manifest 変種 (Python)。sidecar JSON は `latest/` の**外** (qgb の atomic swap 領域を侵さない) に置き、digest は `configuration_digest` と命名 (contract+policy のみ — 入力閉包を主張しない、#32 の sol レビュー準拠)。README にも 1 段落 (運用責務の明示 + Pattern F / #32 への導線)

## 検証と検収

- 実装 subagent が wrapper を**実機実行**で検証 (ALLOW 透過 / RequireClean の clean・dirty 両分岐 / F-1 と F-3 の digest 一致)。F-2 (bash) も Git Bash で実走
- 検収での意味論修正 1 件: **run 後の dirty 判定がほぼ常に true になる欠陥** (qgb run 自身が evidence を書くため) → dirty 判定から `.quality-system/evidence` / `artifacts` を pathspec 除外 (「対象パスに限定した dirty 判定」— 起票文の含意の実装)。除外理由はコード内コメントに記載
- 846 passed / py -3.10・3.13 digest 一致 `817b442b8348de30`
- 独立レビューは省略し指揮側検収に縮退 (skill 変更は自筆 2 bullet のみ、Pattern F は非規範の参考実装で実機検証済み、という比例判断)

## 残タスク

D+E (provenance 本体実装) の要否は Phase 6 計画時に判断 — 判断材料は Issue #32 に集約済み (オプション A〜I、configuration_digest 命名、VCS tagged union、stale ≠ 違反の P3 ガードレール、digest 正規化仕様の prejournal 固定事項)。
