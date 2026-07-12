<!--
  GENERATED FILE - DO NOT EDIT.
  これは生成物。skills/source/body.md を編集すること。
  skill_version: 0.1.7
  converter_version: 0.1.1
  build_input_digest: 817b442b8348de30
-->

## 6. 作業手順

(本セクションは full モード: SKILL.md 内の埋め込み見出し / split モード: `workflow.md` 別ファイル。)

### 6.1 初期化フロー

利用者から「qgb 入れて」「セットアップ」と依頼されたとき:

1. **利用者プロジェクトの状況確認**
   - 現在のディレクトリ (`pwd`)、git 状態 (`git status`)、既存ファイル (`ls -la`)、`README.md` の冒頭
   - 利用者プロジェクトの種類 (CLI / Web / ドキュメント等) を**自律判断せず利用者に確認**する (アダプタ的な機械検出は qgb 本体が撤回した方針、対象認識は LLM 責務)
2. **qgb の可用性確認 (Phase 5 Step 5.c-1)**
   - `python -m qgb --version` を試す。失敗する場合、まず**このプロジェクトの qgb がどの interpreter にいるか**を確定する: `.venv` があれば `.venv\Scripts\python.exe -m qgb` (POSIX: `.venv/bin/python -m qgb`) を明示的に呼び出す (セッション shell は venv を自動 activate しない)
   - それでも qgb が見つからない場合、同梱の `setup-qgb.ps1` / `setup-qgb.sh` の内容 (`.venv` 作成 + タグ固定 `git+` install) を §3.5 の姿勢 (親切なコンサルタント・メンターとして、押し付けず、内容を説明して承諾を得る) で利用者に説明し、承諾を得てから実行を提案する
3. **`python -m qgb init` を実行**
   - `.quality-system/` 配下が生成される
   - 既に存在する場合は `InitError` で停止 → 利用者に上書き可否を確認
4. **`project-context.md` (人間正本) を起草**
   - 利用者から目的 / 対象範囲 / 採用しない方式 / 参照文書を聞き取り、`.quality-system/knowledge/project-context.md` に Markdown で書く
   - 「言語判定」「フレームワーク判定」を agent が肩代わりしない (adapter 量産方針と同じ問題が再発する、Phase 3 Step 3.0 教訓)
5. **`project-context.json` (機械正本) を補佐 Agent として起草**
   - **起草前に同梱スキーマを Read する**: `python -c "import qgb, os; print(os.path.join(os.path.dirname(qgb.__file__), 'schemas'))"` で場所を確定し、`project-context.schema.json` を読む。散文の記憶で書かない (スキーマが正)
   - md の箇条書きは json では構造化される点に注意: 「採用しない方式とその理由」は `non_adopted_methods: [{"method": ..., "reason": ...}]`、「参照文書」は `references: [{"kind": ..., "path": ...}]` — **文字列配列ではない**
   - `project-context.md` を読んで `.quality-system/project-context.json` に構造化
   - `source_metadata.generated_by: "agent-assisted"` を立てる
   - `human_reviewed` は `false` のまま起草し、**利用者が内容を確認したら true 化を利用者に確認する** (立てる判断は利用者のもの。agent の無断 true 化は P8 違反。確認を経ずに false のまま進めると `propose-context` が advisory warning を出し続ける)
6. **段階設計で `policy.json#stages` を確定する** (scaffold の前提)
   - stages が空のまま次 step の scaffold を実行すると拒否される (`policy.json has no stages[]`)
   - 進め方は「段階設計プロンプト」参照 (パターン B 推奨。full: 同一 SKILL.md 内の埋め込み見出し / split: `prompts/design-stages.md`)
7. **`python -m qgb scaffold REQ-APP-001` で最初の REQ を生成**
   - 生成されるのは `req/REQ-APP-001.meta.json` + `contracts/REQ-APP-001/<stage>.json` の placeholder のみ。**REQ 本文 `req/REQ-APP-001.md` は生成されない**
   - REQ 本文 `.md` は利用者と要求内容を対話して agent が新規 Write する (人間正本)
