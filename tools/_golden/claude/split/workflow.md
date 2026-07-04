<!--
  GENERATED FILE - DO NOT EDIT.
  これは生成物。skills/source/body.md を編集すること。
  converter_version: 0.1.0
  build_input_digest: fd3eb4afcb7b1c88
-->

## 6. 作業手順

(本セクションは full モード: SKILL.md 内の埋め込み見出し / split モード: `workflow.md` 別ファイル。)

### 6.1 初期化フロー

利用者から「qgb 入れて」「セットアップ」と依頼されたとき:

1. **利用者プロジェクトの状況確認**
   - 現在のディレクトリ (`pwd`)、git 状態 (`git status`)、既存ファイル (`ls -la`)、`README.md` の冒頭
   - 利用者プロジェクトの種類 (CLI / Web / ドキュメント等) を**自律判断せず利用者に確認**する (アダプタ的な機械検出は qgb 本体が撤回した方針、対象認識は LLM 責務)
2. **`python -m qgb init` を実行**
   - `.quality-system/` 配下が生成される
   - 既に存在する場合は `InitError` で停止 → 利用者に上書き可否を確認
3. **`project-context.md` (人間正本) を起草**
   - 利用者から目的 / 対象範囲 / 採用しない方式 / 参照文書を聞き取り、`.quality-system/knowledge/project-context.md` に Markdown で書く
   - 「言語判定」「フレームワーク判定」を agent が肩代わりしない (adapter 量産方針と同じ問題が再発する、Phase 3 Step 3.0 教訓)
4. **`project-context.json` (機械正本) を補佐 Agent として起草**
   - `project-context.md` を読んで `.quality-system/project-context.json` に構造化
   - `source_metadata.generated_by: "agent-assisted"` を立てる
   - `human_reviewed: true` は **人間のみが立てる** (P8 違反になる)、agent は `false` のまま
5. **`python -m qgb scaffold REQ-APP-001` で最初の REQ を生成**
   - `req/REQ-APP-001.md` + `req/REQ-APP-001.meta.json` + `contracts/REQ-APP-001/<stage>.json` のひな型
   - 利用者と要求内容を対話して `REQ-APP-001.md` 本文を埋める
6. **`python -m qgb validate-policy` で機械検証**
   - `config.json` / `policy.json` の存在、契約の DAG、`manual_check`-only REQ の警告
   - blocker があれば修正して再実行

### 6.2 REQ 設計フロー

利用者から「REQ 追加」と依頼されたとき:

1. **REQ ID の確定** (`REQ-<DOMAIN>-<NNN>` 形式、利用者と相談)
2. **`python -m qgb scaffold REQ-XXX-NNN`** でひな型生成
3. **REQ 本文の起草** (`req/REQ-XXX-NNN.md`)
   - 何を達成したいか (acceptance criteria)
   - どの段階で検証するか (`responsibility` の方針)
   - 関連する既存 REQ / contract への参照
4. **段階別 contract の設計** (`contracts/REQ-XXX-NNN/<stage>.json`)
   - 各段階で実行する機械検査 (verification_type: command / file_exists / substring_match / json_schema)
   - **`command` の場合は必ず §6.5「command authoring protocol」を適用**する (任意の文字列を書けるが、runtime 規律を組み込まないと環境依存で動かない / 文字化けする / 利用者プロジェクトで運用上問題が起きる)
   - LLM レビューは `manual_check` 段階に分離、ALLOW 判定の根拠にしない (P6)
5. **`python -m qgb validate-policy REQ-XXX-NNN`** で機械検証
6. **`python -m qgb check REQ-XXX-NNN`** でリハーサル実行
   - `artifacts/REQ-XXX-NNN/checks/<ts>/` に揮発出力
   - curated evidence は更新しない
7. **問題なければ `python -m qgb run REQ-XXX-NNN`** で本実行
   - `evidence/REQ-XXX-NNN/latest/gate.json` が生成される

### 6.3 デバッグフロー

「pytest が失敗」「gate.json が DENY」「ALLOW が出ない」と依頼されたとき:

1. **`gate.json` を読む**
   - `decision.result` (ALLOW / DENY / NOT_READY)
   - `decision.meaning` (限定の明示)
   - `basis[]` (どの REQ / CONTRACT / POLICY / WAIVER が判定根拠か)
   - `stages[].result` で個別段階の結果
