# Phase 2 Step 2.3 — domain edit commands 作業記録

着手: 2026-06-10
完結: 2026-06-10 (Codex 計画レビュー 10 観点 → 着手前 3 仕様確定 → 本体実装 → 段 1 観点別 5 subagent (hook 注入初実地) → 補修 A1-A3 → 段 3 Codex 横断 → 補修 B1-B3 → 段 5 Codex 2 周目「指摘なし収束」)

## Step 2.3 のスコープ (detailed-design.md §13.2)

Phase 1 では手編集だった waiver 付与と knowledge 追記を CLI 化。Step 2.2 の patch substrate を最初に消費する業務コマンド層。

### 完成した機能

- **`qgb add-waiver <REQ> <stage-id> --reason "..."`**: req-meta は patch substrate 経由 (schema + validate-policy gated、atomic swap)、knowledge.jsonl へ即時 evidence 記録 (F-007)。`--decided-by` / `--force` / `--dry-run` / `--json`
- **`qgb add-knowledge <file>`**: object/array 両対応、all-or-nothing schema 検証、既存 id skip (idempotent)、created_at 補完なし、`--force` なし
- **knowledge orphan check**: `validate_policy_preflight` に統合 (`knowledge_orphan` kind)。waiver/REQ 不在 = blocker、waiver/stage 不在 = blocker、非 waiver = warning。**run_preflight には入れない** (P9: REQ-A の orphan が `qgb run REQ-B` を塞がない)
- **`qgb/core/knowledge.py`** (store 層) + **`qgb/core/edit_commands.py`** (orchestration 層) の 2 module 構成
- **`apply_patch_doc_to_target`**: patch substrate に in-memory patch doc 受けの内部 API を切り出し (file 版は doc 版を呼ぶ 2 段構成)

## 着手前: Codex 計画レビューで確定した 3 仕様

1. **`--force` semantics**: 異 reason 上書きは req-meta のみ更新、knowledge.jsonl の既存 entry は audit history として保持 + CLI 出力で乖離を明示警告。正式な reason 改訂は Phase 3 revoke/supersede
2. **atomicity**: 「multi-file 完全 atomic」ではなく **file 単位の保証 + idempotent recovery** — meta 状態と knowledge 状態を独立判定し、欠けている方だけ埋める収束動作 (req-meta 更新後に knowledge append が失敗しても再実行で収束)
3. **add-knowledge**: created_at 自動補完なし (入力 file が正本、P7) / object & array 両対応 / 既存 id skip / `--force` なし (append-only と意味論衝突、spec の「--force 有り」は add-waiver で充足) / all-or-nothing

その他の計画レビュー決定: 2 module 構成 (knowledge / edit_commands)、`build_waiver_knowledge_entry` を run 時と add-waiver の共通 builder に、`waiver_knowledge_id` の正本を knowledge.py へ移管 (evidence は委譲)、orphan severity 非対称 (waiver=blocker / 非 waiver=warning)。

## 実装で発見した重要バグ (実装中に自己検出)

