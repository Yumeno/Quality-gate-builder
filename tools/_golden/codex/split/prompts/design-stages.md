<!--
  GENERATED FILE - DO NOT EDIT.
  これは生成物。skills/source/body.md を編集すること。
  converter_version: 0.1.0
  build_input_digest: fc0364db68ed8849
-->

# 段階設計プロンプト (qgb design-stages、パターン B / C)

> 本セクションは Phase 5 qgb スキルの **オンデマンド読み込み正本**。
> body.md の trigger 表で「段階作って」「契約設計」「policy.json を作って」「stages を増やしたい」等の依頼に該当したときに読み込む。
>
> full モード: SKILL.md 内の埋め込み見出し「段階設計プロンプト (qgb design-stages、パターン B / C)」として配置。
> split モード: 独立 helper として配置 (= `prompts/design-stages.md`)。

## 1. 段階設計とは何か

qgb は **L1〜L6 のような固定階層を強制しない** (philosophy P10)。各プロジェクトは自分の対象系 (Web アプリ / CLI / バッチ / ドキュメント群 / プロンプト集 / 法務テンプレ等) に合わせて段階数 / 各段階の責務を設計する。

段階設計とは **「このプロジェクトで何を保証したいか」を機械的検査可能な単位に分解する作業**。設計後は `policy.json#stages[]` として固定され、`qgb run` がそれを順に実行する。

### 設計の柱

- **段階数の推奨レンジ**: 3〜7 (1〜2 は階層化の意味薄い、8 以上は単一責任原則破綻のサイン)
- **各段階に `responsibility` を明示** (一文、複数センテンスは単一責任違反の警告)
- **段階間は DAG** (循環禁止、線形は DAG の特殊ケース)
- **採用根拠は機械検査のみ** (P6 / P7)、LLM 主観評価で ALLOW を出さない
- **段階の選択は REQ メタの `stages[]`** (宣言外段階は判定対象外)

## 2. 設計プロセス: パターン B と パターン C の使い分け

qgb は段階設計の進め方として **2 つの公式パターン** を提供する。利用者の環境と作業スタイルに応じて選ぶ。

### パターン B (Phase 2 Step 2.5 で確立): external-LLM proposal/adopt 経路

**前提**: qgb 自身は LLM を一切呼ばない。LLM (= 本スキルを動かしている agent) が外部で段階設計を行い、proposal JSON として qgb に渡す。

**流れ**:

1. `python -m qgb design-stages propose-context [--out FILE]`
   - qgb が対象プロジェクトの自己定義 (`.quality-system/project-context.json` + `knowledge/project-context.md`)、設計例パック (`examples/`)、既存 `policy.json` / `knowledge.jsonl` をすべて JSON として書き出す
   - これは LLM への **入力素材** (context payload)
2. LLM (本スキル) がその context を読んで段階案を起草
   - `examples/` から近い 1〜3 例を参照 (few-shot)
   - 対象プロジェクトの `purpose` / `technologies` / `artifact_kinds` を踏まえる
   - 段階数 3〜7、各段階の responsibility を一文で書く
   - 段階間の DAG を決める
   - 各段階の `verification_type` (`command` / `file_exists` / `substring_match` / `json_schema` / `manual_check`) と `required_contract_fields` を決める
3. proposal JSON として書き出す (schema: `qgb/schemas/proposal.schema.json`)
4. `python -m qgb design-stages adopt <proposal.json>`
   - qgb が proposal を schema 検証 + 既存 `policy.json` / REQ メタとの整合検証
   - `human_reviewed: true` フィールドの存在を確認 (人間が承認したことの記録)
   - 検証通過なら `policy.json#stages[]` に焼き込み

**使うべき場面**:

- LLM が外部 LLM (= 本スキルを動かす agent) として動いている、つまり Phase 5 スキル経路の通常運用
- 人間が proposal を **承認するステップ** を明示的に挟みたい場合
- 設計判断の根拠を `proposal.basis[]` として記録に残したい場合 (audit trail として価値が高い)
- 複数案を比較検討してから 1 つを採用したい場合 (`propose-context` 経由なら別案を別 proposal として平行起草できる)

