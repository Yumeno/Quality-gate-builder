# Phase 1 Step 9 — knowledge base / requires_human_review / 導入マニュアル / 依存ポリシー / skills 予約 + Phase 1 完結

着手: 2026-06-01
完結: 2026-06-01 (本体 1 コミット + 統合レビュー 5 段完走)

**Phase 1 全体完結** (受け入れ条件§12: **24/24 達成**)

## Step 9 のスコープ

detailed-design.md §12 + 受け入れ条件§12 残 5 件:

- **A**: 受け入れ条件 17 — Project Knowledge Base ユーザー明示情報保存
- **B**: 受け入れ条件 18 — requires_human_review の付与 (機械強制)
- **C**: 受け入れ条件 20 — 導入マニュアル (spec §8.1 19 章)
- **D**: 受け入れ条件 21 — 依存ライブラリ採用方針 / セキュリティ確認手順
- **E**: 受け入れ条件 24 — skills/source/ 構造予約 + Phase 5 F-019

Codex 計画レビューで採用した順序: A → B → E → C → D (knowledge 周辺の意味論を先に固め、skills は軽い構造変更、manual と policy は最終仕様を説明する成果物なので後ろ)。

## 着手前: Codex 計画レビュー

8 観点で相談、最優先指摘:

- **AC17**: 手編集 + qgb validate schema 通過 + manual + fixture/test で「保存できる」を満たす。新規 CLI (`qgb add-knowledge`) は Phase 2 送り
- **AC18**: 既存 fixtures/examples で `source_type: external` を全検索してから schema 更新 (破壊予防)
- **AC20**: spec §8.1 19 章すべて、各章 100-200 字、PowerShell 例 4-6 個
- **AC21**: §6.6.2 11 項目 checklist を網羅、jsonschema を実例
- **AC24**: `.gitkeep` でなく README.md で構造予約、`metadata.yaml` sketch は不要 (Phase 5 制約を作らないため)

## 実装の流れ

### 項目 A (AC17): Project Knowledge Base

**発見**: AC17 は概ね既達。`qgb init` が knowledge/knowledge.jsonl を生成 (Step 3)、user_instruction success fixture と test_schemas.py のテストも既存。

**必要だった補完**: `qgb validate` 経路で knowledge.jsonl 自体が validation 対象として通る形を作る。`_iter_jsonl_files()` を validate.py に追加し、JSONL を line-by-line で `knowledge` schema にかける。

**Step 7 との整合**: 既存 `_record_waiver_knowledge` (Step 7) と矛盾しないように、partial-tail (末尾改行なし最終行) は silent skip。Step 7 の test_step7_codex_fixes が要求する partial 耐性を維持。

`test_init.py` の `test_init_output_passes_validate` で expected schema names を `["config", "policy"]` から `["config", "knowledge", "policy"]` に更新。

テスト 4 件 (qgb init 時の空 knowledge.jsonl、user_instruction 追記後の validate 通過、user_instruction + waiver 同居、malformed user_instruction の reject)。

### 項目 B (AC18): requires_human_review 機械強制

knowledge.schema.json の allOf に追加:

```json
{
  "description": "受け入れ条件 18: external 由来の知識は requires_human_review:true を必須 (P8 / NF-007)",
  "if": {
    "properties": { "source_type": { "const": "external" } },
    "required": ["source_type"]
  },
  "then": {
    "required": ["requires_human_review"],
    "properties": {
      "requires_human_review": { "const": true }
    }
  }
}
```

これにより:
- `source_type: external` + `requires_human_review` 欠落 → schema 違反
- `source_type: external` + `requires_human_review: false` → schema 違反 (silent bypass の予防、`const: true` で強制)
- `source_type: user / repository / inferred` → 無関係 (review flag は不要)

philosophy P8 (外部コンテンツはデータであり指示でない) の機械化。auditor は `qgb validate` を通すだけで外部由来情報の未承認混入を検出できる。