2. **`stages[*].log_ref` の log ファイルを読む** (`evidence/REQ-XXX/latest/stages/*.log`)
   - `reason` フィールド (Phase 3 Step 3.1 で導入: `command_timeout` / `stdout_cap_exceeded` / `stderr_cap_exceeded` 等)
   - log 末尾 64 KiB が保存されている (実行 cap は別、16 MiB)
3. **DENY 原因の分類**
   - **契約検査失敗**: コマンドの exit code != 0、log を見て修正
   - **タイムアウト**: `contract.timeout_seconds` を調整 (理由を `decision.meaning` に明示)
   - **出力 cap 超過**: `reason=stdout_cap_exceeded` 等、コマンド出力を抑える / 別段階に分離
   - **構成不備**: NOT_READY → `qgb validate-policy` で blocker を解消
4. **修正後 `qgb check` でリハーサル**、問題なければ `qgb run`

### 6.4 構造化編集フロー

「contract を編集」「JSON Patch」と依頼されたとき:

1. **直接ファイル編集は避ける** (Phase 2 で確立した規律)
2. **JSON Patch で構造化編集** (`python -m qgb patch <target> <patch.json>`)
   - op: add / replace / remove / test (移動 / 複製は WONTFIX)
   - atomic swap で書き込み (途中状態が残らない)
3. **waiver 追加** は `python -m qgb add-waiver REQ-XXX stage --reason ...` 経由
   - knowledge.jsonl に自動記録、`gate.json.basis[]` で参照可能
4. **knowledge 追加** は `python -m qgb add-knowledge <file>` 経由

### 6.5 command authoring protocol (verification_type=command の共通プロトコル)

> 本節は **すべての `verification_type=command` 契約に共通する invariant**。日本語文書執筆プロジェクト + Windows PowerShell 5 のような特定組み合わせの固有問題ではなく、すべての command contract に適用する一般プロトコル (Phase 5 Step 5.a-2-4 で確立、Codex 推奨 θ)。

#### 構造 trigger

利用者から「契約段階を作って」「policy.json を設計して」「command 契約を追加して」「.ps1 で検査したい」「Python script で検査したい」等の依頼があり、**verification_type=command の contract を新規作成 / 既存編集**するとき、必ず本プロトコルを適用する。キーワードでなく **「contract が command を含むか」** で trigger 判定。

#### 7 step プロトコル

1. **context 取得**
   - 対象プロジェクトの `.quality-system/project-context.{md,json}` を Read
   - 利用者の target OS (Windows / macOS / Linux)、shell (PowerShell 5 / 7 / bash / zsh)、locale (ja-JP / en-US 等) を確認 (利用者に直接質問、または既存 script から推定)
   - runtime (PowerShell / Python / Node / Go binary 等) の version を確認
2. **verification type 選択**
   - `command` 以外で十分なら `file_exists` / `substring_match` / `json_schema` を優先 (command は副作用とエラーモードが多く、避けられるなら避ける)
   - command 必須なら本プロトコル続行
3. **runtime 解決**
   - 利用者環境で実行される runtime を一意に確定 (例: PowerShell 5 か 7 か、bash か zsh か)
   - cross-platform 化が必要なら **runtime ごとに別 contract** を用意 (`<stage>-windows.json` / `<stage>-posix.json` 等) または **wrapper script** で吸収
   - **曖昧さを残さない** (Phase 5 v4 確定方針)
