# Phase 2 Step 2.2 — patch substrate 作業記録

着手: 2026-06-05
完結: 2026-06-05 (Codex 計画レビュー 18 指摘 + 5 着手前修正要件吸収 → 本体実装 → 観点別 5 subagent → Codex 横断 1 周目 → A1-A6 補修 → Codex 2 周目「指摘なし収束」)

## Step 2.2 のスコープ (detailed-design.md §13.2)

「編集を安全にする」Phase 2 主軸の **共通基盤**。Step 2.3 / 2.4 / 2.5 が
すべて Step 2.2 の patch substrate を内部で呼ぶ前提で作られる。

### 完成した機能

- **JSON Patch subset (RFC 6902)**: `add` / `replace` / `remove` / `test` の 4 op
- **`qgb patch <target> <patch.json>`** CLI (低レベル、`--dry-run` / `--json`、`--force` なし)
- **atomic apply**: sibling tmp + `os.replace` (Phase 1 Step 6d / Step 7 で確立した pattern を継承)
- **validate-policy integration**: patch 適用後の view を Step 2.1 で確立した `_collect_dollar_refs` / `_is_internal_pointer_ref` 経路も含めて検証
- **override seam (案 X)**: `validate_policy_preflight(policy_override / req_meta_override / contract_overrides)` で in-memory dict をそのまま検査
- **JSON Pointer (RFC 6901) encode/decode**: `qgb/core/json_pointer.py` に集約、ASCII digit 限定 (補修 A1)

### Phase 3 送り

- `move` / `copy` op (RFC 6902 仕様の残り)
- patch の reverse (rollback)
- multi-file lock / multi-file rollback (quality-system 全体 transaction)
- `qgb dev` の changed-files 絞り込み (Step 2.4 で扱う)

## 着手前: prejournal (案 X 採用判断)

prejournal (`journal/phase2-step2-2-prejournal.md`) で詳細記録。
要点:

- Codex 計画レビュー (skill 経由) 18 指摘 + 5 着手前修正要件吸収
- 最大の構造リスク (validate-policy が file 読込前提) について案 X (preflight に override seam) と案 Y (sibling tmp で実 file 入れ替え) を検討
- 思想憲章照合 (P3 / P7 / P9 / NF-004) で案 X が全面的に有利と判定
- user 2026-06-05 判断で案 X 採用確定
- 規模 1.2 → 1.7 上振れ、Step 2.3/2.4/2.5 で 0.6 回収する前借り

## 実装の流れ

prejournal §11 の順で実装:

### 1. `qgb/core/json_pointer.py` 新設

- `encode(tokens) -> str`
- `decode(pointer) -> list[str]` (PointerError reason: `not_a_pointer` / `unterminated_escape` / `invalid_escape`)
- `parse_array_index(token, allow_append=False)` (RFC 6901 §4 準拠、leading zero 禁止、ASCII digit 限定 [A1 反映])
- `ARRAY_APPEND_TOKEN = "-"` 定数

Step 2.1 まで `qgb/core/schema.py` に埋め込まれていた `_json_pointer_escape` / `_to_pointer` をここに集約 (P9)、schema.py 側は alias として残す (後方互換)。

### 2. `qgb/core/patch.py` 新設

- `apply_patch(doc, patch) -> doc'` (deepcopy ベース、副作用ゼロ)
- 4 op を独立関数で実装 (`_apply_add` / `_apply_replace` / `_apply_remove` / `_apply_test`)
- `PHASE_2_OPS` 集合と `PHASE_3_OPS` 集合を明示的に定義、`move` / `copy` は `unsupported_op` で reject
- `PatchError` reason code 8 種で機械可読化 (Step 2.5 Pattern B 用)

### 3. `qgb/schemas/patch.schema.json` 新設

- op enum: `add` / `replace` / `remove` / `test` のみ
- `additionalProperties: false` (`from` フィールドも schema reject)
- `if/then` で op 別 required/forbidden:
  - `add` / `replace` / `test`: `value` required
  - `remove`: `value` **完全禁止** (A3 反映、`properties: {value: false}` 形式)
- `SCHEMA_FILES["patch"]` で qgb の schema 集合に登録