### パターン C (Phase 1 互換、自律実行): rule-based proposer

**前提**: qgb が rule-based に段階案を生成。`examples/generic-minimal` をデフォルトテンプレートとして提案、利用者が y/n/edit で確定。LLM 関与は最小。

**流れ**:

1. `python -m qgb design-stages [--commit] [--json]`
   - qgb が `examples/generic-minimal` の段階構造をテンプレートとして提案
   - `--commit` なしなら提案のみ、`--commit` で `policy.json` に焼き込み
   - `--json` で JSON 出力 (CI 用)

**使うべき場面**:

- 利用者が「とりあえず汎用最小段階で始めたい」「LLM 起草不要」と判断した場合
- CI 内で非対話的に段階を自動採用したい場合 (`--json` 出力を後続処理に流す)
- Phase 1〜2 で既に確立した運用との互換性を保ちたい場合

### B / C の選択判断 (Phase 5 スキル経路では B 推奨)

| 観点 | パターン B 推奨 | パターン C 推奨 |
|---|---|---|
| 設計判断の audit | 必要 (proposal.basis[]) | 不要 |
| 人間承認ステップ | 明示的に挟む | y/n で簡素 |
| 対象プロジェクト | 非自明 (ドキュメント群 / 法務テンプレ等) | 汎用 CLI / Web 等 |
| 初回設計 | B (LLM の理解を活かす) | C (テンプレ起点) |
| 段階の見直し | B (--revise 同型で B を再実行) | C (テンプレ差分で済む) |

**Phase 5 スキル経路では原則 B を推奨**。スキルを動かしている agent が LLM である以上、proposal/adopt 経路で audit trail を残すのが philosophy P6 (LLM 単独 ALLOW 禁止) との整合度が高い。

## 3. パターン B の詳細手順 (本スキル経路の中心)

### 3.1 propose-context の実行

```powershell
python -m qgb design-stages propose-context --out .quality-system/_proposal_input.json
```

出力 (JSON) の実際のトップレベル key は以下の 9 個 (`qgb/core/proposal.py` の `build_proposal_context()` が正本、body.md はここで実装と同期を保つ):

- `document_kind` / `schema_version` / `intended_use` / `intended_use_note` / `contains_executable_instructions`: この文書が「外部 LLM ツールへの入力素材であり ALLOW/DENY 判定根拠ではない」ことを機械可読な形で明示するメタデータ (P6/P8 framing)
- `project_context`: `.quality-system/project-context.json` の中身をそのまま (未整備なら `None`)
- `policy`: 既存 `policy.json` の中身をそのまま (`stages[]` 抜粋ではなくファイル全体)
- `reqs`: 各 REQ の `req_id` / `title` / `stages` (各 stage の `stage_id` / `required` / `waived`) の一覧、meta が読めない REQ は `load_error` 付きで記録
- `constraints`: `verification_types` 一覧、`manual_check_rule`、`recommended_stage_count`、`stage_id_rule`、`contract_layout`、`existing_req_compatibility`、`project_context_role` 等の機械可読な制約サマリ

**意図的に含まれないもの** (`build_proposal_context()` の docstring が理由を説明): `knowledge.jsonl` の中身、`project-context.md` の抜粋、`examples/` の pointer リスト、philosophy 原文の要約は **含まれない**。これらは Phase 3 Step 3.0 以降 deliberately minimal/stable な構造として除外されている。代わりに LLM (本スキル) は以下を **`Read` tool で直接読む**:

- `.quality-system/knowledge/project-context.md` (人間正本、自然言語の設計意図)
- `.quality-system/knowledge/knowledge.jsonl` (waiver / 外部知識記録、必要な範囲だけ)
- `examples/<example>/design-notes.md` + `policy.json` (few-shot 参照、本文 §7.2 に一覧がある 6 例から自分で選ぶ)
- `philosophy.md` (P5〜P12 原文、本文 §3 の 4 原則サマリで足りなければ直接参照)

