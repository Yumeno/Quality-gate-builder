# Phase 2 Step 2.1 — schema baseline 作業記録

着手: 2026-06-04
完結: 2026-06-05 (本体実装 + Codex 計画レビュー 8 指摘吸収 + 段 1 観点別 5 subagent + 段 3 Codex 横断 + A1-A4 補修 + 段 5 Codex 2 周目「指摘なし収束」)

## Step 2.1 のスコープ

detailed-design.md §13.2 + 着手前境界 5 件 (§13.1):

- **format assertion opt-in**: Phase 1 では opt-out していた json_schema verification の format checker を、contract.enforce_format=true のとき強制有効化
- **$ref allowlist 段階解禁**: Phase 1 では全 $ref reject、Phase 2 で contract.allow_internal_ref=true のとき internal JSON Pointer (`#` または `#/...`) のみ accept、それ以外 (anchor / 絶対 URI / 相対 URI / network) は引き続き reject
- **後方互換監査**: 既存 example 3 例 (generic-minimal / python-cli-pytest / markdown-docs) と既存 fixture を新 schema で無変更通過
- **`qgb validate-policy --strict` skeleton**: Codex 計画レビュー指摘 5 で「Step 2.1 では先出ししない、Step 2.7 で初公開」に変更

Phase 2 計画 §13.1 で確定した境界 5 件 (Pattern B LLM 境界 / JSON Patch subset / check 証跡境界 / schema strict mode 段階化 / waiver 削除 Phase 3) のうち、本 Step は **schema strict mode 段階化** の第一段。

## 着手前: Codex 計画レビュー (2026-06-04)

4 軸案 (format opt-in / $ref allowlist / 後方互換監査 / --strict skeleton) で投げて 8 指摘を受領、全件吸収:

1. **$ref 許可条件の厳密化**: `ref.startswith("#")` だと `#foo` ($anchor 系) も通る → `ref == "#"` または `ref.startswith("#/")` のみ
2. **判定順序の spec lock**: 「事前収集 → non-internal reject → validator 作成」を docstring に明記、`$id` / nested `$schema` で解決スコープ複雑化のリスクを順序固定で吸収
3. **format ログ粒度**: `formats_seen` / `formats_checked` / `formats_ignored` の 3 行で typo'd format 名 (例: `datetime` ≠ `date-time`) を audit 可能に
4. **format checker の共有境界 (P9)**: `_build_format_checker` を `build_qgb_format_checker()` として public 化、`qgb_format_names()` を新設して `schema.py` に責務集約
5. **`--strict` skeleton 先出し撤回**: no-op 公開 CLI は誤認リスク、Step 2.7 で実体と同時公開
6. **contract 配置で良い**: 将来 option 増殖時に `json_schema_options` 検討 (Step 2.1 では平坦で OK)
7. **後方互換固定点 5 個明記**: enforce_format 未指定で従来 pass、allow_internal_ref 未指定で従来 reject、既存 contract 検証、log 追加で既存 assert 不破壊、`--strict` の有無で結果同一
8. **$ref 負例テスト追加**: `#foo` reject / relative URI reject / file URI reject / http URI reject / mixed log / self-ref no crash

## 実装の流れ

### 本体実装

`qgb/core/schema.py`:

- `_build_format_checker` → `build_qgb_format_checker()` rename + public 化 (Codex 指摘 4)
- `qgb_format_names() -> frozenset[str]` 新設 (import-time cache、Codex 指摘 3 用)
- `_QGB_FORMAT_NAMES` モジュール変数

`qgb/core/runner.py`:

