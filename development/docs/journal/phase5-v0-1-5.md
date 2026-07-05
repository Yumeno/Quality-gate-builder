# Phase 5 v0.1.5 skill 文言改善バッチ (5.e split 実走の発見反映)

- 実施日: 2026-07-05 / 仕様: [Issue #30](https://github.com/Yumeno/Quality-gate-builder/issues/30) (journal `phase5-step5-e.md` item 1 の 6 件)
- 編成: Fable 5 指揮 (文言確定・検収) + sonnet 実装。**独立レビューは省略し指揮側の機械的検収に縮退** (全編集が「参照の置換・挿入」で新規主張を含まない prose、過去 2 バッチでレビューが捕捉した欠陥クラス = 取り残し/番号衝突/矛盾は grep 全域捜索 + renumber 参照確認 + diff 全読で機械的に被覆できるため。レートリミット下の資源判断も加味)

## 実装内容 (Issue #30 の 6 件)

1. **「§12」エイリアス全面解消**: body.md 7 箇所 + lint README 2 箇所 + lint script 両実装のメッセージ文字列 (.py 4 箇所 / .ps1 3 箇所、pure-ASCII 維持・parity 維持) を「段階設計プロンプト §5.5 (full: 同一 SKILL.md 内 / split: `prompts/design-stages.md`)」系に置換
2. **§6.1 手順順序**: 新 step 6「段階設計で policy.json#stages を確定する (scaffold の前提)」を挿入、旧 6/7/8 → 7/8/9 に renumber (外部参照は step 5 のみで影響なし)
3. **scaffold 生成物の正確化**: §4 構造図 / §6.1 step 7 / §6.2 step 2 — 「.md は生成されない、agent が新規 Write」を明記
4. **`--yes` 明記**: §6.2 step 7 / §6.3 step 4 / repo CLAUDE.md の CLI 一覧
5. **patch の project-wide preflight** を §6.4 step 2 に明記
6. **contract TODO 初回充填の線引き**: §6.4 step 1 (初回充填 = 設計 = 直接 Write 可、以後 = patch) + レビュー観点 §4.3 に同じ線引きを追記して矛盾解消

version lockstep: metadata.yaml / pyproject.toml → 0.1.5。

## 検証

- 846 passed, 3 skipped / lint 両実装 parity smoke 21/21 一致 (メッセージ文字列変更後も)
- 「§12」「12.5.5」残骸ゼロ (skills/source 全域 grep)、renumber の参照切れなし
- digest `615b17206d93a251` (v0.1.4) → `6c3b5b83d915af62` (v0.1.5)、py -3.10 / 3.13 で一致
- リリース: CI green → `skill-v0.1.5` タグ (三点一致ガード対象) → Issue #30 close
