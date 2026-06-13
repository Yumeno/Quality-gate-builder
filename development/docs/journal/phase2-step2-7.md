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

## Phase 3 申し送り項目 (§13.5 相談用)

Phase 2 からの繰越:
1. BOM 残り read path (runner.py / scaffold.py / design_stages.py / edit_commands.py / knowledge.py)
2. `--strict` フラグ実体実装
3. JSON Patch `move` / `copy` op
4. waiver の削除 / revoke / supersede
5. `qgb dev` の changed-files 絞り込み (REQ ↔ source 依存マッピング)
6. multi-doc transaction (one-shot rename)
7. validate_schema_sources の cache 最適化
8. --out の全コマンド展開
9. watch mode (filesystem 監視)
10. 全 REQ 一括 check
11. snapshot helper 統合 (test_patch_apply str版 / conftest bytes版)

Phase 1 からの繰越:
12. Popen / process tree kill (Windows Job Objects / Unix process groups)
13. `.bat` argument escaping
14. `command` runner の真の memory cap
15. fsync / power-loss durability
16. bare `qgb` entry point
17. CI 依存 audit / SBOM 生成
