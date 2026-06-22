# Phase 3 Step 3.1 着手前判断: command runner 強化 + CI 雛形

着手前判断確定: 2026-06-22

## 経緯

Phase 3 Step 3.0 完結 (`46d892a`, 2026-06-21) により detect 廃止 + project-context 二重ファイル設計が確立し、Phase 5 スキル提供の「機械責務側の前提条件」のうち **対象認識の責務分掌** が片付いた。本 Step 3.1 では残り 2 つの前提条件のうち **command 実行の機械的信頼性** を整える:

1. ✅ Step 3.0: 対象認識のライン引き (LLM / 機械 / 補佐 Agent 三層)
2. **Step 3.1 (本書)**: command 実行の機械的信頼性 (process tree kill / 出力 cap / .bat/.cmd escaping / CI 機械化)
3. ⏳ Step 3.2: 依存解決固定 (lock/hash、supply-chain 信頼)

仕様の出典は `development/docs/detailed-design.md` §14.2 (Step 3.1 サブステップ計画) と `development/docs/requirements_and_development.md` §13 Phase 3 サブステップ。本 prejournal はその仕様を本体実装の手前で **判断確定** する。

## 本 Step の理念的位置づけ

Step 3.0 の prejournal で 2 回ライン引きを誤った教訓 (「対象 = プログラミング言語のソース」と暗黙仮定する、「機械責務 = 確定的 / LLM 責務 = 揺らぎ」と二分しがち) は本 Step にも適用される。本 Step では下記 3 つを再点検する:

### 1. なぜ command runner を強化するのか (qgb の P6 を qgb 自身に適用)

contract.json の `verification_type=command` は **利用者プロジェクトの quality gate の最終的な機械検査** になりうる。たとえば「pytest が exit 0 で終わったから ALLOW」「lint が exit 0 で終わったから ALLOW」の判定 (`basis[]` の CONTRACT id) を生成する。

このとき、command runner が下記いずれかを **誤って報告** すると ALLOW の信頼性が崩れる:

- 子孫プロセス (孫プロセス以下) が走り続けても親プロセスが exit 0 で帰ってきたので passed と判定 → P6 違反 (機械検査の客観性が崩れる)
- 巨大出力で qgb プロセス自身が OOM kill → P7 違反 (再現可能な証跡が残らない、kill された事実すら gate.json に書かれない)
- `.bat` で argv が誤解釈され「passed と報告したが実は別コマンドが実行されていた」 → P6 / P7 両方違反

つまり Step 3.1 は **「qgb が自分自身の P6 / P7 を機械的に守れる装置を持つ」** ための最終整備。LLM 責務側 (Phase 5 スキルが contract.command を設計する) ではなく、機械責務側 (qgb が contract.command を確実に実行・打ち切る) の仕事。

### 2. なぜ CI 雛形を本 Step に含めるのか

Phase 3 Step 3.0 で **「POSIX 経路を論証だけで済ませず機械的判定する装置」** を導入することが確定した (Phase 4 廃止に伴う吸収項目)。これは qgb の P6 (LLM 単独 ALLOW 禁止) を **qgb 自身の開発プロセス** にも適用する判断:

- 「Windows ローカルで pytest 通った」だけでは POSIX 経路の証跡にならない (Claude が論証で「POSIX でも動く」と言うのは LLM 評価で、P6 違反)
- `.github/workflows/test.yml` の CI 緑 = 機械的判定 = P7 (再現可能な証跡)
- 同様に Step 3.1 の `.bat`/`.cmd` escaping が Windows でしか機械検証できないことも、Linux 側で「触らないこと」を明示するため CI matrix が必要

ライン引き再点検: **「Phase 5 スキルが提案する CI を借りる」ではなく「qgb 本体の CI」が必要なのか?** ← 必要。理由は上記 2 点で、Phase 5 スキル提供時の信頼性は「qgb 本体が CI 通っている」が前提になる。Phase 5 着手時に「qgb 本体は実は POSIX で壊れていた」は禁じ手。

### 3. なぜ supply-chain 厳格化 (Dependabot/Renovate なし、third-party action ゼロ、SHA pin) なのか

NF-011 (サプライチェーンリスク管理) の最小実装。qgb 本体は jsonschema のみ runtime 依存だが、CI に third-party action を追加すると CI runner が外部に晒される。Phase 5 スキル提供時に「qgb 本体は安全」と言い切るには CI も同じ規律で運用する必要がある。