8. **`python -m qgb validate-policy` で機械検証**
   - `config.json` / `policy.json` の存在、契約の DAG、`manual_check`-only REQ の警告
   - blocker があれば修正して再実行

9. **設計分岐の提示: 判定履歴の保存方針** (§3.5 決定の所有権の型で、初期化時に一度だけ)
   - 機構の事実を開示する: `evidence/<REQ>/latest/` は次の `qgb run` で**上書き**され、`artifacts/` は揮発 (.gitignore + prune 対象)。過去の判定 — 特に DENY だった証跡 — を残したければ、上書き前にどこかへ固定する必要がある
   - あわせて開示する: **gate.json は「どの時点のソースに対する判定か」を自己記述しない** (provenance 記録は将来検討)。evidence とソースの対応づけは運用 — 例: run 直後に evidence とソースを同一 commit に固定する — で保たれ、**qgb はその崩れを検証しない**。運用で守る場合の参考実装 (git 用スナップショット wrapper / 非 git 用 manifest) が qgb repo の `development/docs/ci-examples.md` Pattern F にある
   - 残すか・どう残すか (git commit のタイミング規約 / 別の VCS / アーカイブ / 「latest だけで十分」) は**利用者の設計判断**。git の利用を前提にしない
   - 選択した方針は §6.6 トリガ 1 (設計分岐の選択) として knowledge.jsonl に理由ごと記録する

### 6.2 REQ 設計フロー

利用者から「REQ 追加」と依頼されたとき:

1. **REQ ID の確定** (`REQ-<DOMAIN>-<NNN>` 形式、利用者と相談)
2. **`python -m qgb scaffold REQ-XXX-NNN`** でひな型生成 (前提: `policy.json#stages` が確定済み — 空だと拒否される)
   - 生成物は `.meta.json` + 段階別 contract の placeholder のみ (REQ 本文 `.md` は次 step で agent が新規 Write)
3. **REQ 本文の起草** (`req/REQ-XXX-NNN.md`)
   - 何を達成したいか (acceptance criteria)
   - どの段階で検証するか (`responsibility` の方針)
   - 関連する既存 REQ / contract への参照
4. **段階別 contract の設計** (`contracts/REQ-XXX-NNN/<stage>.json`)
   - 各段階で実行する機械検査 (verification_type: command / file_exists / substring_match / json_schema)
   - **`command` の場合は必ず §6.5「command authoring protocol」を適用**する (任意の文字列を書けるが、runtime 規律を組み込まないと環境依存で動かない / 文字化けする / 利用者プロジェクトで運用上問題が起きる)
   - LLM レビューは `manual_check` 段階に分離、ALLOW 判定の根拠にしない (P6)
   - 設計分岐で判断が発生したら §6.6 の記録トリガに従い knowledge.jsonl に理由を残す
   - 検査の弁別力の確認 (校正) は §6.8 を適用する。red-first で進める場合は §6.9
5. **`python -m qgb validate-policy REQ-XXX-NNN`** で機械検証
6. **`python -m qgb check REQ-XXX-NNN`** でリハーサル実行
   - `artifacts/REQ-XXX-NNN/checks/<ts>/` に揮発出力
   - curated evidence は更新しない
7. **問題なければ `python -m qgb run REQ-XXX-NNN --yes`** で本実行 (非対話環境 = agent 経由では `--yes` が必須。対話 TTY では省略すると確認プロンプトが出る)
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
4. **修正後 `qgb check` でリハーサル**、問題なければ `qgb run --yes`

### 6.4 構造化編集フロー

「contract を編集」「JSON Patch」と依頼されたとき:

1. **直接ファイル編集は避ける** (Phase 2 で確立した規律)
   - 線引き: **scaffold 直後の placeholder (`TODO-...`) を実値に初めて充填する行為は §6.2 step 4 の「contract の設計」であり、直接 Write してよい**。一度実値が入った contract 以降の変更が本フロー (patch 経由) の対象