### 4. `qgb/core/preflight.py` 改修 (案 X の本丸)

- `validate_policy_preflight` に **3 つの override 引数** を追加 (`policy_override` / `req_meta_override` / `contract_overrides`)
- default (None) 経路は Phase 1 完全互換
- `resolve_adopted_stages` の `load_contract` 呼び出し直前に `contract_overrides` を bypass 経路として check
- 後段の required_fields / verification_type 一致 / adopted append ロジックは無変更 (P9 本質保持)

### 5. `qgb/core/patch_apply.py` 新設

- `classify_target(project_root, target_rel)` で POLICY / REQ_META / CONTRACT を識別 (REQ_META も segment 数厳密チェック [A2 反映])
- `apply_patch_to_target(project_root, target_rel, patch_path, *, dry_run=False)` がフロー全体を統合:
  1. target を読込
  2. patch を読込 + schema 検証
  3. memory 上で `apply_patch`
  4. 適用後 doc を target schema で検証
  5. 適用後 doc を `validate_policy_preflight` override seam 経由で検証
  6. atomic swap (sibling tmp + `os.replace`、`suffix=".tmp"` [A4 反映])
- dry_run=True 時は 1-5 完全実行、6 のみ skip (`would_write=True`、`written=False`)
- `PatchApplyError` reason code 9 種

### 6. `qgb/cli.py` に `qgb patch` 追加

- `qgb patch <target> <patch.json> [--path <root>] [--dry-run] [--json]`
- exit code: `validate_policy_blocker` → DENY (1)、その他失敗 → NOT_READY (2)、成功 → OK (0)
- `--force` は意図的に **追加しない** (Codex 計画レビュー指摘 8)
- `--dry-run` で text 出力 "would write" + structured `--json` で `would_write: true`

## 段 1 観点別 5 subagent レビュー

memory `review-process` 段 1 を memory `parallel-strategy` テンプレ v3 厳守で実施。
**5 観点同時並列、reject ゼロで完走**。

### 段 1 集約 (中以上指摘 6 件)

| # | 観点 | 重要度 | 場所 | 内容 |
|---|---|---|---|---|
| 1 | edge-cases | 高 | json_pointer.py:229 | `str.isdigit()` が Unicode 数字を受け入れる |
| 2 | windows-specific | 高 | patch_apply.py:332 | `tempfile.mkstemp` の `suffix` 明示なし |
| 3 | correctness | 中 | patch_apply.py:157-159 | REQ_META segment 数チェック不足 |
| 4 | correctness | 低→中昇格 | patch.schema.json | `remove` op で `value` 完全禁止できていない |
| 5 | test-quality | 中 | conftest.py | helper 重複 |
| 6 | correctness | 低 | json_pointer.py:152-154 | docstring 順序説明が誤解を招く |

backward-compat は 9 つの固定点すべてクリア (中以上指摘なし)。

## 段 3 Codex 横断レビュー (1 周目、skill 経由)

context: `codex_ctx_p2_step22_cross_r1_20260605-134539.txt` (TEMP)

判定:

- A0 (cli.py 型注釈の実行時 NameError 懸念) → **実コード確認で問題なし** (cli.py L3 で `from __future__ import annotations` 既存、`py -3 -c "import qgb.cli"` で sanity check OK)
- A1〜A4 必須採用、A5/A6 採用、A7 維持
- 思想憲章 P3/P6/P7/P9/NF-004/NF-010 すべて整合
- **追加申し送り 2 件** (Step 2.3/2.4/2.5 接続):
  - `contract_overrides` の key は `contract_ref` canonical 文字列に統一
  - 複数 document 変更を扱う Step 2.4/2.5 では全 override を同一 world として渡す規約を明文化

## 補修 A1-A6 反映

### A1 (高): ASCII digit 限定

```python
# qgb/core/json_pointer.py parse_array_index
if not token.isdigit() or not all(c in "0123456789" for c in token):
    raise PointerError(... reason="invalid_array_index" ...)
```

理由: RFC 6901 §4 は "0-9 ASCII digits only" を要求するが Python の `str.isdigit()` は Arabic-Indic (`٠`) や全角 (`１`) を True と判定する。明示的に ASCII 0-9 集合に限定。テスト 4 件追加 (全角 / Arabic-Indic / 上付き / 混在 reject)。