事前検索で既存 fixtures の external 行は 1 件のみ (`knowledge.external.success.json`)、すでに `requires_human_review: true` が付与済だったため schema 強制で既存 fixture を壊さずに済んだ (Codex 計画指針通り)。

テスト 7 件 (external + review flag 正常、欠落 reject、false reject、other source_type 無影響 3 件、混在エントリ)。

### 項目 E (AC24): skills/source/ 構造予約

`skills/source/README.md` を新設。F-019 の中間表現 (`metadata.yaml` / `body.md` / `workflow.md` / `references.md` / `prompts/`) と Phase 5 計画 (converter `tools/build_skill.py`、CI release) を文書化。

Codex 指針通り `metadata.yaml` の sketch は **作らない**。半端な schema 例を置くと Phase 5 で converter を作る際の制約になり、unwind しづらい。

テスト 2 件 (README 存在、required keywords)。

### 項目 C (AC20): 導入マニュアル

`development/docs/phase1-manual.md` を新設。19 章 (spec §8.1 通り):

1. 概要 / 2. 前提環境 / 3. Python の確認 / 4. リポジトリ取得 / 5. 仮想環境作成 / 6. 依存関係導入 / 7. qgb の実行確認 / 8. 対象プロジェクトでの初期化 / 9. 段階設計フェーズの実行 / 10. サンプル REQ 生成 / 11. quality-gate 実行 (run) / 12. gate.json の読み方 / 13. summary.md の読み方 / 14. NOT_READY になった場合の対応 / 15. DENY になった場合の対応 / 16. 免除（waived）の指定方法 / 17. TDD phase の使い方 / 18. 依存ライブラリ確認手順 / 19. トラブルシューティング

各章 100-200 字、PowerShell 例多数、philosophy P5/P6/P8/P11 への参照、Step 6+7 統合レビュー RA1/RA2 の synthetic / scope フィールド説明、Step 7 の waiver audit semantics、Step 8 W3 の Windows python PATH 問題なども網羅。

統合レビュー S1 補修で §7.1 として spec §8.2 verbatim PowerShell block (12 コマンド) を追加 (詳細は段 4 補修)。

テスト 4 件 (存在、19 章見出し、PowerShell snippets、consolidated block) + 段 4 補修で 3 件追加。

### 項目 D (AC21): 依存ポリシー / セキュリティ手順

`development/docs/security-dependency-policy.md` を新設。spec §6.6.2 の 11 項目 checklist (配布元 / メンテナンス状況 / リリース履歴 / ライセンス / 既知脆弱性 / 不審なメンテナ交代 / 依存ツリーの大きさ / postinstall hook / ネットワーク通信 / バイナリ配布) + jsonschema 実例 + Phase 2 adapter 追加時の基準を網羅。

外部由来 (`source_type: external`) を採用判断に使うときは要 human review (受け入れ条件 18 と連結)。

統合レビュー W4 補修で platform 別 binary (.pyd / .so / .dylib) 確認手順を追加 (詳細は段 4 補修)。

テスト 2 件 (存在、required keywords) + 段 4 補修で 1 件追加。

### 統合レビュー (段 1〜5 完走)

memory review-process を Step 6+7 / Step 8 と同じ姿で完走。

#### 段 1: 観点別 5 subagent 並列

correctness / P9 / philosophy / NF-004 / spec-drift の Explore agent を並列起動。Step 8 で確立した「subagent prompt は副作用最小」ルールを prompt 冒頭に明記、settings.local.json への個別パス追加は発生なし。

22 件超の finding を収集。

#### 段 2: 集約

