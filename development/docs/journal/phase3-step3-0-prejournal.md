# Phase 3 Step 3.0 着手前判断: detect 廃止 + project-context 導入

着手前判断確定: 2026-06-21

## 経緯

Phase 2 完結 (`fccc9f2`, 2026-06-13) 後、Phase 3 着手前の user 相談 (detailed-design §13.5 の必須プロセス) で次が確定した:

1. **Phase 4 廃止** (CI 連携は qgb の独立 Phase でない)
2. **adapter 量産廃止** (Go/Rust/.NET/Java/PHP/Markdown adapter 計画撤回)
3. **qgb detect / qgb/adapters/ 廃止** (Step 3.0 で実施)
4. **project-context.{md,json} 二重ファイル設計導入** (Step 3.0 で実施)
5. **Phase 5 から adapter なし設計** (対象理解は LLM、ALLOW/DENY は qgb の contract 実行結果)

spec 改訂は別 commit (`ada386b`) で先行完了。本 prejournal は Step 3.0 本体実装の着手前判断を記録する。

## Claude が前段で 2 回ラインを引き間違えた事実 (恒久記録)

ライン引きの誤りを記録し、Phase 5 以降の同様の判断バイアスの予防教材とする。

### 1 回目の誤り (adapter 廃止 → Phase 5 スキルが LLM で判定)

User 指摘 (「Phase 4 ってほんとにいるんだろうか、ガウディの塔みたいになってないか?」) を受けて、Claude は adapter 量産も過剰仕様と判定し「Phase 5 スキルが LLM で言語判定する」案を提示。

**誤りの根拠**: 「対象判定をすべて LLM 側に倒せばシンプル」と考えた。これは検出結果が gate.json の `runtime` フィールドに入ることを見落とし、P7 (再現可能な証跡) と P6 (LLM 単独 ALLOW 禁止) を qgb 自身の機械的検出範囲にまで適用してしまう誤り。

### 2 回目の誤り (adapter 残す = P7 のため機械側)

1 回目の誤りに気づいた user 指摘 (「LLM と機械の責務分掌ラインを点検して」) を受けて、Claude は反転し「adapter は機械的検出だから P7 のため残す」と提示。

**誤りの根拠**: 「対象プロジェクトは必ずプログラミング言語で書かれている」「検出結果が ALLOW 判定根拠になる」の 2 つの暗黙仮定。両方とも理念に照らすと不成立。

### 3 回目の修正 (user 指摘で再廃止)

User 指摘 (「adapter (言語判定)、ほんとにいる? ユーザーが作ろうとするものは、極端な話、プログラミング言語で構築するプログラムではないかもしれない」) で誤りが確定。

**正しいライン引き**:
- 対象判定 = LLM 自由度側 (設計の起草)
- adapter の検出結果は ALLOW 判定根拠にならない (basis[] は REQ / CONTRACT / POLICY ID のみ、philosophy.md / detailed-design.md で確定済み)
- gate.json の `runtime` に LLM 判定が入っても P7/P6 違反でない (判定の根拠ではなく履歴であるため)

### 構造的盲点 (Codex 全体評価で指摘)

Codex 横断レビューで指摘された Claude のバイアス:

- 「対象プロジェクト = プログラミング言語のソース」と暗黙仮定する傾向
- 「機械責務 = 確定的」「LLM 責務 = 揺らぎ」と二分しがちで、中間 (補佐 Agent が確定的構造化を担う) の存在を見落とす
- philosophy.md P6 (LLM 単独 ALLOW 禁止) を「LLM を排除する」と読みがちで、「機械検査と組み合わせる」本義を忘れがち

Phase 5 着手時、同様のバイアスが顔を出していないか本書を読み返して確認すること。

## Step 3.0 スコープ確定

### A. 削除対象

- `qgb/core/detect.py`
- `qgb/adapters/__init__.py`, `base.py`, `generic.py`, `python.py`
- `qgb/cli.py` から `detect` subcommand handler + parser
- `qgb/core/design_stages.py` から `from qgb.adapters.base import DetectionResult` / `from qgb.core.detect import run_detect` / `DesignProposal.detect` フィールド / `_pick_template(_detect_result)` の detect 依存
- `qgb/core/proposal.py` から `run_detect` 呼び出し / `detect` フィールド出力 (代わりに `project_context` 読み込みを追加)
- 関連テスト:
  - `tests/test_detect.py` (削除)
  - `tests/test_adapter_base.py` / `test_adapter_generic.py` / `test_adapter_python.py` (削除)
  - `tests/test_design_stages_proposal.py` / `test_design_stages_commit.py` (改修: detect フィールド削除)
  - `tests/test_proposal.py` (改修: detect フィールド削除、project_context フィールド追加)
  - `tests/test_cli_smoke.py` (改修: detect コマンド削除)

### B. 新設対象

#### B.1 `qgb/schemas/project-context.schema.json`

Codex 指摘 3 件反映:

