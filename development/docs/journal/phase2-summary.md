# Phase 2 完結サマリ: 「編集を安全にする」

**期間:** 2026-06-04 〜 2026-06-13  
**テスト:** Phase 1 完了時 470 → Phase 2 完了時 731 (+261)  
**コミット:** 2.1 着手 〜 2.7 完結

## 規模実績

| Step | 計画 | 実績 | 内容 |
|------|------|------|------|
| 2.1 | 0.8 | 0.8 | schema baseline (format opt-in + $ref allowlist) |
| 2.2 | 1.2 | 2.0 | patch substrate (案 X override seam + 4 op + atomic) |
| 2.3 | 1.0 | 0.9 | domain edit commands (add-waiver / add-knowledge / orphan) |
| 2.4 | 1.0 | 1.0 | daily verification channel (qgb check / qgb dev) |
| 2.5 | 1.5 | 1.5 | Pattern B external-LLM interface (propose-context / adopt) |
| 2.6 | 1.5 | 0.5 | example packs 3 例 (FastAPI / Go / Node CLI) |
| 2.7 | 0.5 | 0.3 | strictness review + migration notes + journals |
| **合計** | **7.5** | **7.0** | |

Step 2.2 が上振れ (案 X の override seam が想定より重い)、2.6 が下振れ (例の生成はパターン確立後は軽い)。

## Phase 2 で確立した設計境界

1. **Pattern B (LLM 境界)**: qgb は LLM を直接呼ばない。context export + proposal import + validate + atomic apply の 3 interface に徹する
2. **Same-world validation**: policy 変更時は project-wide + 既存全 REQ の整合性を同一 override world で検証する (Step 2.5 で Flow 2 矛盾を発見し確立)
3. **AdoptError 9 reason = stable API**: Phase 5 skill が machine-match する前提で文字列固定
4. **Curated 不変の check mode**: `qgb check` は curated evidence / knowledge.jsonl を一切 touch しない
5. **Patch は 4 op 限定**: add / replace / remove / test。move / copy は Phase 3

## テスト推移

| Step | テスト数 | 増分 |
|------|----------|------|
| 2.1 | 487 | +17 |
| 2.2 | 614 | +127 |
| 2.3 | 666 | +52 |
| 2.4 | 698 | +32 |
| 2.5 | 726 | +28 |
| 2.6 | 731 | +5 |

## Example 体制

Phase 2 完了時点で 6 例:
1. generic-minimal (Phase 1 Step 4)
2. python-cli-pytest (Phase 1 Step 8)
3. markdown-docs (Phase 1 Step 8)
4. python-fastapi-pytest (Phase 2 Step 2.6)
5. go-cli (Phase 2 Step 2.6)
6. node-cli-vitest (Phase 2 Step 2.6)

## レビュープロセスの成熟

Phase 2 で段 1 (観点別 5 subagent) → 段 3 (Codex 横断) → 収束ループのパイプラインが安定運用された。主な改良:
- subagent_type=Explore の排除 (Step 2.4 事故 → default agent type に統一)
- PowerShell 禁止 + パスコピペ規律のテンプレ化
- hook 注入 (inject-subagent-template.ps1) による冒頭テンプレ自動挿入
- 許可申請ゼロの安定達成 (Step 2.3 以降)

## Phase 3 への申し送り

detailed-design.md §13.5 + journal/phase2-step2-7.md に 17 項目を列挙。
Step 2.7 完了後に user と繰越判定を相談する必須プロセス。