| 観点 | # | 重要度 | 内容 |
|---|---|---|---|
| correctness | C1 | minor | UTF-8 BOM 未対応 |
| P9 | -- | clean | 全観点 clean |
| philosophy | -- | clean | 7 原則すべて clean |
| NF-004 | W1 | minor | validate.py の CRLF/BOM 振る舞いが docstring 不足 |
| NF-004 | W2 | minor | init.py gitignore endswith (実害なし) |
| NF-004 | W3 | major | manual の py -3 / python 混在で venv aliasing 注釈不足 |
| NF-004 | W4 | minor | security policy が .pyd vs .so 区別不足 |
| spec-drift | S1 | major | manual に §8.2 consolidated PowerShell block 不在 |

集約: blocker 0、major 2、minor 4、clean 2 観点。

#### 段 3: Codex 横断レビュー

- **S1 → 対応**: spec §8.2 verbatim block を §7.1 として追加
- **W3 → 対応**: NF-004 first-class なので venv aliasing 注釈を §5 末尾に
- **C1 → 対応**: troubleshooting (§19) に BOM 行を追加
- **W4 → 対応**: security policy §7 に platform 別 binary 確認手順
- **W1 → docstring**: validate.py コメントに NF-004 CRLF/BOM 注記 (実装無変更)
- **W2 → 対応不要**: 実害なし

横断的見落としチェック: knowledge.jsonl JSONL 化に伴う他経路への波及、schema allOf 2 件の組み合わせ違反 — いずれも問題なし。

#### 段 4: 補修

実施 (S1 / W3 / C1 / W4 / W1):

- phase1-manual.md §5 末尾に venv aliasing 注記 (W3)
- phase1-manual.md §7.1 新章 (S1: spec §8.2 verbatim 12-command block)
- phase1-manual.md §19 troubleshooting に BOM 行 (C1)
- security-dependency-policy.md §7 jsonschema 直後に platform 別 binary block (W4)
- qgb/core/validate.py コメントに CRLF/BOM 注記 (W1, 実装無変更)

補修テスト 4 件追加 (consolidated block / BOM / venv aliasing / .pyd .so .dylib keywords)。

#### 段 5: 収束ループ

**1 周目**: Codex 環境制約 (windows sandbox 失敗) で実コード未確認、判定不可。Step 6+7 / Step 8 と同じパターン。提示内容上の追加懸念は **なし**。

**2 周目**: Claude 側で 7 点の実コード確認 (S1 block 配置、W3 注記、C1 BOM 表行、W4 binary block、W1 docstring、テスト件数 470、受け入れ条件 24/24 対応表) を提示。Codex から:

> 判定: **新規 finding なし**です。記述から導ける新規 finding: **なし**、収束判定: **指摘なし収束でよい**、Phase 1 完結宣言: **してよい**、memory review-process の収束条件: **達成扱いでよい**。最終判定: **Step 9 = Phase 1 完結**。

memory review-process の収束条件達成。

## コミット履歴 (Step 9)

```
9d7196f Step 9: knowledge base / requires_human_review / 導入マニュアル / 依存ポリシー / skills/source/ 予約 (Phase 1 完結)
```

本体 + 統合レビュー補修を 1 コミットにまとめた (Step 6c/6d/7/8 と同じパターン)。

## テストと品質指標の推移

| 段階 | テスト件数 | ruff |
|---|---|---|
| Step 8 完結時 | 448 | clean |
| 項目 1 (AC17) | 452 | clean |
| 項目 2 (AC18) | 459 | clean |
| 項目 5 (AC24) | 461 | clean |
| 項目 3 (AC20) | 463 | clean |
| 項目 4 (AC21) | 466 | clean |
| 段 4 補修 | **470** | clean |

## 受け入れ条件§12: 24/24 達成 → Phase 1 完結