2. **JSON Patch で構造化編集** (`python -m qgb patch <target> <patch.json>`)
   - op: add / replace / remove / test (移動 / 複製は WONTFIX)
   - atomic swap で書き込み (途中状態が残らない)
   - **patch は対象ファイル単体でなくプロジェクト全体の整合を preflight する**: 無関係に見える小さな patch でも、未充填 contract 等の blocker (`missing_contract_field` など) が残っていると弾かれる。先に `qgb validate-policy` で blocker を解消してから patch する
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
   - argv[0] (実行ファイルの path) は **OS ネイティブの path 区切り**で書く (例: Windows では `.venv\Scripts\python.exe`)。Windows の CreateProcess は `/` 区切りの相対 path を実行ファイルとして解決しない
5. **runtime-specific preflight (= ι capability-based dispatch)**
   - 確定 runtime に対応する checklist を**段階設計プロンプト §5.5「capability-based dispatch checklist」** (full: 同一 SKILL.md 内の埋め込み見出し / split: `prompts/design-stages.md`) から読み込んで適用
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

#### 他 runtime の規律 (概要、詳細は段階設計プロンプト §5.5 capability-based dispatch checklist 参照)

- **bash (POSIX)**: shebang + executable bit + `LC_ALL=C.UTF-8` 設定 + 改行 LF
- **Python**: `python -X utf8` または `PYTHONUTF8=1` + `sys.stdout.reconfigure(encoding='utf-8')` + 改行 LF + 必要なら `# -*- coding: utf-8 -*-` (Python 2 系で書く場合のみ、Python 3 系では不要)
- **Node**: `--input-type=module` (ESM 明示) + `process.stdout.write` で UTF-8 確認 + locale 環境変数
- **Go binary / 他 compiled**: build artifact の path + argv 完全明示、stdout encoding は binary 側の責任

これらの詳細は段階設計プロンプト §5.5 (full: 同一 SKILL.md 内 / split: `prompts/design-stages.md`) に runtime ごとに展開。

#### lint helper script (skill 同梱)

`skills/source/lint/check-command-contract.ps1` (Windows native PowerShell) と `skills/source/lint/check-command-contract.py` (cross-platform Python) を skill 同梱で提供。command contract を Write した直後に skill が以下を機械検査:

1. PowerShell 5 対象かつ非 ASCII `.ps1` なのに BOM がない
2. `.ps1` を `shell=False` の argv で直接起動しようとしている
3. stdout encoding の初期化または実行確認がない
4. command が存在しない runtime を指定している
5. `qgb check` の log に `U+FFFD` がある

dist build 時に converter が `dist/skills/{full,split}/<agent>/lint/` 配下に copy。

### 6.6 記録の規律: knowledge.jsonl は利用者プロジェクトの journal

gate.json が「**何が通ったか**」を残す (P7) のに対し、knowledge.jsonl は「**なぜそう決めたか**」を残す。評価系 (段階構成・contract・waiver) は設計物であり (P12)、その設計判断の理由は機械証跡には写らない。knowledge.jsonl はその置き場 — 次にこのプロジェクトを触る人間・agent への引き継ぎ資料である。

**記録トリガ (このどれかが起きたら 1 エントリ):**

1. **設計分岐の選択**: 段階構成・検査方式・被覆範囲で複数案から選んだとき、採らなかった案と理由ごと記録する (例: 「表記ゆれ検査は禁止リスト照合方式。LLM 評価機 (P12 経路) は規模に比して過剰なので不採用」)
2. **実地トラブルと回避**: 環境固有の問題を踏んで回避したとき (例: argv[0] の path 区切り、encoding 問題)。同じ穴に二度落ちないための恒久化
3. **外部情報の取り込み**: §3.4 の P8 既存規律 (source-index.json とセット)
4. **waiver**: `qgb add-waiver` が自動記録する (追加作業不要)

**比例原則:** 記録するのは判断が発生したときだけ。ルーチン作業 (scaffold、通常の check / run、機械的な修正) にエントリは不要。官僚的記録を強いるための仕組みではない — 「3 ヶ月後にこのプロジェクトを触る者 (人間でも agent でも) がこの判断の理由を必要とするか」で判定する。

記入は `python -m qgb add-knowledge <file>` 経由 (§6.4 参照、直接編集しない)。**エントリ起草前に同梱 `knowledge.schema.json` を Read する** (§6.1 step 5 の要領。必須 field は `id` / `kind` / `title` / `source_type` / `created_at`)。entry 形式の例はレビュー観点プロンプト §5 を参照 (full: 同一 SKILL.md 内の埋め込み見出し / split: `prompts/review-policy.md`)。

