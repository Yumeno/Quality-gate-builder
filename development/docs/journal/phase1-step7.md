# Phase 1 Step 7 — TDD phase=red + command runner + manual_check + waived/knowledge.jsonl 作業記録

着手: 2026-05-31
完結: 2026-05-31 (本体 1 コミット + Codex 横断レビュー指摘 9 件のうち中以上 6 件を本体に吸収)

## Step 7 のスコープ

detailed-design.md §12 + 受け入れ条件 §12-14/15/16:

- **A**: TDD phase=red の expected-failure 本実装 (受け入れ条件 14)
- **B**: command verification_type 実装 (Phase 1 必須 verification_type の追加)
- **C**: manual_check を含む REQ → NOT_READY (受け入れ条件 15)
- **D**: waived 段階 + knowledge.jsonl + KNOWLEDGE-* basis (受け入れ条件 16)

Codex 計画レビューで採用した順序: A → C → D → B。decision/preflight の意味論を先に固め、command runner の実行リスクを最後に閉じる。

## 着手前: Codex 計画レビュー

Step 6 と同じく 8 観点で相談。Codex の最優先指摘:

1. **phase=red の exit code は DENY=1 維持**: gate status と CLI exit を乖離させない。`expected failure` は decision.meaning で表現。
2. **項目順 A → C → D → B**: command runner は subprocess リスクが大きいので最後に独立レビュー。
3. **waived は preflight / runner / decision / basis / knowledge.jsonl の 5 層すべてで同じ意味にする** — Step 7 のレビュー観点で最重要。
4. **command 出力は 64 KiB tail-truncate**: 失敗 traceback が末尾に出る前提。
5. **json_schema は Step 8 送り**: Step 7 は十分大きい。
6. **`qgb add-waiver` CLI は Phase 2 送り**: 受け入れ条件 16 は CLI を要求していない (手編集で OK)。

## 実装の流れ

### 項目 A: TDD phase=red の expected-failure 本実装

`qgb/core/decision.py`:

- `_MEANING_BY_PHASE` を F-016 表通りに書き直し
- phase=red + DENY: "The required test fails as expected before implementation."
- phase=red + ALLOW: "Unexpected pass: phase=red expected the new test to fail..."
- phase=verify + DENY: "Defined checks did not pass. This is not a failure but a signal to revise."
- phase=green/refactor: 実装/refactor の中立な文言
- exit code は status と一致 (CI 自動化との分離原則)

テスト 8 件。

### 項目 C: manual_check を含む REQ → NOT_READY

Step 6a の preflight `check_runtime_support(mode="run")` が manual_check_required を blocker として既に返していた → 受け入れ条件 15 は既達。Step 7 では独立テスト 5 件で挙動をロックして退行を防ぐ。

`validate-policy` 側は warning のまま (Step 6a の severity 分岐維持)。

### 項目 D: waived 段階 + knowledge.jsonl + KNOWLEDGE-* basis (5 層整合)

Codex 計画レビュー最重要原則「5 層整合」を維持するため、preflight / runner / decision / basis / knowledge.jsonl すべてに変更を入れる:

1. **preflight (`AdoptedStage`)**: `waived: bool` / `waiver_reason: str` を追加。`resolve_adopted_stages` で REQ meta から読み取って伝える。
2. **preflight (`check_runtime_support`)**: waived stage は manual_check / unsupported guard を素通させる (実行されないので blocker にする意味がない)。
3. **runner (`run_stages`)**: waived stage は実行前に `result="waived"` で短絡。depends_on 評価より前に挿入することで、waived stage に依存する stage は満たされた前提として扱える。
4. **decision (`decide`)**: waived stage は judgement から除外。all-waived は DENY (ALLOW を出さない P1/P5 維持) だが、`failed_stage=""` で「stage の失敗ではなく judgement material 不在」を表現。
5. **evidence (`build_basis`)**: 各 waived stage に `KNOWLEDGE-WAIVER-<REQ>-<stage>` を追加。
6. **evidence (`_record_waiver_knowledge`)**: knowledge.jsonl に WAIVER エントリを追記。idempotent (既存 id は skip)。

`gate.schema.json` も Step 7 で更新:
- `stages[].result` enum に `"waived"` 追加
- ALLOW 制約: `items: passed|waived` + `contains: passed` (all-waived ALLOW は禁止)
- DENY 制約: `oneOf` で「通常 DENY (failed_stage 非空 + 少なくとも 1 つ failed)」と「all-waived DENY (failed_stage 空 + 全 stage waived)」を分離