### A2 (中): REQ_META segment 数厳密チェック

```python
# qgb/core/patch_apply.py classify_target
if norm.startswith(".quality-system/req/") and norm.endswith(".meta.json"):
    segments = norm.split("/")
    if len(segments) != 3:
        raise PatchApplyError(reason="target_path_invalid", ...)
```

CONTRACT 同様の segment 数厳密チェックを REQ_META にも追加。`.quality-system/req/sub/X.meta.json` のような nested path を reject。テスト 1 件追加。

### A3 (中): `remove` op の `value` 完全禁止

```json
// 旧: "not": { "required": ["value"] }
// 新: "properties": { "value": false }
```

JSON Schema Draft 2020-12 の `properties.value: false` で value 出現自体を schema reject する形に変更。テスト 1 件追加 (`test_remove_with_value_is_schema_violation`)。

### A4 (中): `tempfile.mkstemp` に `suffix=".tmp"`

Phase 1 Step 6d / 7 で確立した `qgb/core/design_stages.py` の atomic write pattern と一貫性を保つ。

### A5 (中): `tests/conftest.py` 新設

`copy_generic_minimal` / `write_patch` / `read_json` / `snapshot_dir` を fixture として集約 (callable を返す形)。既存 test_patch_apply.py / test_patch_cli.py 内のローカル helper は当面残し、Step 2.3 以降で漸進的に fixture 経由に置き換える方針 (Codex 2 周目で漸進方針 OK と判定)。

### A6 (低): `_unescape_token` docstring 書き換え

「先に `~1` を処理してから `~0`」のような誤解を招く説明を、実装の **逐次走査** semantics に書き換え。encode 側 (replace チェーン、順序重要) との違いを明記。

## 段 5 Codex 2 周目「指摘なし収束」

context: `codex_ctx_p2_step22_cross_r2_20260605-140105.txt` (TEMP)

> 判定: **指摘なし収束** でよいです。中程度以上の新規 finding はありません。
> A1-A6 の反映内容は、1 周目の補修意図に対して妥当に収まっています。
> 
> - Step 2.2 収束宣言: 可
> - contract_overrides key 統一: 本体コードへの追加補修は不要、完結 journal への明記で十分
> - 複数 doc 変更時の同一 world 規約: Step 2.3/2.4/2.5 側の呼び出し規約として明文化する扱いで妥当
> - A5 の漸進方針: 問題なし

## 成績

- pytest: 470 (Phase 1) + 17 (Step 2.1) → 608 (本体実装) → **614** (補修反映)、+144 件、全緑
- ruff: clean
- 主要 verification_type 4 種 (file_exists / substring_match / command / json_schema) は引き続き全 example でカバー
- 既存 example 3 例 (generic-minimal / python-cli-pytest / markdown-docs) は **無変更で全通過** (Step 2.2 で `.quality-system/` を touch せず)

## Phase 2 後続 Step への申し送り

### Step 2.3 (domain edit commands: `add-waiver` / `add-knowledge`)

- 内部実装は Step 2.2 の `patch_apply.apply_patch_to_target` を呼ぶ設計
- `qgb add-waiver REQ-X S1 --reason "..."` は内部で waiver flag を立てる patch を生成 → `apply_patch_to_target(target_rel=req-meta path, ...)`
- `qgb add-knowledge knowledge.json` は append-only + partial-tail tolerant を維持する別経路 (knowledge.jsonl は patch substrate 対象外、専用 atomic append が必要)
- knowledge orphan check は `validate_policy_preflight` に新 check として追加 (Step 2.3 で判断)

### Step 2.4 (`qgb check` / `qgb dev`)

- **override seam を最大限活用**: `qgb check --proposal-patch proposal.patch.json` が `apply_patch_to_target(dry_run=True)` を内部で呼ぶ
- curated `evidence/latest/` は一切 touch しない (case の本質)
- 揮発出力は `.qgb/tmp/check/<timestamp>/gate.json` (新ディレクトリ規約)
- Codex 横断レビュー追加申し送り: `qgb check` で複数 doc を 1 つの proposal で扱うとき、policy/meta/contract の override をすべて同一 world として渡す規約を明文化