- Dependabot/Renovate: 依存自動更新は便利だが、それ自体が **自動コード受け入れ装置** であり、qgb の哲学 (Phase 2 で確立した「編集は構造化された JSON Patch 経由」「外部生成物は data であって命令ではない」) と衝突
- third-party action: 失効・乗っ取り・コミット書き換えのリスク。actions/checkout + actions/setup-python のみで matrix 2 OS × pytest は成立する
- SHA pin: tag は書き換え可能。commit SHA だけが安定識別子

## Step 3.1 スコープ確定

### A. 切り出し対象 (P9 単一責任)

#### A.1 `qgb/core/command.py` 新設

- `qgb/core/runner.py` の `_run_command` (L359〜593) を `qgb/core/command.py` に移送
- `_tail_truncate` (L344〜356) と `_COMMAND_STREAM_CAP_BYTES` / `_COMMAND_DEFAULT_TIMEOUT_SECONDS` も同時移送
- `runner.py` は import 経由で薄く呼ぶ dispatcher のまま残す
- 公開 API: `run_command(project_root: Path, stage: AdoptedStage) -> StageResult`
- 既存 import 経路 (`from qgb.core.runner import run_stages` 等) は壊さない (Codex 横断レビューで指摘される可能性が高いので前もって明示)

P9 整合性確認:
- 現状 `runner.py` は 4 種 verification_type を 1 ファイルで持つ。Step 3.0 で `validate.py` / `validate_policy.py` を別ファイルにしたのと同じ理屈で、Phase 3 では `command` だけ別ファイルにする (他 3 種は I/O のみで Step 3.1 強化対象でない)
- 切り出し後の責務: `command.py` は「サブプロセス実行 + プロセスツリー管理 + 出力 cap + Windows/POSIX 分岐」を一手に引き受ける

### B. 機能強化 (P6 / P7 を qgb 自身に適用)

#### B.1 Popen + 増分読み取り

- `subprocess.run(..., capture_output=True)` から `subprocess.Popen(..., stdout=PIPE, stderr=PIPE)` に切替
- バックグラウンドスレッド 2 本で stdout/stderr を増分読み取り (1 本だと deadlock 可能性)
- 各ストリーム **16 MiB 上限** で打ち切り → そこでプロセスツリー kill 発火 (RSS cap は依然 WONTFIX、これは「実行 cap」)
- log 表示は従来通り 64 KiB tail のみ (実行 cap と表示 cap を分離)
- timeout は Popen 側で経過時間監視 → 超過したらツリー kill

#### B.2 Process tree kill (Windows: Job Objects)

ctypes 経由で Windows API を直接呼ぶ:

```
CreateJobObjectW(NULL, NULL)
SetInformationJobObject(job, JobObjectExtendedLimitInformation,
    {LimitFlags: JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE})
AssignProcessToJobObject(job, process_handle)
TerminateJobObject(job, exit_code)
```

- `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` で「job handle が閉じたら全プロセス kill」を保証 → qgb プロセスが落ちても孤児プロセスが残らない
- `TerminateJobObject` で能動的 kill (timeout / 16 MiB 上限到達時)
- **失敗時 fallback**: CreateJobObject / AssignProcessToJobObject が失敗したら、Popen の `process.terminate()` を呼んで子プロセスだけ kill + 「孫プロセスが leak した可能性あり」を log_text と gate.json.stages[].log に記録 (P7 の証跡優先、隠さず明示)

CreateProcess の `CREATE_BREAKAWAY_FROM_JOB` flag は **使わない**: 利用者のコマンドが意図的に job 外に出る挙動を許すと kill が機能しない。利用者の `.bat` / `.cmd` が job をエスケープしようとしたら子孫 leak で記録される。

#### B.3 Process tree kill (POSIX: setsid + killpg)

```
preexec_fn = os.setsid  (Popen 引数)  → 子プロセスが新規 session leader + process group leader になる
kill 時: os.killpg(child.pid, signal.SIGTERM) → 猶予 (3 秒) → os.killpg(child.pid, signal.SIGKILL)
```

- `setsid` で子プロセスが新規 process group を持つので `killpg` で「子孫全部」kill
- SIGTERM → SIGKILL の 2 段は POSIX 慣習 (graceful shutdown を 3 秒待つ)
- Python 3.12 で `subprocess.Popen(..., process_group=0)` がより portable な代替として導入されているが、qgb は `requires-python = ">=3.10"` (pyproject.toml L10) で 3.10 を最小サポートとしており、`process_group=0` は使えない → `preexec_fn=os.setsid` を採用