### 3.2 段階案の起草 (LLM 責務)

LLM (本スキル) は context を読んで段階案を JSON で起草する。最低限の構造:

```json
{
  "proposal_version": "1.0",
  "policy_id": "default",
  "stages": [
    {
      "id": "S1",
      "name": "コマンド成立",
      "responsibility": "CLI コマンドが終了コード 0 で完了する",
      "depends_on": [],
      "verification_type": "command",
      "required_contract_fields": ["command", "expected_exit_code"]
    },
    {
      "id": "S2",
      "name": "出力契約",
      "responsibility": "出力ファイルが JSON Schema を満たす",
      "depends_on": ["S1"],
      "verification_type": "json_schema",
      "required_contract_fields": ["target", "schema"]
    }
  ],
  "basis": [
    {"type": "example", "ref": "examples/python-cli-pytest/", "rationale": "Python CLI の典型段階構造として参照"},
    {"type": "philosophy", "ref": "P10", "rationale": "段階の可変性を尊重、対象に応じて 4 段階に絞った"},
    {"type": "project_context", "ref": ".quality-system/project-context.json#purpose", "rationale": "purpose = '入力検証 + 変換' から S1〜S4 を導出"}
  ],
  "human_reviewed": false,
  "notes": "S4 (異常系) を分離した理由: 不正入力の安全な拒否を別段階で保証 (P1 一要求一外部化)"
}
```

### 3.3 人間承認

LLM は `human_reviewed: false` のまま proposal を出す (P8 違反になるため自動 true 化禁止)。利用者が proposal を読んで承認したら `human_reviewed: true` に書き換える (手動編集 or 確認 UI 経由)。

### 3.4 adopt の実行

```powershell
python -m qgb design-stages adopt .quality-system/_proposal_input.json
```

qgb が以下を機械検証:

- proposal schema 検証
- `human_reviewed: true` の確認 (false なら error)
- DAG (循環なし)
- stage id 一意
- responsibility 非空
- verification_type が定義済み列挙値
- 既存 `policy.json` がある場合は変更差分を提示

検証通過なら `policy.json#stages[]` に書き込み。**書き込みは atomic swap** (途中状態が残らない、Phase 2 規律)。

### 3.5 整合性の機械検証

`policy.json` 更新後、必ず:

```powershell
python -m qgb validate-policy
```

を実行。Phase 1 必須検査項目 (stage id 重複なし / depends_on の DAG / responsibility 存在 / contract layout 等) が機械検査される。blocker があれば修正して再実行。

## 4. パターン C の詳細手順 (Phase 1 互換)

```powershell
# 提案のみ (policy.json は書かない)
python -m qgb design-stages

# 採用 (policy.json に焼き込み)
python -m qgb design-stages --commit

# CI 用 JSON 出力
python -m qgb design-stages --json
```

`examples/generic-minimal` の 2 段階構造 (S1: コマンド成立、S2: 出力契約) がデフォルトで提案される。利用者が y/n/edit から選ぶ。

**注意**: パターン C はテンプレ起点のため、対象プロジェクトの自己定義 (`project-context.{md,json}`) は反映されない。対象が generic-minimal から外れる場合はパターン B を選ぶ。

## 5. 設計時の典型的判断ポイント

### 5.1 段階数をどう決めるか

| 状況 | 推奨 |
|---|---|
| CLI で出力 1 種、異常系少 | 2-3 段階 |
| CLI + 出力 + 異常系 + 結合 | 4-5 段階 |
| Web API + schema + 結合 + 性能 + 異常系 | 5-7 段階 |
| ドキュメント群 (link 整合 + 用語統一 + 構造) | 3-4 段階 |
| プロンプト集 (構文 + 命名 + 重複) | 3 段階 |

8 段階以上を提案するときは「責務を細かく切りすぎていないか」を再点検 (P9 単一責任)。

### 5.2 verification_type の選択

