# Phase 2 Step 2.5 作業記録: Pattern B external-LLM interface

**完結日:** 2026-06-13

## スコープ

- `qgb design-stages propose-context` (構造化 context export)
- `qgb design-stages adopt` (proposal import + 9-step validation + atomic apply)
- `proposal.schema.json` (additionalProperties:false, NF-007)
- same-world validation (project-wide + 全 REQ per-REQ)
- `qgb patch` POLICY 経路の盲点修正 (Step 2.2 retrofix)
- 3 段移行ワークフロー (additive adopt → REQ meta patch → removal adopt)

## レビューサイクル

1. 段 1: 観点別 5 subagent (correctness / edge-cases / windows / test-quality / backward-compat)
   - backward-compat がモデルエラー (Fable 5 停止) → Opus 4.6 で再走
2. A 系列補修 5 件:
   - A1: policy_schema_invalid / atomic_write_failed テスト (9/9 reason 完全カバー)
   - A2: collect_same_world_blockers dedupe テスト
   - A3: BOM 耐性 (utf-8-sig: loader/validate/patch_apply/proposal)
   - A4: propose-context stdout cp932 fallback
   - A5: RecursionError → schema_invalid 変換
3. Codex 横断: 指摘なし収束
4. テスト: 698 → 726 (+28)

## 申し送り

- BOM 残り read path → Step 2.7 / Phase 3
- --path 重複 (ds_p + pc_p/adopt_p) → ジャーナル記録のみ
- AdoptError 9 reason = 固定 API → 追加は versioned change