- 旧 `_schema_contains_dollar_ref(node) -> bool` を **削除**
- 新 `_collect_dollar_refs(node) -> list[str]` (発見した全 $ref 値を収集、非文字列は repr() 化)
- 新 `_collect_format_names(node) -> set[str]`
- 新 `_is_internal_pointer_ref(ref) -> bool` (`ref == "#" or ref.startswith("#/")` のみ True、Codex 指摘 1)
- `_run_json_schema` 本体に Codex 指摘 1-3 を反映:
  - 順序 spec lock: `_collect_dollar_refs` → allow_internal_ref 判定 → validator 構築
  - contract.allow_internal_ref / enforce_format default false で Phase 1 挙動保存
  - `enforce_format: <bool>` / `allow_internal_ref: <bool>` / `formats_seen` / `formats_checked` (true only) / `formats_ignored` (true only) を log 出力

`qgb/schemas/contract.schema.json`:

- json_schema 枝に `enforce_format: boolean` / `allow_internal_ref: boolean` 追加 (default false、Phase 2 Step 2.1 反映の description 付き)

`qgb/core/validate.py`:

- `_CONTRACT_TYPE_FIELDS["json_schema"]` に 2 件追加 (foreign-typed field 検出から除外)

### テスト追加 (15 件)

`tests/test_json_schema_runner.py` の Step 2.1 セクション:

- `enforce_format` 4 件: default off で format 違反 pass / opt-in で valid 通過 / opt-in で invalid fail / unknown format silent ignore + log audit
- `allow_internal_ref` 11 件: default reject / `#/...` accept / `#` accept / `#foo` reject / `../foo` reject / `file://` reject / `http://` reject / `schema.json#/x` reject / `""` reject / mixed log / self-reference no crash

helper: `_set_contract_flags`, `_schema_with_ref`, `_setup_ref_project`

## 段 1 観点別 5 subagent レビュー

memory `review-process` の段 1 として 5 観点並列 (correctness / edge-cases / windows-specific / backward-compat / test-quality)。

**1 回目 (初回並列)**: windows-specific / backward-compat の 2 件が **許可申請を起こして user reject**、結果取得失敗。memory `parallel-strategy` の Bash 禁止句が prompt 冒頭に入っていなかったことが原因。

**memory 改定 (Phase 2 規律確立)**: `parallel-strategy.md` に「**Explore agent prompt の冒頭テンプレ v3 必須**」を昇格。具体的に:

- Read / Grep / Glob のみ使用
- Bash 完全禁止 (`python -c` / `python3 -c` / `py -3 -c` の任意コード実行を含む)
- 「念のため動かしてみる」推測検証も禁止、docstring / spec / 既存テスト名から論証
- 詰む観点は「本体側で確認する」と書いて打ち切ってよい (退路を作る)
- Codex 連携経路は 2 つ併記 (`/ask-codex-with-context` skill / Bash wrapper 直接)、使い分け明記

**2 回目 (再投入)**: テンプレ v3 で 5 観点同時並列、**全観点 reject ゼロで完走**。さらに 3 回目の windows-specific で再投入したのに `python3 -c "Path('C:\\test')..."` で許可申請を起こした事例があり、その追加メモも反映済。

### 段 1 集約 (信頼可な結果)

中程度以上の指摘:

- **correctness 1 件**: `internal_refs_accepted` の count (`len(refs)` 生 list 長) と列挙 (`sorted(set(refs))` dedup) の不整合
- **edge-cases 1 件**: 同上 (count 不一致の再指摘)
- **windows-specific 0 件**: 5 項目すべて論証クリア (string operations は path separator 非依存、`_run_json_schema` 内に subprocess 無し、log 構築は LF + UTF-8)
- **backward-compat 0 件**: 8 つの固定点すべてクリア (fixtures / examples 9 個の contract.json は新フィールド未使用、既存 12 テスト assert は本体 error message 依存で新 log 行に強い)
- **test-quality 1 件**: `test_format_default_off_lets_bad_date_time_pass` で `formats_seen` 存在は assert しているが具体値 (`date-time`) 検証なし
- 命名揺れ (`*_when_flag_default` vs `*_even_when_flag_true` 混在) は Phase 2 後続送り判定