| やりたいこと | type |
|---|---|
| コマンド実行して exit code 確認 | `command` |
| ファイル存在確認のみ | `file_exists` |
| ファイル内テキスト含有確認 | `substring_match` |
| JSON ファイルの schema 適合 | `json_schema` |
| 人間の目視確認 | `manual_check` (採用判定の根拠にできない、P6) |

`manual_check` を含む段階を `required: true` で参照する REQ は `qgb run` で NOT_READY エラー。LLM レビューや人間目視は採用根拠から分離するのが philosophy の核 (「レビュー観点プロンプト」参照、full: SKILL.md 内の埋め込み見出し / split: `prompts/review-policy.md`)。

**LLM/VLM を組み込んだ評価プログラムは `command` 型の判定機として採用できる** (philosophy P12)。ただし採用の規律を守る: モデル・プロンプト・集約手続き (多数決/平均/閾値)・判定基準の固定と版管理、実行ごとの証跡、校正記録 (人間ラベルとの一致率等)、人間による採用承認。評価主体は被評価物の生成者・本スキルを動かす agent と利害を共有しない構成が原則 (逸脱は理由付き宣言 + 評価機設計段階での人間の承認決裁が条件)。

### 5.3 depends_on の決め方

- 「段階 B は段階 A の結果に依存するか」を 1 つずつ確認
- 線形依存 (S1 → S2 → S3) が典型、その特殊ケースとして「S2 と S3 は独立、S4 が両方依存」のような DAG もあり得る
- 循環は禁止 (`qgb validate-policy` で検出)

### 5.4 REQ メタでの stage 選択

各 REQ は `policy.json#stages[]` のサブセットを宣言する。

- 全 REQ が全段階を見る必要はない (P1 一要求一外部化)
- `required: true` の段階のいずれかが failed なら DENY
- 宣言外段階は判定対象外 (出現しない)

例: REQ-DOC-001 (ドキュメント REQ) は `command` 段階を含まず、`file_exists` + `substring_match` + `link_integrity` だけを宣言、等。

### 5.5 capability-based dispatch checklist (verification_type=command 選択時の runtime checklist)

> 本節は **作成物性質 (= script file の拡張子 / runtime 種別) で分岐する checklist**。自然言語キーワードでなく capability で adapter を切り替える設計 (Phase 5 Step 5.a-2-4 で確立、Codex 推奨 ι)。
>
> body.md §6.5 「command authoring protocol」の step 5 runtime-specific preflight で参照される。

#### 共通前提

`verification_type=command` を選んだ時点で:

1. 利用者環境の runtime を 1 つに **確定** する (PowerShell 5 vs 7、bash vs zsh 等の曖昧さを残さない)
2. 確定した runtime に対応する下記 checklist の **全項目を proposal `basis[]` で言及** する (人間が承認するときの確認点)
3. checklist に該当しない新 runtime (例: Ruby / Perl / 独自 binary 等) を採用する場合、design-notes.md に **新 runtime checklist** を追記して proposal に含める

#### PowerShell 5 / 7 (Windows native)

| 観点 | checklist |
|---|---|
| script 保存 encoding | PS 5: **UTF-8 BOM 付き** 必須 / PS 7: UTF-8 BOM なしも可、ただし PS 5 と互換にするなら BOM 付き default |
| script 改行コード | LF (`.gitattributes` で `*.ps1 text eol=lf` 強制済) |
| 冒頭設定 | `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` + `$ErrorActionPreference = 'Stop'` |
| `$OutputEncoding` | 必要なら `$OutputEncoding = [System.Text.Encoding]::UTF8` (child process 渡し encoding) |
| argv | PS 5: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <script.ps1>` / PS 7: `pwsh -NoLogo -NoProfile -NonInteractive -File <script.ps1>` 完全明示 |
| profile load | `-NoProfile` で利用者 profile を読まない (確定動作) |
| execution policy | `-ExecutionPolicy Bypass` (利用者の policy 設定に依存しない、CI 環境で重要) |
| 文字化け検出 | qgb check 後の stage log で `U+FFFD` を grep (κ mojibake sentinel) |
| 日本語コメント / string | BOM 付きなら直接書ける / BOM なしを維持したいなら `[char]0x<codepoint>` で Unicode escape 構築 (pure ASCII script化、`skills/source/hooks/{claude-code,codex}/scripts/check-relevance.ps1` の手法) |

#### bash / sh (POSIX, Linux / macOS / WSL / Git Bash)

| 観点 | checklist |
|---|---|
| script 保存 encoding | UTF-8 BOM なし (BOM 付きだと shebang が parse 失敗する) |
| script 改行コード | LF 必須 (CRLF は shebang が壊れる) |
| shebang | `#!/usr/bin/env bash` (POSIX portable) |
| executable bit | `chmod +x <script.sh>` (.gitattributes では設定不可、利用者環境 / CI で適用) |
| 冒頭設定 | `set -euo pipefail` (error / undefined var / pipe 失敗で即終了) |
| locale | `export LC_ALL=C.UTF-8` (script 冒頭で固定、利用者 locale に依存しない) |
| argv | `bash <script.sh>` (shebang + executable bit に依存しない portable 形) または `./script.sh` (executable bit 必要) |
| 文字化け検出 | qgb check 後の stage log で `U+FFFD` を grep |

