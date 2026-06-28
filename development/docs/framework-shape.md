# フレームワーク境界 v1.0

## 1. 本書の位置づけ

本書は、qgb におけるフレームワーク側（このリポジトリ）と利用者プロジェクト側の境界を定める。

各層の責務、所有物、変更主体を明示することで、qgb 本体に開発過程の履歴が残ること、利用者プロジェクトに不要なフレームワーク内部物が漏れることを防ぐ。

本書は思想憲章 (`philosophy.md`) のうち、特に P4（不易と流行の分離）の運用化を担当する。

## 2. 4 層構造

qgb プロジェクトは次の 4 層で構成される：

```text
[Layer 1] 思想層 — qgb が固定する不易
   ↓ 制約を与える
[Layer 2] フレームワーク層 — qgb 本体（このリポジトリ）
   ↓ 道具を提供する
[Layer 3] スキル層 — Phase 5 のスキル（エージェント中立、Claude Code + Codex CLI 向けにビルド）
   ↓ 適応・対話する
[Layer 4] 利用者プロジェクト層 — qgb init 後の対象プロジェクト
```

各層は明確な所有物と責務を持ち、上位層から下位層への一方向の依存関係を保つ。

Layer 3 のスキルは Claude Code / Codex CLI に投入できる (Phase 5 v4 で supported = Claude Code + Codex CLI に確定、Antigravity CLI は GitHub issue で TODO、Gemini CLI は扱わない)。詳細は §5 を参照。

## 3. Layer 1: 思想層

### 所有物

- `development/docs/philosophy.md` — 思想憲章

### 変更主体

qgb メンテナのみ。改訂は厳格に扱い、バージョン番号を上げる。

### 利用者プロジェクトへの複製

しない。利用者は qgb リポジトリの philosophy.md を直接参照する。

### 上位層

なし（最上位）。

## 4. Layer 2: フレームワーク層（qgb 本体）

### 置くもの