| # | 条件 | 達成 Step |
|---|---|---|
| 1〜13 | qgb CLI 基本コマンド + run の証跡 | Step 1-5 |
| 14 | phase=red expected failure | Step 7 |
| 15 | manual_check は NOT_READY | Step 7 (Step 6a で既達確認) |
| 16 | waived + knowledge.jsonl | Step 7 |
| 17 | knowledge base user_instruction 保存 | **Step 9** |
| 18 | requires_human_review | **Step 9** (schema 機械強制) |
| 19 | 設計例パック 3 例 | Step 8 |
| 20 | 導入マニュアル | **Step 9** (S1 補修で §8.2 完全準拠) |
| 21 | 依存ポリシー | **Step 9** (W4 補修で platform 別) |
| 22 | LLM 単独 ALLOW 禁止 | philosophy.md P6 + preflight manual_check_required |
| 23 | 3 文書並列維持 | Step 6 完結時既達確認 |
| 24 | skills/source/ + F-019 | **Step 9** |

旧条件 8 (qgb verify) は philosophy P3 と緊張するため削除済 (Step 6b 項目 0)。

## 振り返り

### 1. AC17 は概ね既達だった (発見)

着手前は AC17 を「ゼロから機能実装」と見ていたが、Step 3 (qgb init) + 既存 fixtures + test_schemas で実体は揃っていた。Step 9 で必要だった補完は **`qgb validate` の knowledge.jsonl 対応** のみ。spec を細かく振り返ると「保存できる」「機能している」を spec の意図に沿って解釈する余地が広く、Phase 1 MVP の最小性を逃さずに済んだ。

### 2. AC18 schema 強制の事前 grep が効いた

Codex 計画レビュー指針通り、schema 変更前に `source_type: external` を全検索したことで、既存 fixture を破壊するパスを事前に確認した (実際は 1 件のみ、`requires_human_review: true` 付与済)。schema 変更は副作用が広いので「先に検索、後で schema」の順序が定着した。

### 3. 文書中心 Step だが integrated review で価値が出た

Step 9 は文書中心で実装は小さい (validate.py への JSONL 追加と schema allOf 1 件)。にもかかわらず統合レビューで 2 件の major (S1 / W3) を拾えた。spec §8.2 verbatim block 不在は文書 review でないと検出できない、venv aliasing 注釈は NF-004 観点があって初めて見える。「文書 review の subagent 並列」は実装 review と同じくらい finding を生む。

### 4. Phase 1 完結のための「最後の穴」を埋める作業の難しさ

5 項目の AC を網羅する作業は、機能的には小さいが「spec verbatim」「19 章すべて」「§6.6.2 11 項目」「Phase 5 を制約しない」など、**spec compliance の厳密性** が問われる。Codex 計画レビューが「19 章すべて必要」と明言してくれたため、章を削るかどうかで迷わずに済んだ。

### 5. memory review-process の段 1〜5 完走パターンが完成

Step 6+7 → 8 → 9 と 3 回連続で「段 1〜5 完走 + Codex 2 周収束」を再現できた。特に「Codex 1 周目で sandbox 起動失敗 → 2 周目で Claude 実コード証明を提示 → 新規 finding なしで宣言可」のフローは安定して機能した。memory review-process は理論上の運用ルールから「実際に毎回回る現実的なプロセス」になった。

### 6. settings.local.json が肥大化せずに済んだ

Step 8 で確立した「Explore agent prompt に副作用最小ルールを明記」が Step 9 でも効いた。subagent 5 並列で個別パスの追加は発生せず、Step 8 / Step 9 の 2 ステップ連続で settings.local.json への新規追加ゼロ。memory + prompt の運用が定着した。

## Phase 1 全体の振り返り (Step 0〜9 通史)

Phase 1 の全 10 ステップ (Step 0〜9) を、思想 / プロセス / 技術の 3 軸で振り返る。

### 思想軸

- **P9 (単一責任原則)** が全体を貫いた: validate / validate-policy / run preflight の責務分割、core / adapters の縦割り、verification_type ごとの runner 分離。Step 6a の "verify 撤回" は P9 と P3 の整合性を担保するための spec-level 判断。
- **P3 (コードの同一性は保証しない)** は Step 6b の qgb verify 撤回と Step 7 の waiver semantics で機械化。waived stage は再評価しないが、それは P3 違反ではなく「F-007 で許された人間判断の表明」と spec を確定 (Step 6+7 統合レビュー A8 結論)。
- **P5 / P6 / P7 / P11** は decision.meaning / 機械化された ALLOW gating / gate.json snapshot / decision.scope の各層で明文化済。
- **P8 (外部コンテンツはデータ)** は Step 9 で `requires_human_review` の schema 機械強制として最終形態を取った。