#### Python (CPython 3.7+)

| 観点 | checklist |
|---|---|
| script 保存 encoding | UTF-8 (BOM なし、Python 3 default、PEP 3120) |
| script 改行コード | LF |
| 冒頭 | `# -*- coding: utf-8 -*-` は Python 3 では不要、書かない (Python 2 互換のためだけのレガシー) |
| UTF-8 mode | `python -X utf8 <script.py>` (Python 3.7+) または `PYTHONUTF8=1` 環境変数 (Windows 日本語環境で必須、Linux でも安全) |
| stdout reconfigure | script 冒頭で `import sys; sys.stdout.reconfigure(encoding='utf-8', errors='strict')` (Python 3.7+、errors='strict' で誤 encode を fail-fast) |
| argv | `python -X utf8 <script.py>` (UTF-8 mode 明示) |
| exit code | `sys.exit(0)` / `sys.exit(1)` を明示 |
| 文字化け検出 | qgb check 後の stage log で `U+FFFD` を grep + `sys.stdout.reconfigure(errors='strict')` で encode 失敗を捕捉 |

#### Node.js (LTS 18+)

| 観点 | checklist |
|---|---|
| script 保存 encoding | UTF-8 BOM なし |
| script 改行コード | LF |
| module system | `--input-type=module` (ESM 明示) または `.mjs` 拡張子 (CommonJS でも可だが ESM 推奨) |
| stdout encoding | Node 18+ では default UTF-8、`process.stdout.write` で確認 |
| locale | 環境依存最小 (Node は locale 影響少) |
| argv | `node <script.mjs>` (Node version は package.json `engines` で固定推奨) |
| exit code | `process.exit(0)` / `process.exit(1)` |
| 文字化け検出 | qgb check 後の stage log で `U+FFFD` を grep |

#### Go binary / Rust binary / 他 compiled (利用者プロジェクトが事前ビルド済 binary を契約に使う場合)

| 観点 | checklist |
|---|---|
| binary 配置 | `.quality-system/bin/` or 利用者プロジェクト指定 path、絶対 path で contract.command 宣言 |
| 改行コード | binary 出力次第 (script でないので encoding 規律は binary 側の責任) |
| stdout encoding | binary 側が UTF-8 で出力していることを確認 (`U+FFFD` 検出で監視) |
| argv | `<absolute_path_to_binary> <args>` 完全明示 |
| exit code | binary の exit code 規約に従う |
| version 管理 | binary version を `project-context.json#technologies` に記録、再現性を担保 |

#### Markdown lint / link checker / 他 文書系 tool

| 観点 | checklist |
|---|---|
| tool 選択 | `markdownlint-cli2` (Node), `lychee` (Rust binary), `vale` (Go binary) 等 |
| 配置 | npm / cargo / brew で利用者 install、または .quality-system/bin/ に同梱 |
| 上記の runtime 規律に従う (Node なら Node section、binary なら binary section) |