テスト 7 件 (ALLOW 経路、basis、knowledge.jsonl、idempotency、log、all-waived、schema 違反)。

### 項目 B: command verification_type 実装

`qgb/core/runner.py`:

```python
_SUPPORTED_RUNTIME_TYPES = frozenset({"file_exists", "substring_match", "command"})
_COMMAND_STREAM_CAP_BYTES = 64 * 1024
_COMMAND_DEFAULT_TIMEOUT_SECONDS = 60


def _run_command(project_root, stage):
    # argv shape check
    # working_dir is resolved under project_root (R1 guard)
    # subprocess.run(shell=False, env=os.environ.copy(), stdin=DEVNULL,
    #                capture_output=True, text=True, timeout=..., check=False)
    # _tail_truncate stdout/stderr to 64 KiB
    # FileNotFoundError / PermissionError / TimeoutExpired → failed
```

Phase 1 out-of-scope は docstring に明記 (Codex 計画 + 横断レビュー両方):
- Interactive / TTY
- Stdin payloads
- Process tree kill / signal handling
- Network isolation, container sandbox
- Environment allowlist, secret masking
- Shell syntax, glob expansion
- Windows .bat/.cmd argument escaping
- 64 KiB cap は **log cap であり実メモリ cap ではない** (Codex 横断レビュー指摘 1)

テスト 13 件 (zero/nonzero exit, expected nonzero, shell metachar literal, working_dir resolution + R1 escape, timeout, stdout/stderr capture, log cap, command not found, command が runtime supported, argv 空)。

### Codex 横断レビューと補修

本体実装後、Codex に 6 観点でレビューを依頼。指摘 9 件:

| # | 重要度 | 内容 | 対応 |
|---|---|---|---|
| 1 | 高 | 64 KiB cap は log cap であり実メモリ cap でない | **docstring 明記** (Phase 2 で Popen incremental) |
| 2 | 高 | TimeoutExpired.stdout/stderr が bytes になり得る | テスト追加 (Python 3.13 の text=True 経路では str を返すことを確認) |
| 3 | 高 | 非 UTF-8 stdout で UnicodeDecodeError | テスト追加 (subprocess.run の text=True + replace で耐性確認) |
| 4 | 高 | knowledge.jsonl 末尾 partial に append → 新規 waiver 破壊 | append 前に末尾 byte 確認、newline 補完 |
| 5 | 中 | all-waived DENY の failed_stage が waived stage を指す | `failed_stage=""` にする + schema を oneOf に緩和 |
| 6 | 中 | waived dependency の伝播 | runner で waived 短絡を depends_on 評価より前にしたことで satisfied 扱いになることを担保 (テスト追加) |
| 7 | 中 | contract type validation (timeout_seconds など) | 既存挙動 (schema 拒否 + runner argv 拒否) で network、テスト追加 |
| 8 | Phase 2 | Windows .bat/.cmd argument escaping | docstring 明記 |
| 9 | Phase 2 | timeout が process tree を止めない | docstring 明記 |

補修テスト 7 件追加 (全て 1〜7 をカバー)。

Phase 1 致命寄りは 1/2/3/4 で、いずれも本体コミット内で吸収。docstring 4 件 (1/8/9) と挙動 4 件 (2/3/4/5/6/7) の組み合わせ。

## コミット履歴 (Step 7)

```
ace1c0e Step 7: TDD phase=red + command runner + manual_check NOT_READY + waived/knowledge.jsonl
```

## テストと品質指標の推移

| 段階 | テスト件数 | ruff |
|---|---|---|
| Step 6 完結時 | 366 | clean |
| 項目 A (phase=red) | 374 | clean |
| 項目 C (manual_check NOT_READY) | 379 | clean |
| 項目 D (waived/knowledge) | 386 | clean |
| 項目 B (command runner) | 399 | clean |
| 補修 (Codex 7 件) | **406** | clean |

## 振り返り

### 1. 計画レビューが Step 7 でも構造変更を着手前に吸収した

Codex 計画相談で「項目順 A → C → D → B」と「waived は 5 層整合」を着手前に確定したことで、本体実装中に構造的迷いがなくなった。特に **waived の 5 層整合** は、後から「basis に追加し忘れた」「runner で短絡し忘れた」を発生させずに済んだ。これは Codex が「観点」として明示してくれたから。