- **指摘 A**: P8 観点で「人間承認済み」vs「Agent 下書きだけ」の区別フィールド → `human_reviewed: bool` を root に
- **指摘 B**: `constraints.language` が言語中心モデルを再誘発する盲点 → 廃止、代わりに `technologies` (array of string) と `artifact_kinds` (array of string) のような広い語彙
- **指摘 C**: スキル責務文言の「対象判定を全て LLM に委ねる」→「対象理解は LLM、ALLOW/DENY は qgb の contract 実行結果で決まる」(これは framework-shape.md 改訂で反映済み)

スキーマ案:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://qgb.example/schemas/project-context.schema.json",
  "title": "qgb project context",
  "description": "Self-declaration of the target project; mediates between human prose (project-context.md) and machine consumers (qgb propose-context / Phase 5 skills)",
  "type": "object",
  "required": ["schema_version", "human_reviewed", "source_metadata"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "human_reviewed": {
      "type": "boolean",
      "description": "true when a human has reviewed and approved the json (not just an agent draft). qgb design-stages propose-context emits a warning when this is false."
    },
    "project_kind": {
      "type": "string",
      "description": "Free-form descriptor of what kind of artifact set this project produces. Examples: 'python-cli', 'prompt-collection', 'terraform-modules', 'legal-templates', 'mixed-devops'. Not constrained by enum to avoid recreating the language-centric model that adapters had."
    },
    "purpose": {
      "type": "string",
      "description": "Why this project exists; what value it delivers"
    },
    "scope": {
      "type": "object",
      "properties": {
        "in_scope": {"type": "array", "items": {"type": "string"}},
        "out_of_scope": {"type": "array", "items": {"type": "string"}}
      }
    },
    "technologies": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Free-form list of technologies used. NOT a single 'language' field by design: a project may use no programming language at all (markdown docs, prompt sets) or many (mixed-devops). Examples: ['python', 'pytest'], ['terraform', 'aws'], ['markdown'], ['claude-code', 'codex-cli']"
    },
    "artifact_kinds": {
      "type": "array",
      "items": {"type": "string"},
      "description": "What kinds of artifacts this project produces. Examples: ['source-code', 'tests'], ['documentation'], ['prompt-templates'], ['ci-configuration'], ['legal-contract-templates']"
    },
    "platform": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Target platforms. Examples: ['windows', 'linux'], ['browser'], ['posix-only'], ['language-agnostic']"
    },
    "non_adopted_methods": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["method", "reason"],
        "properties": {
          "method": {"type": "string"},
          "reason": {"type": "string"}
        }
      },
      "description": "Methods explicitly rejected and why. Important context for stage design."
    },
    "references": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["kind", "path"],
        "properties": {
          "kind": {"type": "string"},
          "path": {"type": "string"}
        }
      }
    },
    "source_metadata": {
      "type": "object",
      "required": ["generated_by", "generated_at"],
      "properties": {
        "generated_by": {
          "type": "string",
          "enum": ["human", "agent-assisted"],
          "description": "human = handwritten; agent-assisted = an LLM agent helped structure it from project-context.md"
        },
        "agent_name": {
          "type": "string",
          "description": "When generated_by=agent-assisted: name of the assisting agent (e.g. 'claude-code', 'codex-cli', 'gemini-cli')"
        },
        "agent_version": {"type": "string"},
        "generated_at": {"type": "string", "format": "date-time"},
        "source_md_sha256": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$",
          "description": "SHA-256 of project-context.md at the time of generation. Allows detecting md updates that orphan the json."
        }
      }
    }
  }
}
```

#### B.2 `qgb/core/init.py` 修正

- `project-context.json` の雛形を `.quality-system/` 直下に生成
- 初期値: `human_reviewed: false`、`source_metadata.generated_by: "human"`、`source_metadata.generated_at: now`
- 既存の `knowledge/project-context.md` 生成は維持 (人間正本として位置づけ再定義)

雛形例:

```json
{
  "schema_version": "1.0",
  "human_reviewed": false,
  "project_kind": "",
  "purpose": "",
  "scope": {"in_scope": [], "out_of_scope": []},
  "technologies": [],
  "artifact_kinds": [],
  "platform": [],
  "non_adopted_methods": [],
  "references": [],
  "source_metadata": {
    "generated_by": "human",
    "generated_at": "<ISO 8601 UTC>"
  }
}
```

#### B.3 `qgb/core/loader.py` に `load_project_context` 追加

- `.quality-system/project-context.json` を読み込む public 関数
- ファイル不在は `None` 返却 (エラーにしない、optional フィールドとして扱う)
- BOM tolerant (utf-8-sig、Phase 2 Step 2.5 で確立した規約に従う)
- LoaderError は schema-invalid のとき発生 (validate 経由で検出されることを想定、loader は単純 read のみ)

#### B.4 `qgb/core/validate.py` 修正

- `qgb validate` の検査対象に `project-context.json` を追加 (schema 検証のみ)
- `_iter_jsonl_files` と同型の経路追加

#### B.5 `qgb/core/proposal.py` 修正

- `build_proposal_context` から `detect` フィールド削除、`project_context` フィールド追加
- `project_context` は `load_project_context(project_root)` の戻り値 (None なら `null`)
- `human_reviewed: false` のときは `warnings` リストに「project_context is not human-reviewed」を追加

出力構造 (Step 3.0 後):

```python
return {
    "document_kind": PROPOSAL_CONTEXT_DOCUMENT_KIND,
    "schema_version": "1.0",
    "intended_use": "external_tool_input_data",
    "contains_executable_instructions": False,
    "project_context": load_project_context(project_root),  # 新規、None なら null
    "policy": policy,
    "reqs": reqs,
    "constraints": {...},
    "expected_response": {...},
}
```

#### B.6 `qgb/core/design_stages.py` 修正

- `DesignProposal.detect` フィールド削除
- `_pick_template(_detect_result)` は detect 引数を取らない形に変更 (常に `generic-minimal` を返す既存挙動を維持)
- legacy rule-based `qgb design-stages [--json] [--commit]` 経路は維持 (後方互換)

### C. examples 更新

#### C.1 `examples/python-cli-pytest/`

Codex 指摘「Python adapter の知見を few-shot や project-context の記入例として再利用する」を反映:

- `.quality-system/knowledge/project-context.md` の記入例 (Python adapter が観察していた marker file / pyproject.toml セクション / src layout 等を人間向け説明として転記)
- `.quality-system/project-context.json` の記入例 (md の内容を機械可読 json に構造化、`human_reviewed: true` + `source_metadata.generated_by: "human"`)
- `design-notes.md` に「Python プロジェクト観察観点」セクション追加 (元 Python adapter の観点を Phase 5 スキル向けに転記)

#### C.2 他 examples の点検

- `examples/generic-minimal/`: 既存通り (Generic adapter 経路に依存していないので変更なし)
- `examples/markdown-docs/`: 既存通り
- `examples/go-cli/` / `examples/node-cli-vitest/` / `examples/python-fastapi-pytest/`: 既存通り

(これらは detect 結果に依存していない、policy.json と contracts/*.json のみで構成、Phase 2 Step 2.6 で確認済み)

### D. spec / docs (本 prejournal 後の追加対応)

spec 3 ファイルは `ada386b` で先行 commit 済。本体実装後の追加更新:

- `migration-phase1-to-phase2.md` に Step 3.0 の変更点追記 (BOM 対応の延長 + detect 廃止 + project-context 新設)
- README.md の Phase 計画記述更新

## レビュー方針

Phase 2 で確立した 4 段レビュー (`review-process` memory) を踏襲:

- 段 1: 観点別 5 subagent 並列 (correctness / P9 / philosophy / NF-004 / spec-drift)
- 段 2: 集約・調停 (Claude 側、Codex に渡す前)
- 段 3: Codex 横断レビュー (`/ask-codex-with-context` skill 経由)
- 段 4: 人間 (最終判断)
- 収束ループ: 補修 → 再レビュー で K=2 回連続新規 finding ゼロまで

ただし Step 3.0 は **「削除作業 + 新設作業」が混在する** ため、段 1 のレンズに調整を加える:

- correctness: 削除漏れ (grep で残存ゼロ確認) と新設の正しさ両方
- P9: detect 削除で proposal.py / design_stages.py / cli.py の責務がどう整理されたか
- philosophy: project-context.json の human_reviewed 経路が P8 を守れているか、ALLOW 判定根拠に入らないか
- NF-004: project-context.json 読み込み経路の utf-8-sig 対応、PowerShell からの動作
- spec-drift: detailed-design.md §14 と本体実装の乖離点検

## 完了条件

- detect / adapter 関連コード / テストが残らない (`grep -r "detect\|adapter" qgb/ tests/` で残存なし、ただし「detect」を含む正当な単語 = `detected_at` 等は別判定)
- `qgb validate` が `project-context.json` の schema 検証を含む
- `qgb design-stages propose-context` 出力に `project_context` フィールド (または null) が含まれる
- `qgb init` が `project-context.json` 雛形を生成
- `examples/python-cli-pytest/` が新形式 (`project-context.{md,json}` の記入例) で動作
- 既存 731 件 - 削除テスト + 新規テスト で全 green
- ruff clean
- Codex 横断レビュー「指摘なし収束」または「指摘あり → 補修 → 収束」

## 規模感

- 計画見積: 2.0〜2.5 (Step 5 = 1.0 基準)
- Codex 指摘反映 (human_reviewed フィールド + 言語中心モデル回避 + スキル責務文言) は schema 設計に組み込み済、追加上振れ要因なし
- 段 1 subagent 並列レビューでさらに指摘が出る可能性あり、その場合 +0.3〜0.5

## Step 3.1 への申し送り

- `qgb/core/runner.py` の `_run_command` を `qgb/core/command.py` に切り出す Step 3.1 の準備として、本 Step では runner.py には触らない (P9: 削除作業と切り出し作業を混ぜない)
- CI 雛形 `.github/workflows/test.yml` は Step 3.1 で新設、本 Step では作成しない
- 依存固定 (Step 3.2) は本 Step に含めない