## 段 3 Codex 横断レビュー (1 周目)

段 1 集約 + 全 diff (739 行) を Codex に投げて横断レビュー受領:

| 案 | 判定 | 優先度 | コメント |
|---|---|---:|---|
| A1 | 採用必須 | P0 | `found_refs` も同じ不整合、両経路で unique 統一 |
| A2 | 採用 | P1 | 非文字列 $ref 回帰テスト |
| A3 | 採用 | P1 | formats_seen 具体値検証 |
| A4 | 採用 | P2 | format checker 再構築 vs cache 境界 docstring 化 |
| A5 | Phase 2.7 送り | P3 | log フォーマット規約は strictness review で |
| A6 | Phase 2 後続送り | P3 | 命名統一は機械的 churn になる |

追加指摘 (Minor〜Medium): `$id` / base URI と internal-only `$ref` の相互作用 — Step 2.1 の blocker ではないが Step 2.7 に申し送り。

思想憲章 (P3 / P6 / P7 / P9 / NF-010) との衝突なし。`build_qgb_format_checker()` public 化が `schema.py` への format 責務集約で P9 と整合、追加依存なしで NF-010 維持。

## A1-A4 補修反映

### A1 (P0): runner.py の count unique 統一

`internal_refs_accepted` / `found_refs` の両経路で:

```python
unique_refs = sorted(set(refs))
log_lines.append(f"... ({len(unique_refs)}): ...")
```

count と列挙を unique 基準で揃え。

### A4 (P2): format checker 構築境界 docstring

`qgb_format_names()` は import-time cache (frozenset)、`build_qgb_format_checker()` は per-call fresh 構築 (jsonschema 側 stateful 化 / 副作用混入の予防)、両者の format set は同じ (build 関数の checkers ロジック由来) を 6 行コメントで明記。

### A3 (P1): formats_seen 具体値検証

`test_format_default_off_lets_bad_date_time_pass` に追加 assertion:

- `assert "date-time" in log` (具体値検証)
- `assert "formats_checked" not in log` / `assert "formats_ignored" not in log` (enforce_format=false 時の非対称性 spec lock)

### A2 (P1): 回帰テスト 2 件追加

- `test_non_string_ref_value_does_not_crash`: `{"$ref": 123}` で crash せず `repr(123)='123'` が disallowed_refs に出る
- `test_duplicate_ref_unique_count_and_listing`: 同 `#/$defs/S` を 2 properties から参照、`internal_refs_accepted (1):` (dedup 後 count) で 1 件のみ列挙

## 段 5 Codex 2 周目「指摘なし収束」

補修 A1-A4 反映後 diff (841 行) を Codex に投げて 2 周目判定:

> 指摘なし収束。A1-A4 は指摘の意図どおり反映されています。中程度以上の新規 finding はありません。Step 2.1 は収束宣言してよく、commit + journal 作成へ進んでよい判定です。

`/ask-codex-with-context` skill 経由で最終 sanity check を別途実施 (Phase 2 規律: 計画/レビュー局面で skill を一度は使う):

> commit + journal 作成して完結宣言してよい判定です。完了条件 3 点はすべて満たし、reject ゼロ + Codex 2 周目「指摘なし収束」+ ruff clean。`--strict` skeleton を Step 2.1 で先出ししない判断も計画レビューの採用内容と整合。規模感も 0.8 相当として妥当。

## 成績

- pytest: 470 件 (Phase 1 完結時) → 485 件 (Step 2.1 本体 +15) → 487 件 (補修 +2)、全緑
- ruff: clean
- 主要 verification_type 4 種 (file_exists / substring_match / command / json_schema) は引き続き全 example でカバー
- 既存 example 3 例 (generic-minimal / python-cli-pytest / markdown-docs) は無変更で全通過

## 受け入れ条件§12 進捗

