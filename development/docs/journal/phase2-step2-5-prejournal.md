# Phase 2 Step 2.5 — Pattern B external-LLM interface 着手前判断記録 (prejournal)

記録日: 2026-06-12
状態: 実装着手前。Codex 計画レビュー 2 周 (1 周目: 構造確定 / 2 周目: 実運用シミュレーション起因の追加 3 件の影響確認) + user 確定まで完了。

## 1. 確定ライン (Codex 1 周目 + user 確定)

1. **proposal schema は「policy_stages 提案」に主語を絞る**: `qgb/schemas/proposal.schema.json` は `proposal_type: "policy_stages"` + `stages[]` (宣言的全量置換) + `source_metadata` (任意)。req-meta / contract を混ぜる余地を schema レベルで閉じる (P9)。操作列形式は JSON Patch (`qgb patch`) と重複するため不採用 — **proposal = 設計意図 (宣言)、patch = 低レベル編集 (手続き)** の分業
2. **`AdoptError` 新設** (PatchApplyError 流用しない — failure surface が異なる)。reason は固定 enum、検証順も安定 API: `read_error` → `invalid_json` → `schema_invalid` → `unsupported_schema_version` → `unsupported_proposal_type` → `policy_build_failed` → `policy_schema_invalid` → `policy_preflight_failed` → `atomic_write_failed`。`reason` は固定文字列 / `details` は非安定、と Phase 5 skill 向けに区別
3. **証跡 = knowledge 記録なし + result JSON に hash 必須**: adopt 成功時の `--json` に `proposal_sha256` / `policy_before_sha256` / `policy_after_sha256` / `applied_at` / `source_metadata` を返す。監査は git + CI/skill 側保存 (P7 は hash で担保)。「LLM 由来」は proposal の `source_metadata` に任意で載り、qgb はそれを実行意味に使わない
4. **P8 フレーミングは機械可読メタデータ**: propose-context 出力に `document_kind: "qgb.proposal_context"` / `intended_use: "external_tool_input_data"` / `contains_executable_instructions: false`。自然言語の注意書き文は「LLM への命令文」に見えるため不採用
5. **propose-context は最小で安定**: detect 結果 + 現 policy (verbatim) + REQ 一覧 + 制約サマリ (stage 数 3-7 / verification_type enum / canonical layout / id 規約) のみ。contracts 本文 / knowledge.jsonl / project-context.md は含めない (将来の明示 option)
6. **adopt は stages-only + sibling-tmp atomic swap** (patch substrate 方式)。temp-tree 方式 (commit_design) は将来の multi-file adopt 用に温存。`--dry-run` / `--json` あり、`--force` なし、確認プロンプトなし (patch / add-waiver と対称 — F-008 は curated evidence 保護であり、正本編集は git 可逆性に委ねる)
7. **既存 `qgb design-stages [--commit] [--json]` は完全温存**: `propose-context` / `adopt` は明示 subcommand のときだけ分岐 (rule-based 提案と LLM 経由提案は別の入口)
8. **`qgb patch policy` alias は追加しない**: §13.2 の文言は実装済みの path 形 (`qgb patch .quality-system/policy.json <patch.json>`) で充足。skill はフルパスを機械生成するので alias の利便は効かない (NF-010)。e2e fixture で実証
9. **fixture は tests/fixtures/** (examples/ はユーザー契約に近いため Phase 2.5 では早い)。`source_metadata.generator: "fixture"` で非 LLM 生成を明示
10. **exit code**: add-waiver 規約と整合 — 成功 0 / validate-policy blocker 1 / 他エラー 2

## 2. 実運用シミュレーションで発見した矛盾 (user 依頼による Flow 検証)

**Flow 2 (稼働中プロジェクトの policy 再設計)**: adopt の検証が project-wide validate-policy のみだと、stage 再構成 proposal が「policy 単体はグラフ健全」で adopt 成功した直後に、既存 REQ が unknown_stage_id で NOT_READY、waiver entry は orphan blocker 化 — **「adopt 成功と報告したのに世界が壊れている」**。

さらに調査で **Step 2.2 の `qgb patch` POLICY 経路にも同じ盲点** を確認 (`_run_validate_policy` が `policy_override` のみ・req_id=None で呼ぶ。docstring の「project 全体の整合性確認」は過大表現)。

## 3. 追加確定 3 件 (user 承認 2026-06-12、Codex 2 周目で影響確認済み)

1. **adopt の検証 = project-wide + 既存全 REQ の same-world per-REQ 検証**: `.quality-system/req/*.meta.json` を列挙し、各 REQ に `validate_policy_preflight(root, req_id, policy_override=new_policy)`。1 つでも blocker なら reject (`policy_preflight_failed`)。
   - per-REQ 失敗詳細は機械可読で (`req_id` / `kind` / `where` / `message` / `severity`) — どの REQ を先に移行すべきか判断できる粒度 (Codex r2)
   - 壊れた既存 meta (読めない / schema 不一致) も reject、詳細は policy graph 失敗と混ぜず existing-REQ 起因と分かる形で載せる (Codex r2)
   - 計算量 (REQ 数 × preflight) は daily 操作として許容、validate_schema_sources 再実行の最適化は Phase 3 送り (Codex r2)
   - **破壊的 rename の正規手順 = 3 段移行**: additive 追加 adopt → 各 REQ meta を patch で移行 (新旧並存中なので通る) → 削除 adopt。one-shot rename は Phase 3 multi-doc transaction まで reject が正しい。docs に明記
2. **同検証を `qgb patch` の POLICY 経路にも適用**: silent に世界を壊す patch が reject される安全側の挙動変更。patch は Phase 2 新設コマンドなので Phase 1 互換 (default 経路) の対象外 — 変更可 (Codex r2 同意)。reason は既存 `validate_policy_blocker` 流用 (enum 追加なし)。docstring の過大表現も修正。既存テストの期待値変更は許容
3. **`propose-context --out <file>`**: UTF-8 明示のファイル出力 option。PowerShell 5.1 の stdout cp932 化け (hook 事故で実証済み) を迂回する file-based handoff が skill の主消費経路になる想定 (NF-004)。Step 2.5 実装は propose-context のみ、§13.2 に「handoff JSON を出すコマンドは将来 --out を提供する方針」を将来規約として記載 (Codex r2)

## 4. 規模ガード (Codex r2)

1.5 内に収まる見込み。超過リスク 3 つを意図的に回避: per-REQ 詳細 result JSON を凝りすぎない / --out を全 --json コマンドへ広げない / schema・preflight cache を本格設計しない。

## 5. 実装構成 (予定)

- `qgb/core/proposal.py` (新設): `build_proposal_context(project_root)` / `adopt_proposal(project_root, proposal_path, *, dry_run)` / `AdoptError`
- `qgb/schemas/proposal.schema.json` (新設、Step 2.1 の format / `$ref` allowlist 継承)
- `qgb/core/patch_apply.py`: POLICY 経路に全 REQ same-world 検証を追加 (共通ヘルパーを proposal.py 側か preflight 側に置くかは実装時判断)
- `qgb/cli.py`: design-stages に subcommand 分岐 (後方互換維持)
- tests: `tests/test_proposal.py` + fixture (`tests/fixtures/proposal/`) + patch 側の挙動変更テスト

## 6. Step 2.6 / 2.7 / Phase 3 への接続

- Step 2.6: propose-context の context shape が example packs の入力制約になる (順序入れ替え不要、Codex 1 周目)
- Step 2.7: `mode` discriminator と同様、`proposal_type` も予約済み discriminator として strictness review で扱う
- Phase 3: multi-doc transaction (one-shot rename)、validate_schema_sources の cache 最適化、--out の全コマンド展開