`preexec_fn` の fork 後 thread safety 問題は qgb 本体が thread を立てていないため実害なし (Popen 自身が増分読み取りスレッドを立てるのは fork **後** であり、子プロセス側の fork 時点では single-threaded)。

#### B.4 stream 16 MiB cap

- stdout / stderr **個別に** 16 MiB cap (合算ではない、片方が暴走しても他方の cap を圧迫しない)
- 16 MiB に達したら即時 process tree kill 発火 → stage は failed (理由: "output stream exceeded 16 MiB limit")
- 打ち切った時点で 64 KiB tail を log_text に記録 (証跡)

`_tail_truncate` (現 64 KiB) はそのまま流用、cap 定数を **2 つ** に分離:
- `_COMMAND_EXECUTION_CAP_BYTES = 16 * 1024 * 1024` (実行 cap、Popen 側で監視)
- `_COMMAND_LOG_TAIL_CAP_BYTES = 64 * 1024` (表示 cap、log_text 用、現 `_COMMAND_STREAM_CAP_BYTES` を rename)

#### B.5 .bat / .cmd argument escaping

argv[0] が `.bat` / `.cmd` の場合のみ適用 (それ以外は現状 `shell=False` のままで安全):

##### B.5.a `cmd.exe` メタ文字 escaper

```python
def _escape_cmd_metacharacters(arg: str) -> str:
    # cmd.exe メタ文字: & | < > ^ % " ( )
    # %VAR% 展開を抑止するため % を ^ でエスケープ
    # 詳細: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw
```

##### B.5.b C++ argv parsing (CommandLineToArgvW 互換) escaper

```python
def _escape_argv_for_msvcrt(arg: str) -> str:
    # MSVCRT の CommandLineToArgvW 規則 (バックスラッシュ + ダブルクォート の特殊扱い)
    # https://learn.microsoft.com/en-us/cpp/cpp/main-function-command-line-args#parsing-c-command-line-arguments
```

**両者を別関数で実装する理由** (Codex 計画レビュー指摘):
- `.bat` / `.cmd` 経由では `cmd.exe` が **まず** argv を C++ argv parsing で分解し、**そのあと** メタ文字解釈する → 2 段階のエスケープが順序つきで必要
- Python の `subprocess.list2cmdline` は MSVCRT 規則だけで cmd.exe メタ文字を考慮しない (これが現 `_run_command` の盲点、Codex 8 指摘)

argv[0] の判定: `Path(argv[0]).suffix.lower() in (".bat", ".cmd")` で判定。argv[0] が `cmd.exe` で argv[1] が `.bat` パターンは **本 Step ではスコープ外** (利用者が明示的に cmd.exe を呼ぶケース、現実的でないため Step 3.3 or 利用者責務)。

##### B.5.c 実 temporary `.bat`/`.cmd` fixture でテスト (Codex 指摘)

論証だけで済まさず、`tests/test_command_runner.py` (新設) に下記 fixture テストを入れる:
- `echo_args.bat` (引数を echo するだけ) を temporary directory に作成
- argv に `["a & b", "c | d", "%PATH%", '"quoted"']` を渡し、echo 結果が **生の文字列のまま返る** ことを assert
- escaping が漏れているとメタ文字解釈で別コマンドが実行されたり %PATH% が展開されたりするので、検出可能

Windows でのみ実行 (POSIX では `.bat` 経路が無効なので `pytest.mark.skipif`)。

### C. CI 雛形

#### C.1 `.github/workflows/test.yml`

```yaml
name: test
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, ubuntu-latest]
        python-version: ["3.10", "3.12"]   # 最小要件 + 上限の 2 つだけ matrix (中間 3.11 は P11 整合: ALLOW は OS × version の組み合わせで意味、全網羅は不要)
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@<SHA pin>
      - uses: actions/setup-python@<SHA pin>
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e .[dev]
      - run: pytest -x
```