Phase 1 完結時に 24/24 達成済。Phase 2 では Phase 1 受け入れ条件への影響は出さない (`enforce_format` / `allow_internal_ref` ともに default false で Phase 1 挙動保存)。Phase 2 用の新受け入れ条件は Step 2.7 で確定予定 (現状は detailed-design.md §13 の完了条件 = Step 単位の閉合条件として運用)。

## Phase 2 後続 Step への申し送り

### Step 2.2 (patch substrate)

- JSON Patch (`add` / `replace` / `remove` / `test`) で contract.json を編集するとき、`enforce_format` / `allow_internal_ref` の default false を前提にするか、patch 側で明示するかを Step 2.2 着手前に固定
- patch 適用後の validate-policy 経由で Step 2.1 で確立した `_collect_dollar_refs` / `_is_internal_pointer_ref` 経路がそのまま走ることを確認 (atomic apply 前 validate の事前検査として)

### Step 2.5 (Pattern B external-LLM interface)

- proposal schema (`qgb/schemas/proposal.schema.json`) を新設するとき、Step 2.1 で確立した format / `$ref` allowlist を継承する (proposal schema 自身の $ref / format も同じ allowlist 経路を通す)
- proposal を adopt するとき contract 経由で `allow_internal_ref` / `enforce_format` を設定する flow を Step 2.5 で定義

### Step 2.7 (strictness review)

複合課題として以下を一括処理:

- `formats_checked` / `formats_ignored` を strict mode で必須証跡にするか
- unknown format を warning 止まりか failure に昇格するか
- `$id` / base URI / embedded resource と `allow_internal_ref` の関係明文化 (Codex 1 周目横断レビュー Minor〜Medium 指摘)
- log アサーションを固定文字列依存から構造化寄りに (テスト品質指摘 #1 への対応)
- 命名揺れ (`*_when_flag_default` / `*_even_when_flag_true`) を Phase 2 全体で統一
- `qgb validate-policy --strict` の実体実装 (`additionalProperties: false` の全面 / 部分 / 見送り判断)

## プロセス軸の振り返り

### Phase 1 で確立したサイクルの Phase 2 再現性

- **計画 Codex 相談 → 着手前構造修正 → 実装** が Step 2.1 で再現 (8 指摘吸収、内 1 件 = `--strict` 先出し撤回が構造修正)
- **memory review-process 段 1〜5 完走** も Step 2.1 で再現 (段 1 reject → memory 改定 → 再投入で完走 + 2 周目「指摘なし収束」)
- **本体 + 補修を 1 コミット** パターンを Phase 2 でも継承 (本 commit に補修込み)

### Phase 2 で確立した新規プロセス

- **subagent prompt 冒頭テンプレ v3 必須**: Bash 完全禁止 + 許可が通る経路の例示 + 論証で詰める指針 + 退路 (「打ち切ってよい」)。memory `parallel-strategy` に永続化
- **Codex 経路の二段構え**: `/ask-codex-with-context` skill (手動起動 / セカンドオピニオン) + Bash wrapper 直接 (大規模 context オーケストレーション)。memory `codex-context-files` に併記
- **`qgb-llm-boundary` 境界の Step 2.1 実装段階での維持確認**: format checker / $ref allowlist いずれも qgb 本体内で完結、LLM SDK / 外部依存追加なし (NF-010 / Pattern B 整合)

### memory 改定の経緯

Step 2.1 中に 2 件の memory 改定を実施:

1. `qgb-llm-boundary` (新規、Phase 1 → Phase 2 移行時に Codex 計画レビューで確立した境界を永続化、Phase 5 接続も明記)
2. `parallel-strategy` (テンプレ v3 + 失敗時リカバリ手順 + Codex 経路二段構え)
3. `codex-context-files` (skill 経路と wrapper 経路の使い分け併記、quote 付き wrapper パス必須を明記)

これらは Step 2.2 以降の規律として運用する。