#### lint helper script の自動適用

skill が `verification_type=command` の contract を起草した直後、`skills/source/lint/check-command-contract.{ps1,py}` (Step 5.a-2-4 段階 4 で実装) を実行:

1. 確定 runtime と script 拡張子の整合 (例: PowerShell 5 確定なのに `.sh` を指定していたら error)
2. 上記 checklist の必須項目 (BOM / shebang / encoding / argv / exit code) のうち、機械検査可能な項目を check
3. `qgb check` 実行後の stage log で `U+FFFD` を grep

これは **proposal adopt 前の skill 内部 lint**、qgb 本体機能ではない (philosophy P9 + framework-shape §5 境界遵守、qgb 本体は contract に書かれたものを実行するだけ)。

## 6. 設計後の見直しフロー (`--revise` 相当)

段階を増やしたい / 減らしたい / 名称を変えたいとき:

1. **段階追加**: パターン B で新 proposal を起こし adopt 経路で追加
   - 新段階を含む REQ から `stages[]` で参照
   - `qgb validate-policy` で DAG / 整合性確認
2. **段階削除**: REQ メタで該当 stage を参照している箇所をすべて削除してから `policy.json#stages[]` から削除
   - 参照が残っているまま削除すると `qgb validate-policy` で error
3. **段階の `id` 変更**: 既存 REQ メタの `stage_id` 参照が壊れるため、警告 + 連動更新
   - 推奨: id は固定、名称 (`name`) や責務 (`responsibility`) の修正で対応

## 7. アンチパターンと回避

### 7.1 `manual_check` で ALLOW を出そうとする

❌ `manual_check` を含む REQ で `qgb run` を強行 → NOT_READY エラー。

✅ `manual_check` は別 REQ に分離し、機械化された段階と別経路で扱う。または `human_attestation` 型 (Phase 2 以降) を待つ。

### 7.2 段階を細かく切りすぎる (8 段階以上)

❌ S1 (コマンド) / S2 (exit code) / S3 (stdout 存在) / S4 (stdout 形式) / S5 (... ) と細かく分けすぎ。

✅ 責務を 1 段階に統合 (「コマンド成立」段階で exit code + stdout 確認まで含める)。`qgb validate-policy` の警告を尊重。

### 7.3 `responsibility` を複数センテンスで書く

❌ `"responsibility": "CLI コマンドが exit code 0 で完了する。stdout に期待する文字列が含まれる。stderr に warning がない。"` → 単一責任違反、警告。

✅ 1 文に絞る (`"CLI コマンドが exit code 0 で完了する"`)、追加要件は別段階に。

### 7.4 LLM 主観評価で ALLOW を出す

❌ proposal の `basis[]` に「LLM レビュー結果は問題なし」と書いて ALLOW を主張。

✅ LLM レビューは **advisory のみ**、「レビュー観点プロンプト」の規律に従う (full: SKILL.md 内の埋め込み見出し / split: `prompts/review-policy.md`)。ALLOW は機械検査の通過だけ。

### 7.5 `human_reviewed: true` を LLM が自動で立てる

❌ LLM (本スキル) が proposal 起草と同時に `human_reviewed: true` を立てる → P8 違反 (外部内容を上位指示として扱う)。

✅ LLM は `false` のまま出す、人間のみが `true` に書き換える。

## 8. 関連参照

- `philosophy.md` P5 / P6 / P7 / P8 / P9 / P10 / P11 / P12
- `stage-design.md` 段階設計フェーズ仕様 v1.0 (本スキルの上位仕様)
- `requirements_and_development.md` §6.4 (validation flow)
- `examples/generic-minimal/`, `examples/python-cli-pytest/`, `examples/markdown-docs/`, `examples/python-fastapi-pytest/`, `examples/go-cli/`, `examples/node-cli-vitest/` (設計例パック、few-shot 用)
- 「レビュー観点プロンプト (qgb 利用時の LLM レビューの境界)」(本セクションと姉妹、full: SKILL.md 内の埋め込み見出し / split: `prompts/review-policy.md`)

