# Phase 2 Step 2.7 作業記録: strictness review

**完結日:** 2026-06-13

## additionalProperties 判断

**部分適用 (現状維持)**:

- gate.schema.json (curated): false — 採用判定証跡は厳格固定 (Phase 1 から不変)
- proposal.schema.json (root): false — 外部入力境界 NF-007 (Step 2.5 新設)
- 上記以外: true — Phase 3 adapter 拡張で言語固有フィールド追加が必要

`--strict` フラグの実体実装は Phase 3 送り (Step 2.1 の「先出ししない」判断を継続)。

## 成果物

- `migration-phase1-to-phase2.md`: Phase 2 全変更の移行ガイド
- `detailed-design.md`: Step 2.5〜2.7 完結記録
- Phase 2 全 Step のジャーナル完備 (step2-1 〜 step2-7 + prejournal 2 件)
- Phase 2 summary ジャーナル

## Phase 3 申し送り項目 (§13.5 相談用、理念再精査済み)

### 解消済み (繰越から除外)
- BOM 残り read path → **即修正済み** (NF-004 の徹底、中途半端な対応は違反)

### WONTFIX (理念に照らして不要と判断)
- JSON Patch `move` / `copy` op → add+remove で代替可能 (NF-010: 不要な機能を追加しない。rename UX が必要なら domain command で実装、patch substrate に op を増やさない)
- snapshot helper 統合 → テストの独立性が統合より価値がある (str 比較と bytes 比較は検出する失敗モードが違うため P9 違反ではなく責務分離)

### Phase 3 繰越 (13 件)

Phase 3 前提条件 (adapter 量産前に対処):
1. Popen / process tree kill (adapter がコマンド実行を多用)
2. `.bat` argument escaping (Node/dotnet adapter が .cmd ラッパーを使う)

Phase 3 で必要だが独立:
3. `--strict` フラグ実体実装
4. waiver の削除 / revoke / supersede
5. `qgb dev` の changed-files 絞り込み (adapter 層知識が必要、adapter 後)
6. multi-doc transaction (one-shot rename)
7. validate_schema_sources の cache (計測後判断、P3 不変仮定禁止)
8. --out の全コマンド展開
9. watch mode (供給チェーン検討が必要)
10. 全 REQ 一括 check

Phase 1 繰越 (P3/P7 再精査で繰越維持):
11. `command` runner の真の memory cap (「稀だから」は不変仮定)
12. fsync / power-loss durability (P7: 証跡消失を「稀」で片付けない。対象は adopt/waiver/knowledge/evidence に限定)
13. bare `qgb` entry point (低優先。配布 UX 要求が明確になってから)
14. 依存解決結果の固定 (hash/lock) (Codex 指摘で WONTFIX 撤回: jsonschema の推移依存が複数あり pip freeze だけでは P7 不足。SBOM までは不要、lock/hash/CI resolved deps が最低ライン)