### 2. 横断レビューで「Phase 1 致命的」を高頻度で拾った

Step 7 の Codex 横断レビュー指摘 9 件のうち 4 件 (1/2/3/4) は「致命的に近い」レベル (memory リーク / 例外漏れ / データ破壊)。Step 6 までの指摘より重症度が高い。これは Step 7 が subprocess.run / 副作用ファイル (knowledge.jsonl) を扱うため、抽象的な責務分割の議論より「実行時の失敗モード」が支配的になったため。

「Phase 1 MVP として致命的な漏れ」を Codex に明示的に問うことで、設計議論ではなくバグ拾いの観点で機能した。

### 3. waived の意味論を 5 層に揃えるために decision の補修が要った

当初の decision 実装は all-waived のとき `failed_stage = adopted[0].stage_id` にしていた。これは「DENY のとき failed_stage は必ず非空」という gate.schema.json の旧制約を満たすための便宜的措置だったが、Codex が「waived stage が DENY の理由のように見える」と指摘。

修正方針: `failed_stage = ""` にして「stage の失敗ではなく judgement material 不在」を表現し、schema 側も `oneOf` で all-waived DENY を別ケースとして定義。これにより 5 層整合が完全に揃った。

### 4. knowledge.jsonl の末尾 newline 補完は append-only の典型的落とし穴

`open("a")` は末尾改行の有無を見ずに直接追記するので、partial line がある状態で append すると新規行が partial line と連結される。これは Codex の補修 4 で指摘されるまで気付かなかった。

教訓: **append-only ファイル形式 (JSONL / NDJSON など) の書き込みは、末尾 byte の確認を含めて 1 つの操作として扱う**。Phase 2 で他の append-only ファイル (gate アーカイブなど) を扱うときも同じパターン。

### 5. command runner は Phase 1 の「実行系の本丸」

これまでの Phase 1 実装は基本的にファイル I/O と JSON 操作で済んでいたが、command runner は OS プロセスを起動する。subprocess の細部 (shell=False の Windows 挙動、text=True の decode、timeout の grandchildren、メモリ cap) は Codex の知識に強く依存した。

Phase 2 で `Popen` incremental に書き換える余地は明確に残っているが、Phase 1 では `subprocess.run` 1 行で済むメリット (見通し、デバッグ性、テスト容易性) を選んだ。docstring に「ここは log cap であり実メモリ cap ではない」と書いておくことで、Phase 2 で本格化する人が躓かずに進められる。

### 6. Step 7 で Phase 1 受け入れ条件 14/15/16 達成

Step 6 完結時点で 14/24 件達成 → Step 7 で 14/15/16 を追加して **17/24 件達成**。残 7 件:

| # | 条件 | 状態 |
|---|---|---|
| 17 | Project Knowledge Base にユーザー明示情報を保存 | Step 9 予定 |
| 18 | 外部由来情報に requires_human_review 付与 | Step 9 予定 (schema は既にある) |
| 19 | 設計例パック 3 例が動作 | Step 8 予定 |
| 20 | 導入マニュアルが存在 | Step 9 予定 |
| 21 | 依存ライブラリ採用方針 + セキュリティ確認手順 | Step 9 予定 |
| 23 | 思想憲章 / 段階設計 / フレームワーク境界の 3 文書並列維持 | 達成済み (Step 7 で確認) |
| 24 | skills/source/ 構造 + Phase 5 エージェント中立スキル要件 | Step 9 予定 |

23 は実は既達なので、実質残 6 件。Step 8 で 19 を、Step 9 で 17/18/20/21/24 を消化予定。

## Step 7 で確立した API (Step 8/9 入力)

- `AdoptedStage.waived` / `waiver_reason` (preflight)
- `StageResult.result == "waived"` (runner)
- `KNOWLEDGE-WAIVER-<REQ>-<stage>` (basis convention)
- `knowledge.jsonl` の WAIVER エントリ schema (knowledge.schema.json で既に確定)
- gate.schema.json: all-waived DENY ブランチ
- command verification_type の runner 実装 (Phase 1 fully runnable な verification_type は file_exists / substring_match / command の 3 種)

## 次のステップ (Step 8)

- 設計例パック 2 例追加: python-cli-pytest + markdown-docs (受け入れ条件 19)
- json_schema verification_type の本実装 (Phase 1 内で必要に応じて)
- 既存 examples/generic-minimal との並立性確認 (各 example に対する run / validate / validate-policy が通る最小 fixture を用意)