確定事項:
- third-party action **ゼロ** (上記 actions/* は GitHub 公式)
- secrets 不使用 (この CI は読み取り専用)
- Dependabot/Renovate なし (.github/dependabot.yml を **作らない**)
- python-version は pyproject.toml の最小要件と同じ 1 つだけ (matrix を膨らませない)
- `fail-fast: false` で Windows / Ubuntu のどちらが落ちたか必ず両方の結果を残す

#### C.2 SHA pin の方針

- actions/checkout, actions/setup-python の最新リリースタグ → そのコミット SHA を調べて pin
- README にも書くが、変更時は **手動で SHA を更新** (自動更新装置を入れない)
- SHA 更新の commit は単独で行い、変更理由 (CVE / 機能追加 / 任意更新) を commit message に書く

#### C.3 失敗時のフォールバック設計

CI が落ちたとき、Step 3.1 の何が失敗しているか早期に切り分けるため、pytest 出力に下記を期待:
- Windows でしか動かないテスト (`.bat` fixture) は Ubuntu で skip と表示される
- POSIX でしか動かないテスト (`os.setsid` 経路) は Windows で skip と表示される
- skip 理由は `pytest.mark.skipif(reason="...")` で明示

### D. テスト追加

#### D.1 `tests/test_command_runner.py` (新設)

- 既存 `_run_command` のテストは `tests/test_runner.py` 等に散在 → grep で網羅性確認、必要なら本ファイルに集約
- 新規追加:
  - `.bat`/`.cmd` argument escaping fixture (B.5.c)
  - 16 MiB stream cap 発火テスト (`python -c "print('x' * 17 * 1024 * 1024)"` で stdout 16 MiB 超え → ツリー kill 発火 → failed)
  - process tree kill テスト: 親が exit したあと孫プロセスが残らないこと (POSIX: pgrep / Windows: tasklist で確認、ただし fragility が高いので慎重に)
  - timeout テスト (現状あるはず、再確認)

#### D.2 既存テストの維持

- `_run_command` の import 元が変わるので、`from qgb.core.runner import _run_command` を直接 import しているテストがあれば修正 (grep 確認)
- 想定: 既存 731 件 + 上記新規 = 745〜755 件、全 green

### E. spec / docs 更新

- `development/docs/detailed-design.md` §14.2 Step 3.1 に **完結記録** を追記 (本 prejournal で確定した内容と実装結果の差分を明示)
- `development/docs/requirements_and_development.md` §13 Phase 3 にも完結記録
- `development/docs/framework-shape.md` §5 (Step 3.0 で新設) に command runner の動作契約を追記:
  - 「子孫プロセスは Job Object / setsid 経由で kill 保証する」
  - 「stream 16 MiB 超過は failed (DENY ではなく failed) として扱う」
  - 「.bat/.cmd は escaping 経由でのみ argv を受け取る」
- `CLAUDE.md` 更新: 「command runner 強化」を Phase 3 進捗欄に追記
- `README.md` の Phase 計画記述更新 (CI バッジ追加検討)

## 規模見積

- 本体実装 (A.1 + B.1〜B.5 + C.1〜C.3 + D.1〜D.2 + E): 1.5〜2.0 (Step 5 = 1.0 基準、detailed-design.md §14.2 記載値と整合)
- Codex 横断レビュー 1 周追加: +0.2〜0.3 (Step 3.0 の経験から)
- 5 観点並列レビューで指摘が出る可能性: +0.3〜0.5
- 想定上限: 2.5 程度

## サブステップ分割 (context 効率の観点)

Step 3.0 の教訓 (「作業量増えたから Step 分けない、ただし context 長効率のためにサブステップ分割は可」) を踏襲:

- **Step 3.1a**: `core/command.py` 切り出し (B.1 一旦保留、現 `subprocess.run` のまま移送) + 既存テスト維持
- **Step 3.1b**: Popen + process tree kill (B.1 + B.2 + B.3) + 関連テスト
- **Step 3.1c**: stream 16 MiB cap (B.4) + 関連テスト
- **Step 3.1d**: .bat/.cmd escaping (B.5) + fixture テスト
- **Step 3.1e**: CI 雛形 (C.1〜C.3) + SHA pin + 動作確認
- **Step 3.1f**: 5 観点レビュー + Codex 横断 + 補修ループ + spec/docs 更新 + 完結

サブステップ間の commit cycle はそれぞれ独立。Step 番号は **3.1 のまま** で本体実装の論理単位だけが a〜f に分かれる。

## レビュー方針

`review-process` memory に従い 4 段:

- 段 1: 観点別 5 subagent 並列 (correctness / P9 / philosophy / NF-004 / spec-drift)
- 段 2: 集約・調停 (Claude)
- 段 3: Codex 横断レビュー (`/ask-codex-with-context`)
- 段 4: 人間 (最終判断)
- 収束ループ: K=2 回連続新規 finding ゼロまで

レンズ調整 (Step 3.1 固有):

- **correctness**: ctypes 呼び出しの正しさ (Job Objects API 呼び出し順、struct レイアウト)、escaping の境界ケース (空文字、長大文字列、surrogate pair)
- **P9**: command.py の責務が広がりすぎていないか (Job Object 管理 + escaping + cap + dispatch を 1 ファイルに集約してよいか / さらに分割すべきか)
- **philosophy**: 16 MiB 超過を「failed」と扱うのは P5 (ALLOW の意味限定) と整合か (DENY ではなく failed = stage 内部の機械検査エラー、判定としては DENY と同じ「ALLOW でない」を出す)
- **NF-004**: Windows ctypes 経路の動作確認、SHA pin で Windows runner が安定供給される確証
- **spec-drift**: detailed-design.md §14.2 の文言と実装の整合

## Codex 相談点 (本 Step 着手前)

下記 4 点は Codex セカンドオピニオンで検証する価値あり:

1. **出力 cap 単位**: stdout/stderr 各 16 MiB 個別 cap で妥当か、合算 16 MiB の方が望ましいケースがあるか
2. **Job Object 失敗時 fallback**: 「孫プロセス leak を log に明示するだけ」で十分か、より厳しい挙動 (raise / NOT_READY) が必要か
3. **CI matrix の最小性**: python-version 1 つだけで Phase 5 提供時に十分か (Phase 5 でユーザーが 3.10/3.11/3.12 を使う可能性、pyproject.toml の `python_requires` で固定する案)
4. **SHA pin の更新サイクル明文化**: README or SECURITY.md に「いつ・誰が・どう pin 更新するか」のオペレーション規約を書くべきか

これらは prejournal commit の **後** で Codex に渡し、本体実装着手前に方針確定する (Step 3.0 prejournal でも同じ流れ)。

## Claude のバイアス再点検

Step 3.0 で発見した「Claude が機械責務側に過剰に責務を寄せがち」「LLM 責務を狭めがち」のバイアスは本 Step に **直接は出にくい** (本 Step はそもそも機械責務側の話)。ただし下記 2 点は警戒する:

- 「CI を充実させれば Phase 5 スキルが信頼される」と思い込みすぎない: CI は機械的判定の 1 装置で、スキル品質の代替にはならない (Phase 5 では別のレビュー装置が必要)
- 「.bat / .cmd の escaping を完璧にすれば command runner は信頼できる」と過信しない: escaping の境界ケースは無限にあり、本 Step では「主要メタ文字 + C++ argv parsing」までで止める。「.bat の任意の挙動を全て覆う」は目標にしない (Phase 5 スキルが contract.command を設計するときに `.bat` を避けるよう誘導する選択肢もある)

## 完了条件

- `qgb/core/command.py` が新設され、`_run_command` 関連が完全に移送されている
- Popen + process tree kill (Windows: Job Object、POSIX: setsid) が動作する
- stream 16 MiB cap が機能し、超過時にツリー kill 発火
- `.bat`/`.cmd` argument escaping が cmd.exe メタ文字 + C++ argv parsing の両方に対応
- 実 `.bat`/`.cmd` fixture テストが Windows で green
- `.github/workflows/test.yml` が Windows + Ubuntu matrix で green
- POSIX 経路 (`os.setsid` + `killpg`) が Ubuntu CI で実証
- ruff clean
- 既存 731 件 + 新規テスト全 green
- spec / docs (detailed-design.md / requirements_and_development.md / framework-shape.md / CLAUDE.md / README.md) 更新
- 5 観点並列レビュー + Codex 横断レビュー で K=2 回連続新規 finding ゼロ

## Step 3.2 への申し送り

- 依存解決固定 (pip-compile --generate-hashes) は本 Step 完結後に着手
- 本 Step の CI 雛形に lock/hash チェックを追加する形になる (CI ファイル 2 度更新)
- 当初 Phase 4 の「依存 audit / SBOM」を Step 3.2 で吸収する判断は確定済

## Phase 5 への申し送り (Step 3.1 由来)

- Phase 5 スキルが contract.command を設計するとき、本 Step で確立した「機械責務側の保証」を前提にしてよい:
  - 子孫プロセスは Job Object / setsid 経由で kill 保証される (孤児プロセスを心配しなくてよい)
  - 16 MiB を超える出力は機械的に failed になる (巨大出力で qgb 自身が OOM する心配は不要)
  - `.bat`/`.cmd` 経由も escaping される (ただしスキルが `.bat`/`.cmd` を勧めるかは別判断)
- 一方、本 Step の範囲外:
  - メモリ cap (RSS 監視) は依然 WONTFIX → Phase 5 スキルが利用者に「contract.command は短時間で完了するものに限る」と明示する設計
  - 並列実行 (複数 stage の concurrent run) は引き続き未対応 → Phase 5 スキルが順次実行前提で設計