- `qgb/` Python パッケージ本体
  - `core/` — runner, command, _win_job, _win_bat_escape, decision, evidence, schema, patch, patch_apply, knowledge, edit_commands, preflight, proposal, design_stages, init, scaffold, validate, loader, json_pointer, check
    - `command` — Phase 3 Step 3.1 で `runner._run_command` を切り出し、Step 3.1 補修群でステート空間の不在化を完了 (`_CapExceededState`、supervisor 観測契機 ≠ 最終結果、reader.join timeout なし)
    - `_win_job` — Windows Job Object 経由の process tree kill。`spawn_suspended_and_resume` で transactional cleanup (Step 3.1 補修 #2/#3)
    - `_win_bat_escape` — `.bat`/`.cmd` の cmd.exe メタ文字 + MSVCRT 二段エスケープ (Step 3.1d + 補修 #4 で argv[0] にも均一適用)
  - ~~`adapters/`~~ **Phase 3 Step 3.0 (2026-06-21) で廃止**。対象プロジェクトの分析は Phase 5 スキル (LLM) の責務、qgb 本体は機械的検査に徹する
  - `schemas/` — JSON Schema 群（gate, gate.runtime, policy, contract, knowledge, req-meta, config, patch, proposal, project-context）
    - gate / gate.runtime には Step 3.1c 以降、`stages[].reason` (enum: command_timeout / stdout_cap_exceeded / stderr_cap_exceeded) と `stages[].runner_warning` (optional string) が追加されている
  - `templates/` — 生成テンプレート（REQ.md, contract.\*.json, summary.md, project-context.{md,json}, quality-gate.ps1）
- `development/docs/` — 開発文書
  - 思想憲章、要件定義書、段階設計仕様、フレームワーク境界（本書）
  - プロジェクト経緯、参考実装情報、発表資料まとめ
- `examples/` — 設計例パック（複数の対象系での段階設計例）
- `tests/` — qgb 本体のテスト
- `skills/` — Phase 5 のスキル定義（Layer 3）
- ルートファイル: `pyproject.toml`, `README.md`, `LICENSE`, `.gitignore`

### 置かないもの

- 開発過程の議論ログ、引き継ぎ資料
- 一度限りの移行・棚卸し資料
- 利用者プロジェクト固有の REQ（examples 内のサンプルは別、これはフレームワークの一部）
- 内部調整の会話記録、設計検討の途中経過
- ChatGPT / Claude / Codex などのチャットログ
- 開発者個人の作業メモ

これらは git 履歴と Issue で追えれば十分であり、リポジトリ本体に常駐させない。

### 変更主体

qgb メンテナ。実装の追加・修正・テストの拡張。

### 利用者プロジェクトへの複製

しない。利用者は git clone で qgb を取得し、`python -m qgb` 経由で実行する。Phase 2 以降で PyPI 配布を検討する場合も、配布物は本層に限定する。

### command runner の動作契約 (Step 3.1 で確立)

Layer 2 の `qgb.core.command.run_command` は、利用者が与えた foreground command を実行し、その正常な完了経路で観測できた機械的検査の事実を gate.json に記録する。具体的に **機械的に担保する** ものは:

- **timeout**: `contract.timeout_seconds` (default 60s) を超えたコマンドは process tree ごと kill し、`stages[].reason = "command_timeout"` を gate.json に記録する
- **per-stream execution cap**: stdout / stderr それぞれ 16 MiB を超えた時点で process tree ごと kill し、`stages[].reason = "stdout_cap_exceeded"` または `"stderr_cap_exceeded"` を記録する。最悪保持量は約 35 MiB (stdout 16 MiB + stderr 16 MiB + log 構築バッファ)
- **process tree termination**: POSIX は `preexec_fn=os.setsid` + `killpg(SIGTERM)` → grace 3s → `killpg(SIGKILL)`、Windows は `WindowsJob` (CreateJobObject + KILL_ON_JOB_CLOSE) + `TerminateJobObject` + transactional spawn (assign/resume 失敗時は子を kill+wait してから raise)
- **structured reason**: `stages[].reason` enum と `stages[].runner_warning` (kill 経路の degradation を構造化フィールドで残す) で gate.json の証跡が事実を語る (philosophy P7)
- **.bat / .cmd argument escaping**: Windows の `.bat` / `.cmd` 起動では cmd.exe メタ文字 (`& | < > ( ) % ^`) と MSVCRT argv parsing の両層を、argv[0] (script path) を含む全 item に均一に適用する
- **observation vs final result の分離**: supervisor loop は早期離脱契機を観測するだけで、最終結果 (cap > timeout > natural exit の優先順) は reader thread 完了後に確定する

これらの契約は philosophy P5 (ALLOW の意味限定) / P7 (再現可能な証跡) / P9 (段階単一責任) の機械側担保。

## 5. Layer 3: スキル層（Phase 5、エージェント中立）

### 構造 (A1' = body.md 単一正本、Phase 5 Step 5.a-2-2 で確定)

Layer 3 は **A1' 単一正本 + コンバータ + Claude Code/Codex CLI 向け成果物** で構成される：

```text
skills/source/                   # 中間表現（正本、リポジトリで保守）
  metadata.yaml                  # thin typed manifest (build matrix 宣言)
  metadata.schema.json           # JSON Schema 型固定
  body.md                        # authored source 正本
                                 # (full モード本文 + split helper 本文を
                                 #  include marker で内包する単一ファイル)

tools/build_skill.py             # コンバータ（リポジトリで保守）

dist/skills/                     # ビルド成果物（.gitignore、リリース時に生成）
  full/
    claude/   SKILL.md           # 単一ファイル (helper を本文に embed)
    codex/    SKILL.md
  split/
    claude/
      SKILL.md
      workflow.md                # body.md include marker から converter 生成
      references.md              # 同上
      prompts/
        design-stages.md         # 同上
        review-policy.md         # 同上
    codex/  (同構造)
```

`workflow.md` / `references.md` / `prompts/design-stages.md` / `prompts/review-policy.md` は **`skills/source/` には存在しない** (A1' = body.md 単一正本)。これらは body.md 内の include marker (`<!-- split:helper_start <NAME> --> ... <!-- split:helper_end -->`) から converter が split build で機械生成し、`dist/skills/split/{claude,codex}/` 配下にのみ現れる。

### 中間表現の役割

`skills/source/` がスキルの正本。各エージェント向け成果物はすべてここから派生する。

- `metadata.yaml` — thin typed manifest (skill_id / version / description / converter_min_version / source_files / build_modes / target_agents、Phase 5 v4 case C で確定)
- `metadata.schema.json` — JSON Schema 型固定
- `body.md` — スキル本体 (中立 Markdown)、split build で個別 helper として配置される章を include marker で内包

`metadata.yaml` の例 (A1' 完成形):

```yaml
skill_id: qgb
version: 0.1.0
description: |
  qgb (quality-gate-builder) を使って任意のプロジェクトに証跡ゲート
  (REQ → contract → 機械検査 → ALLOW/DENY) を構築するスキル。
converter_min_version: 0.1.0

source_files:
  - body.md              # A1' で source は body.md のみ

build_modes:
  - full                 # 全部のせ (helper 内容を SKILL.md に embed)
  - split                # 分離 (helper を別ファイルとして配置)

target_agents:
  - claude               # Claude Code
  - codex                # Codex CLI
```

`agent_bindings` は Phase 5 v4 で廃止 (二重管理回避)。agent 別の変換規則は `tools/build_skill.py` が持ち、agent 状態 (status / last_verified / hook_support 等) は `development/docs/skill-converter/agent-{name}.md` の front matter で 1 か所だけ管理する。

### 集合分離契約 (A1' 核心)

- `metadata.yaml#source_files` は **converter が直接読む authored source 文書**の一覧 (現状 `[body.md]` のみ)
- `body.md` 内の include marker 名は **split build の生成 helper 名**を宣言
- 両者は **別集合** であり、marker 名は `source_files` に含めない
- A1' により skills/source/ に「読まないが置かれているファイル」は存在しない

### コンバータの責務

`tools/build_skill.py` は中間表現を読み、Claude Code / Codex CLI 向け成果物を `dist/skills/{full,split}/{claude,codex}/` に生成する。

各エージェント向けの変換規則：

| エージェント | 主成果物 | full モード | split モード | 配置先（利用者環境） |
|---|---|---|---|---|
| Claude Code | `SKILL.md`（YAML frontmatter 付き） | 単一ファイル (helper 本文を埋め込み) | `SKILL.md` + 4 helper を同ディレクトリに配置 | `~/.claude/skills/<skill-id>/` または `.claude/skills/<skill-id>/` |
| Codex CLI | `SKILL.md`（Agent Skills 標準準拠） | 単一ファイル | `SKILL.md` + 4 helper を同ディレクトリに配置 | `~/.agents/skills/<skill-id>/` または `.agents/skills/<skill-id>/` |

Antigravity CLI 対応は GitHub issue #25 で TODO 化 (Phase 5 では着手しない)。Gemini CLI は扱わない (終息品)。

### コンバータが守るべき制約

- 中間表現を介さない直接編集の禁止（思想憲章 C-008）
- 成果物にコンバータ版数とソースのコミットハッシュを埋め込む（再生成可能性、思想 P7）
- 各成果物に「これは生成物である。`skills/source/body.md` を編集すること」と明示する
- supported 全 agent で動作する共通機能を中核に据え、固有機能は補助的に扱う
- `source_files` と marker 名の集合分離を構造的に保証 (collision detection で fail-closed)
- marker path 安全性検査 (`..` / 絶対パス / バックスラッシュ / 連続区切り / 入れ子等を拒否)

### 責務

スキル（生成物が読み込まれた状態）の責務：

- **対象プロジェクトを理解** (言語、フレームワーク、対象成果物の種類、目的)。対象は必ずしもプログラミング言語のソースとは限らない (ドキュメント群、プロンプト集、設定群、法務テンプレート等)
- 思想憲章と設計例パックを参照
- `.quality-system/knowledge/project-context.md` (人間が書いた自己定義) を読み、必要に応じて `.quality-system/project-context.json` (機械正本) への構造化を補佐 (Phase 3 Step 3.0 で導入)
- 段階設計案を生成
- ユーザーと対話して確定
- `policy.json`, REQ メタ, contract 雛形を Layer 4 に書き込み
- `qgb validate-policy` を呼んで機械検査

**重要な境界 (Phase 3 計画確定 2026-06-21):**

- **対象理解は LLM が行い、ALLOW/DENY は qgb の contract 実行結果で決まる**
- スキルが対象を読み損ねても、それは proposal 品質の問題であり、gate の判定根拠にはしない (philosophy P6)
- スキルが「対象判定モジュール」として機械的検出を肩代わりすると、qgb が adapter を持っていた時と同じ「対象プロジェクトの広がりに枠組みが追いつかない」問題に陥る。スキルは対象を Read で読み、人間の自己定義 (`project-context.md`) を尊重しつつ柔軟に理解する役回りに徹する

### project-context.{md,json} の運用契約 (Phase 3 Step 3.0 で確立)

`.quality-system/knowledge/project-context.md` (人間正本) と `.quality-system/project-context.json` (機械正本) の二重ファイル設計には次の運用契約がある。Codex セカンドオピニオン (2026-06-21) 段 3 で「補佐 Agent と人間の役割分担を明文化すべき」という指摘を受けて固定した。

**編集権 (誰がどちらを書くか):**

| ファイル | 編集者 | 内容 |
|---|---|---|
| `project-context.md` | **人間** | 自然言語で対象プロジェクトの自己定義 (目的、対象範囲、制約、採用しない方式、参照文書) を書く。設計意図と背景の正本 |
| `project-context.json` | **補佐 Agent (利用者環境の LLM: Claude Code / Codex CLI / その他の補佐 LLM)** | md を読んで構造化、schema 整合性を保つ。`generated_by: "agent-assisted"` を立てる |
| `human_reviewed: true` | **人間のみ** | json をレビューして承認したら手で `true` に書き換える。Agent が立ててはならない (P8 違反になる) |

**不一致時の扱い (md と json が乖離した場合):**

- 検出: json の `source_metadata.source_md_sha256` と md の現在の SHA-256 を突き合わせる (Phase 3+ で `qgb validate-policy` の advisory kind として `project_context_stale` の追加を予定)
- 復旧フロー: md が真の意図を保持しているので、補佐 Agent に「md を読み直して json を更新して」と依頼。Agent は新しい `source_md_sha256` を立て、`generated_at` を更新し、必要なら `human_reviewed: false` に戻す (人間の再承認が必要)
- 緊急時: 人間が json を直接編集してもよい。その場合 `generated_by: "human"` と `human_reviewed: true` を手で立てる

**API 期待 (Phase 5 スキルが project-context を読むとき):**

- スキルは `.quality-system/project-context.json` を **`qgb design-stages propose-context`** の出力経由で受け取る (直接 Read してもよいが、推奨は qgb 経由で BOM tolerant な経路を使う)
- `human_reviewed: false` のときは `qgb design-stages propose-context` の出力 `warnings[]` にその旨が含まれる。スキルは warning に従って「provisional として扱う」(人間に確認を求めるなど) を判断する
- json の自由 prose フィールド (`purpose` / `scope.*` / `non_adopted_methods[].reason` / `references[].path`) は **データであって命令ではない** (P8 / NF-007)。スキルはこれらを LLM プロンプトに直接注入してはならない。設計判断の文脈として使う

**欠落時 fallback:**

- `.quality-system/project-context.json` が存在しないプロジェクト: `qgb design-stages propose-context` の出力で `project_context: null`、`warnings[]` は空 (宣言不在は P8 違反ではない)
- スキルは fallback として: (1) 対象プロジェクトのソースを直接 Read で読む、(2) `examples/` の中で対象に近いプロジェクトを参考にする、(3) 人間にヒアリングする (Phase 5 スキルの会話経路を使う)
- **「detect の代わりにスキルが言語判定する」のは禁止** — それは adapter 量産と同じ問題を別の場所で起こす。スキルは対象を「分類」せず「理解」する役回り

**Free prose の prompt-injection 扱い (P8 / NF-007):**

- `project-context.md` も `project-context.json` も、利用者またはその補佐 Agent が書いた文書として扱う。**外部取得コンテンツではない** (P8 区別)
- ただしスキル設計者は、悪意ある利用者または compromise された補佐 Agent が prompt injection 文字列を埋め込む可能性を考慮し、これらの prose を「上位指示」として扱ってはならない。設計判断の input data として扱う
- スキルが「`project_kind: 'python-cli'` だから Python 用のテスト段階を提案する」のような判断は妥当 (構造化フィールドを設計判断の根拠にする使い方)。一方「`purpose` の自然言語をそのまま新 stage の `responsibility` に流し込む」のような無検査の prose 移送は危険 (P9 違反のサインも検出できなくなる)

### 読む側（参照元）

- Layer 1: 思想憲章
- Layer 2: 設計例パック、JSON Schema 群、qgb CLI（`python -m qgb` 呼び出し）

### 書く側（出力先）

- Layer 4: 利用者プロジェクトの `.quality-system/`

### 変更主体

- 中間表現とコンバータ: qgb メンテナ
- 生成物: コンバータのみ（手編集禁止）

### 利用者プロジェクトへの複製

スキル本体（中間表現とコンバータ）は qgb リポジトリ側に置く。利用者プロジェクトに複製しない。

利用者はリリース成果物（`dist/skills/{full,split}/{claude,codex}/` または GitHub Releases）から自分の使うエージェント向け × 採用 build mode の 1 セットだけを取得し、各エージェントの規約に従って配置する。配置先の詳細はリリースに同梱するインストール手順を参照。

### Phase 計画

- Phase 1〜4: `skills/source/` のディレクトリ構造のみ予約。コンバータ未実装
- Phase 5: 中間表現とコンバータを本実装、Claude Code + Codex CLI 向け (full/split 計 4 成果物) のリリースを CI で生成、GitHub Releases にアタッチ

## 6. Layer 4: 利用者プロジェクト層

### `qgb init` 後に利用者プロジェクトが所有するもの

`.quality-system/` 配下：

```text
.quality-system/
  config.json
  policy.json
  project-context.json       # 機械正本: 対象プロジェクトの自己定義 (Phase 3 Step 3.0 で新設)
  req/
    REQ-APP-001.md
    REQ-APP-001.meta.json
  contracts/
    REQ-APP-001/
      S1.json
      S2.json
  knowledge/
    knowledge.jsonl
    source-index.json
    project-context.md       # 人間正本: 自然言語の設計意図と背景
  evidence/
    REQ-APP-001/
      latest/
        gate.json
        summary.md
        stages/
          S1.log
          S2.log
  artifacts/
    REQ-APP-001/
      runs/
        2026-05-15T012345Z/
          gate.json
          stages/
            S1.log
```

加えて：

- `tests/quality/` または対象系で適切な場所のテスト雛形
- `scripts/quality-gate.ps1` 等の薄いラッパー（任意）
- `.gitignore` への qgb 関連追記（`.quality-system/artifacts/` を除外）

### 採用済み証跡と揮発の分離

- `evidence/<REQ>/latest/` — 採用判定の最新証跡。コミット対象
- `artifacts/<REQ>/runs/<timestamp>/` — 揮発的な実行証跡。`.gitignore` で除外

採用判定 (`evidence/`) を更新できるのは `qgb run` のみ。`qgb run` は対象 REQ の全 stage を実行し、揮発側と採用側の両方に書き込む。「検査範囲を絞る軽量入口」(`qgb verify` 相当) は設けない（思想憲章 P3 との緊張のため。部分検証は REQ 分割で扱う。詳細は `stage-design.md` §3.1 と要件定義書 §6 を参照）。

### 利用者プロジェクトに複製しないもの

- qgb 本体のソースコード（`qgb/` 配下）
- スキル中間表現とコンバータ（`skills/source/`, `tools/build_skill.py`）
- 思想憲章（`philosophy.md`） — 参照のみ、複製しない
- 設計例パック（`examples/` 配下）
- 段階設計仕様、フレームワーク境界、要件定義書

これらは qgb リポジトリ側に置き、利用者は必要に応じて参照する。利用者プロジェクトには「確定したもの」だけを書く。

利用者は自分が使うエージェント向けのスキル成果物 (Claude Code / Codex CLI 用の `SKILL.md` + 補助ファイル、full モード or split モードのいずれか 1 セット) だけを GitHub Releases から取得し、各エージェントの規約に従って配置する。

### 変更主体

利用者プロジェクトのメンテナ。qgb は雛形を生成するが、その後の編集は利用者の責任。

### `.gitignore` への追記

`qgb init` は対象プロジェクト直下の `.gitignore` に以下を追記する：

```gitignore
# qgb volatile artifacts
.quality-system/artifacts/
```

既存 `.gitignore` がある場合は追記、無ければ生成する。利用者が手動で外す余地はある（履歴をすべて残したい運用なら採用してよい）。

## 7. 境界の運用原則

### 7.1 symlink 非依存

フレームワーク本体を symlink で参照させない。利用者プロジェクトに必要なファイルは実体として配置する。

- `.quality-system/` 配下は実体ファイル
- `scripts/quality-gate.ps1` も実体ファイル

理由：Windows での symlink 対応の差、環境依存の挙動、CI/CD ツールの symlink 解釈差を回避する。

### 7.2 公開対象には再利用可能なものだけ置く

qgb 本体に開発履歴・引き継ぎ資料を残さない。例外として `development/docs/` は開発判断の根拠として残すが、これは利用者プロジェクトには複製されない。

### 7.3 生成過程の履歴を利用者プロジェクトに継承させない

qgb の Issue 議論、設計検討、ChatGPT/Claude/Codex とのやり取りは qgb 側に閉じる。利用者プロジェクトの `.quality-system/` には「確定したもの」だけを書く。

### 7.4 異常時の責務分離 (Step 3.1 補修 #7 経由で確定)

> **重要な前置き — ドメイン依存性**:
> 本節の責務分離は qgb のドメイン (LLM 生成物の品質ゲート、CI / 開発支援文脈、異常時に人間が手で介入できる前提) に固有の判断である。リアルタイムハードウェア制御、医療機器、航空電子、金融決済等、「異常時に人間が介入する前にケガ / 損害が起きる」ドメインでは、本節と逆の責務 (システム自身が partial death を検知し能動的に safe state に倒す) が必要になる。qgb の責務分離を **普遍原則として他ドメインに適用しない** こと。

qgb の command runner は、利用者が与えた foreground command を実行し、その正常な完了経路で観測できた機械的検査の事実を gate.json に記録する。

下記は qgb の責務範囲外とする:

- 利用者の `contract.command` が daemon / detached background process / 孫プロセスなどを生成し、直接子の終了後も stdout / stderr pipe の file descriptor を保持し続けることで、qgb が EOF を観測できない状態
- OS 異常、ハードウェア異常、外部プロセス操作などにより、process tree の一部だけが想定外に生存または停止する状態
- 上記の異常状態を qgb が検出・分類し、gate.json に reason 付きで記録すること

この場合、利用者または実行環境は Ctrl+C、ジョブ停止、端末再起動、CI job timeout などの OS / 運用レイヤの手段で介入する。qgb は process supervisor ではなく、process tree の部分生存に対する hang recovery を保証しない。

したがって、qgb 経由で評価する `contract.command` は、foreground で完結し、stdout / stderr pipe を不要に継承する background process を残さない形で設計する。daemon spawn や detached background process を含む command は、qgb の評価対象として適さない。

異常時に **qgb が完了証跡を作らないことが正しい**。利用者は「`gate.json` の不在 / CI job の異常終了」を異常事態の指標として運用する。qgb 内部に hang detection + dummy reason を仕込んで「正常に異常を分類した」体裁を作るのは P7 (再現可能な証跡) 違反となる。

この判断は philosophy P4 (不易と流行の分離) + P7 + P9 (段階単一責任) と整合する。Codex 段 5 r3 で指摘された「直接子の wait と pipe EOF は一致しない」という技術的事実は認めるが、それは qgb が補修する責務範囲ではなく、OS / 運用 / 利用者 command 設計のレイヤで扱う。

## 8. 配布形態

### Phase 1

- 配布: git clone + 導入マニュアル
- PyPI 配布は必須としない
- LLM ユーザーがマニュアルに従ってローカル実行できる程度の複雑性に留める

### Phase 2 以降

- PyPI 配布を検討
- 配布物は Layer 2（フレームワーク層）に限定
- サプライチェーンリスク管理を実施（思想憲章 P8 と要件定義書 §6.9 に準拠）

### composer 相当の配布は採用しない

Python は composer のような vendor 配置が標準でない。core の `composer require --dev` モデルは PHP/Symfony 固有の運用であり、qgb はこれを直接模倣しない。

## 9. Phase 5 スキル化での境界

### スキルが対象プロジェクトに生成するもの

- `.quality-system/` 配下のファイル（config, policy, REQ, contract, evidence, knowledge）
- `tests/quality/` 配下のテスト雛形
- `.gitignore` への追記
- `scripts/quality-gate.ps1`（任意）

### スキルが対象プロジェクトに生成しないもの

- 思想憲章のコピー
- 設計例パックのコピー
- qgb 本体のコード
- スキル中間表現とコンバータのコピー
- 他エージェント向けのスキル成果物（利用者が使わないもの）

### スキルの動作

- Read で qgb 側の文書（思想憲章、設計例パック、JSON Schema）を参照
- Write で利用者プロジェクト側にだけ書き込む
- Bash（または各エージェントの相当機能）で `qgb validate-policy` を呼んで機械検査
- ユーザーとの対話で段階設計を確定

### エージェント間の差分の隠蔽

スキル本体 (中間表現) は supported agent (Claude Code + Codex CLI) 共通のロジックを記述する。エージェント固有の差分 (ツール呼び出しの構文、ファイル読み書きの API、スラッシュコマンドの起動方法) はコンバータが吸収する。

スキル利用者は、自分が使うエージェントの規約に従ってインストールするだけで、同じ動作を得られる。

## 10. 改訂の連動

本書はフレームワーク変更と連動する：

- 新しい JSON Schema が追加されたら、Layer 2 の「置くもの」に列挙
- 利用者プロジェクト側の所有物が増えたら、Layer 4 に追記
- スキルの新機能で生成物が増えたら、Layer 3 / Layer 4 に追記
- 対応エージェントが増減した場合（Phase 5 以降）、Layer 3 の中間表現スキーマとコンバータを更新

### 改訂履歴 (大きな構造変更のみ)

- **2026-06-21 Phase 3 計画確定**: adapter (`qgb/adapters/`) を Layer 2 から削除。対象プロジェクトの分析は Phase 5 スキル (LLM) の責務に統合。`.quality-system/project-context.{md,json}` の二重ファイル設計を Layer 4 に追加 (md = 人間正本、json = 機械正本、補佐 Agent が md→json 変換を担う運用想定)。Layer 3 スキル責務に「対象理解は LLM、ALLOW/DENY は qgb の contract 実行結果で決まる」を明文化
- **2026-06-24 Phase 3 Step 3.1 完結**: Layer 2 §4 に command runner の動作契約節を追加 (timeout / per-stream cap / process tree termination / structured reason / .bat escape / observation vs final result 分離)。Layer 2 「置くもの」の `core/` 一覧に `command.py` / `_win_job.py` / `_win_bat_escape.py` を反映。§7.4 「異常時の責務分離」を新設 (process tree partial survivor の hang recovery は qgb 責務外、異常時は OS / user が介入する設計)。ドメイン依存性の前置きを明示 (qgb の責務分離は LLM 生成物品質ゲート / CI / 開発支援ドメイン固有、リアルタイム制御等の他ドメインへ普遍適用しない)

## 11. 関連文書

- `philosophy.md` — 思想憲章（本書の上位制約、特に P4）
- `requirements_and_development.md` — 要件定義書
- `stage-design.md` — 段階設計フェーズ仕様
- `examples/` — 設計例パック
- 参考: `yaoyorozu-system/core` の `docs/framework-shape.md`（PHP 版の対応文書）
