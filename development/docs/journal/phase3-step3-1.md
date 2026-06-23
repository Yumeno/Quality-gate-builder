# Phase 3 Step 3.1 完結ジャーナル: command runner 強化 + CI 雛形

完結日: 2026-06-24
着手前判断: `phase3-step3-1-prejournal.md` (v1 commit `849b7f5` / v2 Codex セカンドオピニオン反映 `a129ebf`)

## Step 3.1 で確立した境界 (恒久記録)

### 機械責務として担保したもの

- `qgb/core/command.py` を P9 単一責任モジュールとして切り出し、command runner の全責務を集約
- **timeout**: `contract.timeout_seconds` (default 60s) 超過で process tree kill + `reason="command_timeout"`
- **per-stream execution cap**: stdout / stderr それぞれ 16 MiB cap (合算でなく個別)、`reason="stdout_cap_exceeded"` または `"stderr_cap_exceeded"`
- **process tree termination**:
  - POSIX: `preexec_fn=os.setsid` + `killpg(SIGTERM)` → grace 3s → `killpg(SIGKILL)`
  - Windows: `qgb/core/_win_job.py` の `WindowsJob` (ctypes 経由)、`spawn_suspended_and_resume` で transactional cleanup、`KILL_ON_JOB_CLOSE` で defense-in-depth
- **structured reason**: `stages[].reason` enum 3 種 + `stages[].runner_warning` (kill 経路 degradation の構造化フィールド)、`gate.json` / `gate.runtime.json` 両 schema に optional フィールド追加 (pre-3.1c gate.json 読込互換)
- **.bat / .cmd argument escaping**: `qgb/core/_win_bat_escape.py`、cmd.exe メタ文字 (`& | < > ( ) % ^`) + MSVCRT argv parsing の二段エスケープを **argv[0] (script path) を含む全 item に均一適用**
- **observation vs final result の分離**: supervisor loop は早期離脱契機を観測、最終結果は reader thread 完了後に `cap > timeout > natural exit` の優先順で確定 (`_CapExceededState` の Lock 保護 `snapshot` を最終判定の単一情報源とする)
- **`.github/workflows/test.yml`**: Windows + Ubuntu × Python 3.10 + 3.12 matrix、SHA pin、`persist-credentials: false`、`timeout-minutes: 20`、third-party action ゼロ、`SECURITY.md` で SHA pin 更新ルール明文化

### qgb の責務範囲外として整理したもの

- 利用者 `contract.command` が daemon / detached background process / 孫プロセスを生成し、直接子の終了後も stdout/stderr pipe の fd を保持し続けることで qgb が EOF を観測できない状態
- OS / ハード異常で process tree の一部だけが想定外に生存または停止する状態
- 上記異常を qgb が検出・分類し gate.json に reason 付きで記録すること

異常時は user が Ctrl+C / 端末再起動 / CI job timeout 等の OS / 運用レイヤで介入する。「gate.json の不在 / CI job の異常終了」自体が異常事態の指標。

**この責務分離は qgb のドメイン (LLM 生成物品質ゲート / CI / 開発支援、異常時に人間が手で介入できる前提) 固有であり、リアルタイムハードウェア制御 / 医療機器 / 航空電子 / 金融決済等、人間介入前に損害が出るドメインには普遍適用しない**。詳細は `framework-shape.md` §7.4。

## Step 3.1 のサブステップ構成

prejournal v2 でサブステップ 3.1a〜3.1e に分割した。3.1b は更に b-1/b-2/b-3 に細分化 (Codex 段 0 r2 推奨で「Popen 切替 / POSIX killpg / Windows Job Object を独立 commit に」と分けた)。

| サブステップ | commit | 内容 |
|---|---|---|
| 3.1a | `23f2cbf` | `qgb/core/command.py` 切り出し (subprocess.run のまま移送) |
| 3.1b-1 | `6e7c3d0` | subprocess.run → Popen + reader thread 2 本 + bytearray sink |
| 3.1b-2 | `3b5f01c` | POSIX killpg 経路、token + heartbeat 方式の test fixture |
| 3.1b-3 | `c134095` | Windows Job Object (ctypes 経由)、CREATE_SUSPENDED → assign → resume |
| 3.1c | `3ea31bd` | per-stream 16 MiB cap、`reason` enum、gate schema 拡張 |
| 3.1d | `8682ff5` | `.bat` 二段エスケープ + path-with-spaces 対応 |
| 3.1e | `1c04bc2` | `.github/workflows/test.yml` + `SECURITY.md` |
| 3.1e 補修 | `bee9cea`, `222fd1e` | `importlib.resources.abc` を 3.10/3.11 互換に、`TestRecursionGuard` を 3.10/3.12 互換に |

## 段 1〜5 のレビュープロセス (Codex セカンドオピニオン 6 周)