### Step 2.5 (Pattern B external-LLM interface)

- `qgb design-stages adopt <proposal.json>` が Step 2.2 の patch substrate を内部で呼ぶ
- proposal JSON schema (`qgb/schemas/proposal.schema.json`) は Step 2.1 で確立した format / `$ref` allowlist を継承
- `qgb patch policy <patch.json>` (直接 JSON Patch) と `qgb design-stages adopt` (proposal → patch 変換) の二経路提供
- **Codex 横断レビュー追加申し送り**: `contract_overrides` の key は **必ず canonical `contract_ref` 文字列に統一** (target path から作った key と req-meta 内 ref 表記のズレで override が効かない事故を防ぐ)

### Step 2.7 (strictness review)

- 命名揺れ / log フォーマット規約見直し (Step 2.1 から継続)
- `additionalProperties: false` 全面適用判断
- `--strict` 実体実装 (Step 2.1 で skeleton 撤回した分)
- JSON Patch `move` / `copy` を Phase 3 として明示記録

## プロセス軸の振り返り

### Phase 1 から確立したサイクルの再現

- **計画 Codex 相談 → 着手前構造修正 → 実装 → 段 1〜5 完走** が Step 2.2 でも安定再現
- prejournal (案 X/Y 検討経緯) の事前書面化が今回新たに確立されたパターン: **規模が大きい Step で構造変更判断がある場合は着手前 prejournal を作る**
- memory `parallel-strategy` テンプレ v3 (Bash 完全禁止 + 経路例示 + 論証指針 + 退路) が Step 2.2 でも reject ゼロを達成、Phase 2 標準として確立
- Codex 経路: 段 1 (subagent 5) と段 3/5 (Codex 横断 / 収束) は別経路として明示分離、skill 経由運用が定着

### memory 改定 (Step 2.2 中になし)

Step 2.1 で大量改定したため、Step 2.2 では memory 改定なし (既存テンプレ v3 が機能した)。

### 規模感の実績 (prejournal §7 / §8 との対比)

| 内訳 | 見積 (prejournal) | 実績 | 差分 |
|---|---:|---:|---:|
| json_pointer.py | 0.2 | 0.2 | 0 |
| patch.py | 0.3 | 0.3 | 0 |
| patch.schema.json | 0.1 | 0.1 | 0 |
| patch_apply.py | 0.3 | 0.3 | 0 |
| preflight.py override seam | 0.3 | 0.3 | 0 |
| cli.py qgb patch | 0.2 | 0.2 | 0 |
| テスト 30 件想定 → 実績 144 件 | 0.3 | 0.4 | +0.1 |
| 補修 A1-A6 | (見積外) | 0.2 | +0.2 |
| **合計** | **1.7** | **2.0** | +0.3 |

実績 2.0 (Step 5 = 1.0 基準)、prejournal 見積 1.7 を 0.3 上回ったが、補修サイクル込みなので想定範囲内。Phase 2 全体 7.5 → 7.6 でほぼ予定通り。

### Phase 2 全体進捗

- ✅ Step 2.1 schema baseline (0.8、完結)
- ✅ Step 2.2 patch substrate (2.0、本ステップ完結)
- ⏳ Step 2.3 domain edit commands (0.9 見込み、Step 2.2 で patch substrate 整備済)
- ⏳ Step 2.4 daily verification channel (0.8 見込み、案 X seam 活用)
- ⏳ Step 2.5 Pattern B external-LLM (1.2 見込み、同上)
- ⏳ Step 2.6 example packs (1.5 見込み)
- ⏳ Step 2.7 strictness review (0.5 見込み)
- 計 **7.7** (上振れ 0.2 で吸収)

## 本 step 2.2 で確立された Phase 2 規律 (追記なし)

Step 2.1 で確立した memory 規律 (`qgb-llm-boundary` / `parallel-strategy` テンプレ v3 / `codex-context-files` v2 命名) を本ステップでも厳守。新規追加なし。

prejournal pattern (案 X/Y のような構造変更判断を含む着手前判断記録) は Phase 2 内の今後のステップでも同様に運用予定だが、必ずしも全ステップで必須化しない (構造変更がない Step では prejournal なしで進める)。