`build_waiver_knowledge_entry` の初版が id を `KNOWLEDGE-WAIVER-...` としていたが、既存の knowledge.jsonl entry id は `WAIVER-<REQ>-<stage>` (gate.json#basis 側が `KNOWLEDGE-` を前置する規約)。そのまま進めると **run 時の idempotent skip が壊れて entry が二重化** するところだった。knowledge.py の `waiver_knowledge_id` を正本とし、evidence 側を委譲に変更して一元化。

## 段 1 観点別 5 subagent レビュー (hook 注入の初実地テスト)

**reject ゼロ、Bash 申請ゼロで完走**。PreToolUse hook (`inject-subagent-template.ps1`) によるテンプレ自動注入の初実地で、5 subagent 中 4 が「テンプレ視認 yes」を自己報告 (1 件 no 報告だが挙動は規律通り)。手動テンプレコピペなしでの運用が成立。

### 集約 → 補修 A1-A3

| # | 起源 | 重要度 | 内容 |
|---|---|---|---|
| A1 | correctness | 高 | dry-run の戻り値が meta_changed=False 固定 → would-be 値 (meta_needs_patch / knowledge_needs_append) を返すよう修正 |
| A2 | edge-cases | 中 | knowledge append の OSError が EditError に包まれず CLI に traceback → io_error で wrap、「再実行で収束」を message に明記 |
| A3 | test-quality | 中 | force+dry-run / recovery+dry-run / add_knowledge dry-run skip / CLI --dry-run ×2 / io_error のテスト 6 件追加 |
| A4 | test-quality | 低 | `_entry`/`_kentry` helper 重複 → **Step 2.7 送り** |

windows / backward-compat は中以上指摘なし (encoding utf-8 明示、CRLF 耐性、BOM 方針整合、8 固定点クリア)。

## 段 3 Codex 横断レビュー → 補修 B1-B3

### B1 (必修): `--force` + knowledge 欠落 recovery の境界ケース

meta=waived/reason A + knowledge entry 欠落で `--force --reason B` を打つと、新規 entry は reason B で作られるのに warning が「既存 entry が reason A を保持」と嘘を言う問題。補修: knowledge 状態判定を force 分岐より前に移動し、warning を実態で分岐 (entry 存在 → 歴史保持文言 / 欠落 → 「新 entry が新 reason を記録、旧 reason の evidence は存在しない」)。仕様として「knowledge 欠落時の force は現 reason の evidence を新規作成」を確定。

### B2: add-waiver 生成 entry の schema validate

add-knowledge は入力を schema 検証するのに add-waiver は生成 entry を無検証で append していた。`--decided-by ""` で不正 entry が書ける穴。補修: append 直前に `schema_validate(entry, "knowledge")`、違反は `knowledge_schema_violation` (add-knowledge と同じ reason code、idempotent recovery 案内付き)。

### B3: append atomicity の保証境界

「file 単位 atomic」「1 行 = 1 write」という文言が実装より強かった (json と "\n" を別 write、os.replace 型でもない)。補修: (実装) 単一 write に統合 (partial-tail 窓を 1 entry 内に縮小)、(文言) 「append-only + partial-tail tolerant + idempotent recovery。req-meta の atomic swap とは異なる」に正確化 (NF-010: 保証の過大表現を避ける)。

## 段 5 Codex 2 周目「指摘なし収束」

> 指摘なし収束。B1/B2/B3 の補修内容は Step 2.3 の収束条件を満たしています。

軽微注記 (gate 非阻害): 複数回 `--force` された場合の warning の「original reason」が req-meta 直前 reason か knowledge 実記録 reason かの明確化 → **Step 2.7 送り**。

## 成績

- pytest: 614 (Step 2.2 完結時) → 658 (本体 +44) → 664 (A 補修 +6) → **666** (B 補修 +2)、全緑
- ruff: clean
- 新テスト: test_knowledge_store.py (17) / test_edit_commands.py (31) / test_knowledge_orphan_preflight.py (4)
- 既存 example 3 例 + fixture 無変更通過

## Phase 2 後続 Step への申し送り

### Step 2.4 (`qgb check` / `qgb dev`)

- knowledge orphan が project-wide / per-REQ 両経路で出る意図を CLI 表示で明文化 (Codex 1 周目申し送り)
- **unrelated orphan blocker が patch 経由 edit を止めるかの確認**: `apply_patch_doc_to_target` の validate-policy 検査は project 全体を見るので、無関係な REQ の orphan blocker が add-waiver / patch を NOT_READY にしうる — Step 2.4 で「check の診断範囲」を設計するときに併せて検討
- `qgb check` は `add_waiver(dry_run=True)` / `apply_patch_doc_to_target(dry_run=True)` の組合せで実装できる

### Step 2.5 (Pattern B)

- **knowledge.jsonl は JSON Patch 対象外を維持**: proposal 適用でも knowledge への書き込みは `qgb.core.knowledge` 経由に限定 (edit_commands docstring に明文化済)
- **`EditError.reason` / `PatchApplyError.reason` を安定 API として扱う**: proposal/adopt の機械判定が依存する

### Step 2.7 (strictness review)

- helper 重複整理 (`_entry` / `_kentry` / `_write_knowledge` の conftest 集約) — A4
- 複数回 force 時の warning 文言明確化 — Codex 2 周目軽微注記
- force + knowledge missing / 生成 entry schema validation / append 保証境界の regression test 維持確認 — Codex 1 周目申し送り

## プロセス軸の変化 (Step 2.3 で初めて成立したもの)

- **hook 自動注入での段 1 運用**: 手動テンプレコピペなしで 5 subagent が規律通り完走。subagent prompt はレビュー内容に専念できるようになった
- **`-m *` 傘 + `cd *` + read-only grep/find 傘**: 本 Step では Bash 許可申請が実装フェーズ含めゼロ (settings 整理の効果)
- 規模実績: 約 0.9 (計画 0.9 と一致 — Step 2.2 の前借り効果が予測通り発現)