### 6.7 サブエージェント委任の規律

サブエージェントは本スキルを読んでいない。委任した瞬間に規律が消えるのを防ぐため、委任 prompt に以下の**最小規律セット**を明示的に含める:

1. **現在の承認状態**: 例「段階案は adopt 済み / project-context は human_reviewed=true 済み」。承認待ちが残っているなら「〜は人間承認待ち — 依存する作業に着手しない」と明記する (§3.5 の判定テスト参照)
2. **禁止操作**: `.quality-system/` 配下の直接編集禁止。`qgb check` / `run` / git commit 等のゲート操作・証跡確定の主体を分離する場合は「あなたはやらない (メインが実施する)」と書く。read-only レビューの委任では「編集禁止」を明示する
3. **実行経路**: qgb の呼び方 (プロジェクト venv の python を明示) など、確定済みの環境事項
4. **成果物の位置づけ**: 「あなたの成果物は候補であり、採用判定は機械ゲートと人間の承認が行う」(P5/P6)

規律は委任のたびに繰り返す (子は前回の委任を覚えていない)。この最小セットは委任 prompt の冒頭に置くのがよい。

### 6.8 検証系の校正: ALL GREEN は検査が機能している証明ではない

検査が「機能している」とは**落とすべきものを落とせる**こと (弁別力) であり、緑が並ぶことではない。一度も失敗を観測していない検査は、常に緑を返す壊れ方 (exit 0 固定 / 対象 glob の空振り / pattern の書き間違い) をしていても検出できない。これは自作 command checker に限らず、**利用者が構成したすべての検査インスタンス**に当てはまる — 組み込み verification_type でも `substring_match` の pattern 間違いは常緑になる (免除されるのは qgb 本体がテスト済みの runner 実装だけで、その上に載る設定は免除されない)。

憲章上の位置づけは評価機の「校正」(P12)。特に成果物と checker を同一 agent が書く運用では利害が同一になるため、校正の証跡が対抗策になる。

**やり方 (強い順):**

1. **恒久メタテスト**: 検査ごとに「既知のダメ入力を食わせたら落ちる」テストを 1 本、通常のテストスイートに置く — 毎 run 再校正され、checker 側の退行も捕まえる
2. **一度の観測記録**: ダメ入力で DENY することを一度確認し、knowledge.jsonl に記録 (§6.6 トリガ 2 相当、artifacts の該当 check を参照で残す)
3. **受容**: 小規模・低リスクなら校正なしの受容も正当な選択

どこまでやるかは**利用者の設計判断** (§3.5 決定の所有権の型で選択肢と負荷を提示して選んでもらう)。選択は §6.6 トリガ 1 として理由ごと記録する。

### 6.9 TDD mode: red-first で進めたい場合 (F-016)

qgb には「実装前に gate を立て、DENY を期待された状態として証跡化する」TDD mode がある。骨子:

1. REQ + contract を**実装より先に**確定し、`python -m qgb run REQ-XXX-NNN --yes --phase red` を実行する。DENY になるが、gate.json は `phase: "red"` + 失敗が実装前の期待状態である旨の meaning で記録される — 「この検査は未実装を正しく落とす」という §6.8 の弁別力確認を兼ねた証跡になる
2. 実装が進んで検査が通ったら `--phase green` で ALLOW への初回転換を記録する
3. 以後の通常運用は `--phase verify` (既定)。`--phase` は red / green / refactor / verify の 4 値で、DENY の意味づけが変わるのは red のみ (green / refactor / verify での DENY は通常の失敗)。red での ALLOW は「落ちるはずの検査が通った」という疑義 (§6.8 と同種) として meaning に記録される

**注意: `phase=red` は DENY の意味づけを変えるだけで、終了コードを成功に反転しない** — CI や後続処理の上では失敗のままであり、red 段階を自動化する場合は DENY を明示的に期待して扱う。red-first で進めるかどうかは進め方の選択であって必須ではない。使わない場合の弁別力確認は §6.8 で担保する。