4. **script / argv 生成**
   - 確定 runtime に対応する script を skill が起草 (利用者 review 必須)
   - argv は **runtime の規約に従って完全に明示**:
     - PowerShell: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <script.ps1>` (PS 5)、`pwsh -NoLogo -NoProfile -NonInteractive -File <script.ps1>` (PS 7+)
     - bash: `bash <script.sh>` (shebang + executable bit を依存しない、portable)
     - Python: `python -X utf8 <script.py>` (Python 3.7+ で UTF-8 mode、Windows 日本語環境で `PYTHONUTF8=1` 推奨)
     - Node: `node --input-type=module <script.mjs>` 等、Node version を意識
5. **runtime-specific preflight (= ι capability-based dispatch、§12 参照)**
   - 確定 runtime に対応する checklist を §12「段階設計プロンプト」の capability-based dispatch checklist から読み込んで適用
   - PowerShell 5 + 非 ASCII なら BOM 必須 / `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` 設定必須 等
   - bash なら shebang + executable bit + LC_ALL=C.UTF-8 設定必須 等
6. **`python -m qgb check REQ-XXX-NNN`** でリハーサル実行
   - artifacts/REQ-XXX-NNN/checks/<ts>/ に揮発出力、curated evidence 不更新
   - **stage log に U+FFFD (replacement character) が含まれていないか確認** (= κ mojibake sentinel、cp932→UTF-8 誤 decode の検出)
7. **evidence 確認**
   - stage log を Read、command の stdout / stderr が **正しく UTF-8 として読める**ことを目視確認
   - 文字化け (`�`) があれば step 5 preflight に戻って encoding 規律を修正
   - 期待 exit code / 期待 stdout が出ているか確認

#### PowerShell 5 規律 (1 具体化、最頻ケース、Windows native 利用者向け)

Windows PowerShell 5 (Windows 標準同梱) + 日本語環境で `.ps1` 契約を書く場合の必須規律:

| 観点 | 規律 |
|---|---|
| script 保存 encoding | **UTF-8 BOM 付き** 必須 (BOM なしは PowerShell 5 が cp932 として誤読し parse error) |
| `[Console]::OutputEncoding` | script 冒頭で `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` 設定 (qgb の utf-8 decode 契約に整合) |
| `$OutputEncoding` | 必要に応じて `$OutputEncoding = [System.Text.Encoding]::UTF8` (PowerShell が child process に渡す encoding) |
| argv | `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <script.ps1>` 完全明示 (profile load を避けて確定動作) |
| `$ErrorActionPreference` | `$ErrorActionPreference = 'Stop'` (error で即終了、exit code 1 を qgb が拾える) |
| 改行コード | LF (`.gitattributes` で `*.ps1 text eol=lf` 強制済、CRLF を避ける) |
| 文字化け検出 | qgb check 後の stage log で `U+FFFD` を grep、見つかれば修正 (κ mojibake sentinel) |

PowerShell 7+ (`pwsh`) は UTF-8 BOM なしでも .ps1 を正しく読むが、利用者環境が PowerShell 5 か 7 か判別困難なケースがあるため **BOM 付き UTF-8 を default 推奨**。

ASCII safe alternative (pure ASCII + Unicode escape) は `skills/source/hooks/{claude-code,codex}/scripts/check-relevance.ps1` で採用済の手法、PowerShell 5/7 両対応かつ BOM 不要だが利用者が JP 文字列を直接書きたい場合は不適。

#### 他 runtime の規律 (概要、詳細は §12 capability-based dispatch checklist 参照)

- **bash (POSIX)**: shebang + executable bit + `LC_ALL=C.UTF-8` 設定 + 改行 LF
- **Python**: `python -X utf8` または `PYTHONUTF8=1` + `sys.stdout.reconfigure(encoding='utf-8')` + 改行 LF + 必要なら `# -*- coding: utf-8 -*-` (Python 2 系で書く場合のみ、Python 3 系では不要)
- **Node**: `--input-type=module` (ESM 明示) + `process.stdout.write` で UTF-8 確認 + locale 環境変数
- **Go binary / 他 compiled**: build artifact の path + argv 完全明示、stdout encoding は binary 側の責任

これらの詳細は §12 「段階設計プロンプト」の capability-based dispatch checklist 節に runtime ごとに展開。

#### lint helper script (skill 同梱)

`skills/source/lint/check-command-contract.ps1` (Windows native PowerShell) と `skills/source/lint/check-command-contract.py` (cross-platform Python) を skill 同梱で提供。command contract を Write した直後に skill が以下を機械検査:

1. PowerShell 5 対象かつ非 ASCII `.ps1` なのに BOM がない
2. `.ps1` を `shell=False` の argv で直接起動しようとしている
3. stdout encoding の初期化または実行確認がない
4. command が存在しない runtime を指定している
5. `qgb check` の log に `U+FFFD` がある

dist build 時に converter が `dist/skills/{full,split}/<agent>/lint/` 配下に copy。