| 段 | 周 | 内容 | finding |
|---|---|---|---|
| 0 | r1 | prejournal v1 計画レビュー | 5 件指摘、prejournal v2 に反映 |
| 0 | r2 | prejournal v2 確認 | 承認、補修方針確定 |
| 1 | — | 観点別 5 並列レビュー (correctness / P9 / philosophy / NF-004 / spec-drift) | 48 件、段 2 で Claude 集約 |
| 3 | r1 | 横断レビュー (集約結果) | cross-cutting 5 軸、A/B/C 群 triage 承認 |
| 3 | r2 | 「症状対処より入らない設計」転換後の方針再レビュー | 承認 + `CapExceededState` 統合の追加指摘 |
| 5 | r1 | 補修 #1〜#5 後の K=2 第 1 周 | 新規 finding 1 件 (cap-vs-exit race) → 補修 #6 |
| 5 | r2 | 補修 #6 後の K=2 第 2 周 | 新規 finding 1 件 (reader.join timeout=5 が race を完全に閉じない) → 補修 #7 (メタレビュー経由) |
| 5 | r3 | 補修 #7 後の K=2 第 3 周 | 新規 finding 1 件 (孫プロセス継承で永久ブロックの物理経路) → user 介入で「責務範囲外」整理 |
| 5 | r4 | 「責務範囲外」判定の妥当性確認 | 承認、`framework-shape.md` §7.4 で明文化方針確定 |

段 5 r5 (Task 22 spec 反映後の最終確認) を本ジャーナル commit 後に実施 → 新規 finding ゼロなら K=2 達成。

## 補修 7 件 (「ステート不在化」の系統)

| 補修 | commit | 解消した finding | 設計 |
|---|---|---|---|
| #1 | `0d3e52d` | C-P0-2 (UnboundLocalError 余地), C-P0-3 (timed_out false-positive) | supervisor loop を `poll → cap → deadline` の 3 状態直交分割 |
| #2 + #3 | `8d5921a` | C-P0-1 (suspended 漏れ), 9-P0-1 (docstring 境界違反), NF-P2-1 (dead branch), C/NF-P1 (GetLastError), C-P1-3, C-P1-5 | `WindowsJob.spawn_suspended_and_resume` で transactional cleanup + Job Object hardening (`use_last_error=True`, function binding, `_close_handle` finally) |
| #4 | `ed8660e` | NF-P1-2 (argv[0] unquoted) | `build_command_line` の `argv[0]` も `escape_argv_for_msvcrt` を通す均一ポリシー、path-with-spaces 対応 |
| #5 | `1146ce4` | C-P1-1 (cap state race) | `_CapExceededState` クラスで 2 変数の race-prone 分離を統合 (Lock 保護) |
| #6 | `9e86344` | Codex 段 5 r1 (cap-vs-exit race) | 観測契機 ≠ 最終結果の設計分離、cap > timeout > natural exit 優先順 |
| #7 | `1dea387` | Codex 段 5 r2 (reader.join timeout race) | OS + stdlib 契約信頼、reader.join timeout 撤廃 |

すべて「症状対処」ではなく「**ステート空間そのものを不在化する**」アプローチで実装。

## 作業プロセス記録 (timeline)