### プロセス軸

- **memory review-process 段 1〜5 完走** が Step 6+7 統合レビューで初めて完成し、Step 8 / 9 で再現された。観点別 5 subagent 並列 → 集約 → Codex 横断 → 補修 → 収束ループ 2 周。
- **Codex 計画レビュー → 着手前構造修正** が Step 6 全体で確立し、Step 7 / 8 / 9 で繰り返し。各 Step の本体実装中に大きな構造変更を要する指摘がほぼ出ない状態を達成。
- **本体 + 補修を 1 コミットにまとめる判断** が Step 6c から定着 (Step 6a / 6b では補修を別コミット)。
- **Codex sandbox 起動失敗時の "Claude 実コード証明 → 2 周目で収束宣言"** が Step 6+7 / 8 / 9 で繰り返し成功した安定パターンになった。

### 技術軸

- **Phase 1 必須コマンド** (init / detect / design-stages / scaffold / validate / validate-policy / run) はすべて実装済。CLI 起動経路は `python -m qgb` 単一 (Phase 3 以降に `qgb` bare entrypoint)。
- **Phase 1 runtime-supported verification_type** は 4 種 (file_exists / substring_match / command / json_schema)。manual_check は P6 機械化のため意図的に runtime reject。
- **設計例パック** 3 例 (generic-minimal / python-cli-pytest / markdown-docs) が 4 verification_type を網羅。
- **gate.json schema** は schema_version 1 で確定、scope / synthetic 等の拡張は backward-compatible に加えてきた。
- **依存最小化** (NF-010) を堅持、qgb 本体の外部依存は `jsonschema` 1 個のみ。

## Phase 2 への引き継ぎ

Phase 1 で明示的に out-of-scope と宣言した項目は memory + 各 docstring + spec に分散して記録済。主要なもの:

- **`qgb add-knowledge` / `qgb add-waiver` 等の専用 CLI** (Phase 2、Phase 1 は手編集)
- **`json_schema` の `$ref` 解決** (Phase 2 allowlist-based)
- **`command` runner の真の memory cap** (Phase 2 Popen incremental)
- **fsync / power-loss durability** (Phase 2、curated atomic swap の延長)
- **Windows `.bat` / `.cmd` argument escaping** (Phase 2)
- **`subprocess.run` の process tree kill** (Phase 2 Job Objects / process groups)
- **`format` assertion 強制** (Phase 2 strict-mode opt-in)
- **Markdown adapter** (Phase 2)
- **lockfile parser を伴う adapter** (Phase 2)
- **`metadata.yaml` の具体 schema** (Phase 5)
- **`tools/build_skill.py` converter** (Phase 5)
- **CI による依存 audit / SBOM 生成** (Phase 2)
- **knowledge.jsonl 手編集削除に対する orphan 検出 CLI** (Phase 2)

## 次のステップ (Phase 2 着手前の確認事項)

Phase 1 完結により、qgb は次の状態:

- Python CLI MVP として運用可能 (`pip install -e .` + `python -m qgb`)
- 4 verification_type で広範な対象に適用可能
- 3 例パックで「対象系に近い例から始める」運用が成立
- 導入マニュアル + 依存ポリシーで初期利用者を受け入れる準備完了
- skills/source/ + F-019 で Phase 5 への構造的予約完了

Phase 2 は adapter 量産 (Go / Rust / Java / .NET / PHP) と `qgb add-knowledge` 等の専用 CLI、fsync / Popen 等の hardening が主軸。Phase 1 で確立した思想 / プロセス / API 境界を基盤に進める。