| 時刻 (相対) | 出来事 |
|---|---|
| 段 0 r1 | prejournal v1 commit (`849b7f5`)、Codex r1 で 5 指摘 |
| 段 0 r2 | prejournal v2 commit (`a129ebf`)、Codex r2 で承認 |
| 3.1a | command.py 切り出し、既存テスト 700 件全 PASS |
| 3.1b-1 | bufsize=-1 / read1 で incremental I/O 確立、最初の試行 (`bufsize=0` + `read1`) で `_io.FileIO.read1` 不在に遭遇、stdlib 仕様を確認して修正 |
| 3.1b-2 | POSIX killpg + token + heartbeat fixture (Codex 推奨方式)。Windows test は xfail で残してフレームワークだけ整備 |
| 3.1b-3 | Windows Job Object 実装、xfail → 正式 PASS 昇格。`_handle_thread` がない CPython バージョンに気付き Toolhelp32Snapshot 経由の fallback を追加 (後の補修 #2 で dead branch と判明し削除) |
| 3.1c | per-stream cap、reason enum、gate schema 拡張 |
| 3.1d | quote 単独では injection 防げないことを実機検証で発見、quote + carat 両層が必要と判明、`subprocess.list2cmdline` バイパスで Popen に str command line を直接渡す戦略採用 |
| 3.1e | CI 雛形 + SECURITY.md。初回 push で **CI failure** → `importlib.resources.abc` が 3.10/3.11 で不在を CI が機械検出 (`bee9cea`)。再 push でも 1 件 failure → `TestRecursionGuard` の 500 段 nest が 3.10 json.encoder で RecursionError (`222fd1e`)。**Step 3.1e 本旨「qgb の P6 を qgb 自身に適用 = CI 緑 = 機械的判定」が早速 2 度機能した実例** |
| 段 1 | 5 並列レビュー 48 件、段 2 で Claude 集約 |
| 段 3 r1 | Codex 横断、cross-cutting 5 軸 |
| user 介入 1 | 「症状対処より入らない設計のほうが大事」嗅覚 → 方針転換 |
| 段 3 r2 | 転換方針を Codex 承認、`CapExceededState` 統合の追加指摘 |
| 補修 #1〜#5 | 4 commit + #5 で K=2 第 1 周用意 |
| 段 5 r1 | finding 1 件 (cap-vs-exit race) → 補修 #6 |
| 段 5 r2 | finding 1 件 (reader.join timeout race) → 補修 #7 候補化 |
| user 介入 2 | 「フォールバック警戒過剰じゃないか」→ Claude メタレビュー (Agent 2 並列) で「Codex 案の形をなぞる反射」を点検 |
| 補修 #7 | timeout 撤廃、commit message を「Codex 指摘修正」でなく「補修 #5/#6 の入らない設計の貫徹 + Phase 5 few-shot 価値」軸で記述 |
| 段 5 r3 | finding 1 件 (孫プロセス継承で永久ブロック) → user 介入 3 で「責務範囲外」整理 |
| user 介入 3 | 「qgb の責務じゃない！って分離するなら、それすら不要では」「異常時は user が Ctrl+C で介入で十分」 |
| user 介入 4 | 「リアルタイム制御のドメインもある、ケースバイケース」→ 責務分離はドメイン依存と前置きを追加 |
| 段 5 r4 | 「責務範囲外」判定の妥当性 Codex 承認、`framework-shape.md` §7.4 文言確定 |
| Task 22 | spec 更新 (detailed-design / requirements / framework-shape / CLAUDE / README / journal) + memory 更新 |

## ユーザー判断の重要転換点

### 転換点 1: 「症状対処より入らない設計のほうが大事」(補修方針)

段 3 r1 で Codex が「補修 4 commit 案」を提示、Claude はその形をなぞる方向に倒れかけたところで user 介入。
- 「`process.poll()` を先に追加する」(症状対処) でなく「`poll → cap → deadline` の 3 状態直交分割でステート空間を消す」(不在化) に転換
- 「resume 失敗で kill する」(症状対処) でなく「`WindowsJob.spawn_suspended_and_resume` で suspended 漏れステートを構造的に不在化」(不在化) に転換
- 「stream race を Lock で保護」(症状対処) でなく「`_CapExceededState` で 2 変数の race-prone 分離を 1 オブジェクトに統合」(不在化) に転換

### 転換点 2: 「フォールバック警戒過剰じゃないか」(補修 #7)

段 5 r2 で Codex が「reader.join(timeout=5) を `timeout なし` or `timeout + internal_error reason`」の 2 案を提示。Claude は両案を user に提示する反射に倒れたところで user 介入。
- Claude メタレビュー (Agent 2 並列) を発動 → 「Codex 案の形をなぞる反射」を点検
- 「timeout 撤廃 (Codex 案 1)」を **「Codex 指摘修正」でなく「補修 #5/#6 の入らない設計の貫徹 + Phase 5 few-shot 価値 + magic number 排除」を主理由とする独立判断** として採用
- commit message も主理由を変更

### 転換点 3: 「qgb の責務じゃない！」(段 5 r3 = 異常時の責務分離)

段 5 r3 で Codex が「孫プロセス継承で永久ブロックの物理経路あり」を指摘、Claude は「補修 #8 で natural exit 経路でも `_terminate_process` を呼ぶ + reader_hang reason 追加」案に倒れたところで user 介入。
- 「qgb の責務じゃない！って分離するなら、ハード不良で一部プロセスだけ死ぬケースもそれを気にするのが qgb の責務じゃない、timeout=3 すら不要」
- 「異常動作時に user が Ctrl+C / 端末再起動で強制終了して、なにか問題がある?」
- **責務範囲外** として整理、framework-shape.md §7.4 で明文化する方針に転換

### 転換点 4: 「ケースバイケースの判断」(ドメイン依存性)

「責務範囲外」整理を進める段で user 介入。
- 「OS に任せていたら人がケガをするリアルタイム制御の世界もある」
- 「今回の責務分離は普遍原則ではない、ケースバイケース」
- **ドメイン依存性** を前置きとして framework-shape.md §7.4 / requirements §9.2 / CLAUDE.md Platform expectations に明示。Phase 5 で他ドメイン (リアルタイム / 医療 / 航空 / 金融) に qgb 流を普遍適用しないよう注意喚起

## Phase 5 への申し送り (技術と方法論を分離)

### subprocess 技術 (command runner 設計の few-shot)

- **foreground command 前提**: 利用者 `contract.command` は foreground で完結する設計、daemon spawn は qgb 評価対象外
- **observation vs final result の分離**: supervisor は早期離脱契機を観測、最終結果は reader 完了後に優先順で確定
- **ステート不在化**: 中間ステートを Lock + 1 オブジェクトで構造的に消す (`_CapExceededState`)
- **transactional spawn**: Windows でも POSIX でも、子プロセス起動 → kill+wait のラップを context manager で
- **均一 escape ポリシー**: argv の head/tail で扱いを変えない (`build_command_line` の argv[0] 含む全 item 均一)
- **不易の契約に倒す**: `Popen.wait → pipe close → read1 EOF` のような OS + stdlib 契約を信頼する設計、`reader.join` は timeout なし
- **異常時の責務分離**: qgb は process tree partial survivor の hang recovery を保証しない、user が OS 介入する設計 (**ドメイン依存**、リアルタイム制御等には適用不可)

### review 方法論 (Codex セカンドオピニオン消化の few-shot)

- **finding の 3 分類**: `code fix` / `spec fix` / `out of scope by philosophy`
- **「指摘されたら即補修」反射の警戒**: 段 5 r2 で発動した user 介入 (転換点 2) で点検したパターン
- **「Codex 案の形をなぞる反射」の警戒**: Claude メタレビュー (Agent 2 並列) で発動可能、転換点 2 で実践
- **philosophy で責務点検**: 「qgb の責務範囲内か」を P4 (不易と流行) / P7 (再現可能な証跡) / P9 (段階単一責任) で問う
- **ドメイン依存性の自覚**: qgb の責務分離は LLM 生成物品質ゲート / CI / 開発支援固有、他ドメインに普遍適用しない
- **K=2 収束基準の解釈**: 「コード補修も spec 補修も解決手段」なら、その判断が文書 / memory に反映された周から K=2 をカウント
- **メタレビューの活用**: Codex が複数案を提示した時に user に丸投げせず、Agent 並列で「Codex 案の形をなぞる反射」と「あるべき設計」を独立評価する手段がある

両方の教訓は subprocess 制御 (技術) と review 姿勢 (組織知) の 2 層であり、混ぜると Phase 5 で読む側が読み違える。**分離して記録**。

## 規模実績の振り返り

- prejournal v2 見積もり: 1.5〜2.0 (Step 5 = 1.0 基準)
- 実績: prejournal 計画 + サブステップ実装 + 補修 7 件 + spec 更新 で **約 3.5〜4.0**
- 上振れ理由: 5 観点並列レビューで 48 finding が出たこと + ステート不在化への補修方針転換 + 責務範囲整理 (段 5 r3 経由)
- ただし「上振れ」は **ステート不在化と責務範囲整理の知見** を得た投資であり、Phase 5 提供時の信頼性と few-shot 教材価値で十分回収できる判断

## 次の Step 申し送り

- **Step 3.2 (依存解決固定)**: pip-tools 等で `requirements.txt` の hash pin 化、CI で resolved deps を artifact として残す。当初 Phase 4 「依存 audit / SBOM」をここで吸収。本 Step で確立した SHA pin / SECURITY.md / CI matrix の運用と一貫させる
- **Phase 5 (Skill Creator 化) 着手前提**: Step 3.2 完結後に揃う
- **Step 3.3 (Phase 2 繰越実需回収、任意)**: Phase 5 で必要が判明したものに限定、先回りで全部はやらない

## 関連ファイル

- `phase3-step3-1-prejournal.md` (着手前判断、v1 + v2 Codex 反映)
- `qgb/core/command.py` / `qgb/core/_win_job.py` / `qgb/core/_win_bat_escape.py` (本 Step で確立した実装)
- `tests/test_command_process_kill.py` / `tests/test_command_bat_escape.py` (token + heartbeat / path-with-spaces / cap / atomicity 等の回帰防止テスト)
- `.github/workflows/test.yml` / `SECURITY.md` (CI 雛形 + SHA pin 更新規約)
- `development/docs/framework-shape.md` §4 (Layer 2 command runner 動作契約) / §7.4 (異常時の責務分離、ドメイン依存性前置き)
- `development/docs/detailed-design.md` §14.2 (Step 3.1 完結記録) / §15 改訂履歴 0.28
- `development/docs/requirements_and_development.md` §9.2 (コマンド実行制御) / §13 (Phase 3 進捗)
- `CLAUDE.md` (Platform expectations / Phase 5 skill perspective)
- `README.md` (CI badge / Phase 進捗)

memory に「review-process」の finding 分類追加と「`subprocess-runner-domain-scope`」等の新規 memory 候補。`Task 22-G` 参照。
