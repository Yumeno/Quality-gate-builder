# 作業記録: Phase 1 Step 5 (本体 + 補修 4 段)

期間: 2026-05-21〜2026-05-23 (Step 3〜4 記録の続き)

## 目的

Step 5 (`qgb run` 縦串実装) と、それに続く **4 段の補修** の経緯を時系列で残す。Step 3〜4 記録 (`phase1-step3-to-step4.md`) の続編。

Step 5 は Phase 1 MVP の縦串完成にあたり、扱う面が広い (5 モジュール + schema + テスト + サンプル + ドキュメント)。Codex レビューも 3 回かかり、補修コミットは合計 4 本になった。本記録の目的は次の 3 つ:

1. なぜ Step 5 で **本体 1 + 補修 4 = 計 5 コミット** という構成になったかの判断経緯を残す
2. Codex レビューを「丸呑み」せず「思想憲章で取捨選択」する規律が今期どう機能したかを残す
3. 「Step 6 申し送り」と「Step 5 系で完結すべき課題」の **線引き判断** がユーザー指摘で軌道修正された経緯を残す (本期最大の学び)

## 全体の流れ

```
Step 5 本体     qgb run 縦串実装                       commit 7bef1b3 (173 件)
   ↓ Codex 一次レビュー
Step 5 補修     R1 path escape / R2 同秒 / R3 optional commit 6e51f47 (178 件)
   ↓ Codex 二次レビュー
Step 5 二次補修 RR1 atomic / MR2 abs path / MR3 const  commit 8864913 (184 件)
   ↓ Codex 三次レビュー
Step 5 三次補修 run_id 導入 / preflight 5 分割 / M1    commit eb5f2fb (196 件)
   ↓ Codex 三次レビュー結果から `r0000` 残課題発覚
Step 5 四次補修 r0000 reject / run_dir suffix pattern  commit a42b1b0 (204 件)
                                                      → Step 5 完結
```

各補修コミットは「Codex 指摘の重大度分類 → 思想憲章で取捨選択 → 実装 → 詳細設計反映」という同じパターンで進めた。

## Step 5 本体: qgb run 縦串実装 (commit `7bef1b3`)

### 実装内容

policy.json と REQ メタ、contract を読んで採用段階を順次実行し、ALLOW/DENY を決定して採用側 (`evidence/<REQ>/latest/`) と揮発側 (`artifacts/<REQ>/runs/<ts>/`) の両方に gate.json + summary.md + stages/*.log を書き出すまでを実装。`examples/generic-minimal/` で ALLOW が出る状態に到達。

責務分割 (P9 を実装側に降ろした 5 モジュール):

- `qgb/core/loader.py`    — policy/req-meta/contract/config の I/O のみ
- `qgb/core/preflight.py` — READY/NOT_READY 判定。validate + 必須正本 + DAG + stage_id 解決 + contract_ref 解決 + verification_type 一致 + manual_check required 段階拒否 + Phase 1 runnable type のみ許可
- `qgb/core/runner.py`    — file_exists / substring_match を実行し StageResult を返す。depends_on 失敗時はスキップ (failed 記録) で gate.schema の DENY 制約を自然に満たす
- `qgb/core/decision.py`  — ALLOW/DENY + failed_stage (最初の failed required) + phase 別の decision.meaning テンプレート
- `qgb/core/evidence.py`  — 単一 datetime から compact / RFC3339 を生成、basis[] を REQ + POLICY + CONTRACT 順で組み立て、採用/揮発両系統に byte-for-byte 等価の gate.json を書き出し、QGB_KEEP_RUNS (default 10) で揮発側を prune

### TDD discipline

- まず `tests/test_run_generic_minimal.py` 17 件を書く (受入テスト)
- その後 loader → preflight → runner → decision → evidence → cli の順で実装

### 自前で見つけたバグ

QGB_KEEP_RUNS テスト失敗 — 同一秒内に 4 回 `main([...])` を呼ぶと `paths.run_dir` のディレクトリ名が同じ timestamp になり 1 個に潰れる。テスト側の前提が雑だったので `monkeypatch.setattr(evidence_mod, "make_timestamps", ...)` で固定 datetime を 1 秒ずつずらして注入する形に変更。

**この時点では「テスト側の問題」と片付けた。後の Codex 二次レビューで「これはプロダクト側の同秒衝突問題も同時に出ていた」と指摘される (RR1)。**

### 手動 smoke で in-repo example の手書き reference を上書き

動作確認で `python -m qgb run REQ-APP-001 --path examples/generic-minimal` を実行したところ、Step 4 で手書きした「リファレンス出力」である `examples/generic-minimal/.quality-system/evidence/REQ-APP-001/latest/gate.json` が新しい timestamp で上書きされた。`git restore` で復旧したが、構造的問題として認識。**この時点では Step 5 補修で扱うことを決断**。

## Step 5 補修: Codex 一次レビュー反映 (commit `6e51f47`)

### Codex 一次レビュー (重大 3 + 中 5 + 軽微 4)

| 区分 | # | 指摘 | 本コミットでの対応 |
|---|---|---|---|
| 重大 | R1 | contract.target で project root escape 可能 (NF-007) | 対応 (loader.resolve_project_relative を共通化) |
| 重大 | R2 | 同秒衝突で run_dir 上書き (P7) | 対応 (1 秒ずつ進めた synthetic timestamp で吸収) |
| 重大 | R3 | optional stage と ALLOW schema 矛盾 (P5) | 対応 (Phase 1 は全 adopted を判定対象) |
| 中 | M1 | REQ meta 実行順がトポロジカル順か未検証 | **Step 6 に申し送り** |
| 中 | M2 | PreflightReport.ready() が単純すぎ (severity 必要) | **Step 6 に申し送り** |
| 中 | M3 | preflight 早期 return 判定が validate-policy 再利用で情報不足 | **Step 6 に申し送り** |
| 中 | M4 | _replace_dir_contents() が非 atomic | **Step 6 に申し送り** |
| 中 | M5 | unlink 失敗を握りつぶす | **Step 6 に申し送り** |
| 軽微 | L1〜L4 | コメント / byte offset / loader error 分類 / QGB_KEEP_RUNS warning | **Step 6 に申し送り** |
| 運用 | — | in-repo example 上書き問題 | 対応 (`evidence-reference/` に退避) |

### 運用問題: reference 退避

`examples/generic-minimal/.quality-system/evidence/...` と `evidence-reference/...` に分離。`.quality-system/evidence/` は **qgb run の destination 専用**、`evidence-reference/` は **手書きリファレンス専用** とした。これで in-repo で直接 `python -m qgb run --path examples/generic-minimal` を叩いても、コミット済みのリファレンスは上書きされない。

Codex 一次レビューでは選択肢 (a)-(d) を提示した。(a) reference を移動、(b) --dry-run、(c) CI ガード、(d) 別パス退避。最終的に **(d) + (c)** を採用。

### Codex 指摘の取捨選択

R1/R2/R3 は即時補修 (重大)、M1-M5 / L1-L4 は Step 6 申し送り、と分類。**この時点では「次の Step に持っていける」という判断だった**。

## Step 5 二次補修: Codex 二次レビュー反映 (commit `8864913`)

### Codex 二次レビュー (重大 1 + 中 2 + 軽微 1)

| 区分 | # | 指摘 | 本コミットでの対応 |
|---|---|---|---|
| 重大 | RR1 | run_dir 予約が check-then-create で並行 race | 対応 (mkdir(exist_ok=False) で atomic 化) |
| 重大寄り | RR2 | 1 秒前進 synthetic timestamp は実時刻を歪める | **Step 6 に申し送り** (timestamp と run_id の責務分離) |
| 中 | MR1 | 60 秒衝突 fallback の microsecond suffix が curated schema を破る | **Step 6 に申し送り** (上と同時対応) |
| 中 | MR2 | resolve_project_relative() 絶対パスが docstring と実装で不一致 | 対応 (Path(ref).is_absolute() で先に拒否) |
| 中 | MR3 | required=false を schema で受け入れて decision で無視 | 対応 (req-meta.schema.json で const: true 固定) |
| 軽微 | — | symlink escape テスト不足 | 対応 (os.symlink → pytest.skip 構造) |

### この時点での Step 6 申し送りリストの肥大化

二次補修コミット後の `detailed-design.md §12` には次が積まれていた:

- preflight モジュール再分割
- PreflightIssue.severity 導入
- timestamp と run_id の責務分離 (schema 改訂を伴う)
- REQ meta トポロジカル順検証
- _replace_dir_contents() の atomic 化
- byte offset 表記
- LoaderError 分類
- QGB_KEEP_RUNS warning

**ここで気付くべきだったが気付かなかった**: 上記のうち「timestamp と run_id の責務分離」「REQ meta トポロジカル順検証」は本来 **Step 5 の証跡意味論** の話で、設計フェーズ系コマンドの構築 (Step 6 本来スコープ) ではない。

## Step 5 三次補修: ユーザー指摘 → Codex 三次相談 → スコープ整理 (commit `eb5f2fb`)

### ユーザーからのスコープ指摘

二次補修コミットの直後、Step 5 系の補修 + Step 6 への申し送りで進めるつもりだったところ、ユーザーから:

> 「Step6送りにされているもののうち、『設計フェーズ系コマンドの構築』というスコープから逸脱しているものはないですか」

この問いを受けて Step 6 申し送りリストを精査し、次の分類を立てた:

- **A**: 本来 Step 6 (detect / design-stages / scaffold / validate-policy / verify / `--yes`)
- **B**: Step 6 で便乗していて本質は Step 5 系構造改善 (preflight 再分割、severity)
- **C**: Step 6 に置いているが本質的に Step 5 系積み残し (run_id、トポロジカル順)

その上で、B/C をどう扱うべきか Codex に再相談した。

### Codex 三次相談 (B/C のスコープ判定)

選択肢 (P1)〜(P4) のうち Claude は **P4 (中間案: C 全部 + B シグネチャだけ前倒し)** を推奨し、Codex も同じ結論を独立に導いた。判断軸は **P7 (再現可能な証跡) + P9 (単一責任)**。

Codex の表現:

> Step 6 をきれいにするためというより、Step 5 の採用判定・証跡生成の意味論を未確定のまま次工程へ渡さないため

これは「Step 6 のスコープ純度」より一段深い理屈で、得心した。

### 三次補修の実装内容

**C 系 (完全前倒し)**:

- gate.schema.json / gate.runtime.schema.json に `run_id` を必須追加 (`^r[0-9a-f]{4}$`)
- paths.run_dir のサフィックスを `<compact>-<run_id>` 形式に
- `timestamp_*` は wall-clock truth、衝突回避は `run_id` だけで担う
- `evidence._reserve_run_dir` で run_id を順次インクリメント、65535 全部埋まれば `RunDirReservationError` で停止
- 旧版の microsecond suffix fallback は廃止
- 手書きリファレンス + 12 個の schema fixture を一括更新
- REQ meta トポロジカル順検証 (M1): `depends_on_order_violation` kind を追加

**B 系 (型・構造のみ前倒し)**:

- preflight.py を 5 関数に分割:
    - `validate_schema_sources` / `inspect_policy_graph` / `resolve_adopted_stages` / `check_runtime_support` / `run_preflight`
- 中身は既存ロジックの移動だけ、API は仮置きで Step 6 で調整可能
- `PreflightIssue.severity` フィールド追加 (Phase 1 は全件 `"blocker"`、Step 6 validate-policy で `"warning"` を初使用予定)

### Codex 二次レビューの追加チェック項目 7 件への対応

二次レビュー末尾で Codex が挙げた 7 項目を補修内に折り込んだ。特に重要だったのは **#1 (run_id schema pattern と生成規則の一致)** で、私はこの時点で「一致している」と回答していた。**この回答が次のレビューで誤りだったと露見する**。

## Step 5 四次補修: Codex 三次レビュー反映 (commit `a42b1b0`)

### Codex 三次レビュー (重大 1 + 中 1)

| 区分 | # | 指摘 | 本コミットでの対応 |
|---|---|---|---|
| 重大 | RRR1 | schema pattern `^r[0-9a-f]{4}$` が `r0000` を受理 (生成側は `_RUN_ID_MIN=1`) | 対応 (`not: {const: "r0000"}` 追加) |
| 中 | RRR2 | paths.run_dir の suffix pattern が schema で縛れていない | 対応 (両 schema に pattern 追加) |

Codex は他はすべて「Step 5 を完結と宣言してよい」と評価。「`r0000` だけ潰せば完結」という辛口の指摘で締めくくった:

> 辛口に言うと、「完結」と言う前に r0000 は潰してください。

### r0000 が見過ごされていた構造

私は三次補修時点で「生成側 `_RUN_ID_MIN = 1` から `r0001..rffff` のみ生成」と書きつつ、schema pattern を `^r[0-9a-f]{4}$` (= `r0000` も受理) のままにしていた。Codex 二次レビューの追加チェック #1 で「schema と生成が一致しているか」と問われたとき、`r0000` の存在を見落として「一致」と即答した。

**「自分が一致と回答した直後にレビューで見落としを指摘される」 は、Codex レビュー 3 回の中で最も実用的な学びだった**。レビューに対する自分の回答も、次回のレビューで点検される対象になりうる。

### 四次補修の実装内容

- gate.schema.json / gate.runtime.schema.json の `run_id` property に `"not": {"const": "r0000"}` を追加
- 両 schema の `paths.run_dir` に `<timestamp_utc>-<run_id>` 形状を強制する pattern を追加 (`r(?!0000)[0-9a-f]{4}` で `r0000` を inline 拒否)
- テスト追加 (8 件):
    - `test_gate_run_id_regex_rejects_bogus_values` の parametric に `"r0000"` を追加
    - `test_gate_runtime_also_rejects_r0000` 新設
    - `test_gate_paths_run_dir_suffix_pattern_rejects_bogus_values` 新設 (parametric 6 件)

### Step 5 完結宣言

四次補修後、`detailed-design.md` の改訂履歴 v0.10 に **「Step 5 系は本版で完結」** を明記。残課題 (atomic write / byte offset / loader error / QGB_KEEP_RUNS warning) は Step 6 と一緒に扱うことを確定。

## 振り返り: Step 5 系 4 段補修から固まったパターン

### 1. Codex レビュー 3 回 + 補修 4 段の構造

Step 0〜4 では「Codex レビュー 1 回 + 補修 1 回」が標準だった。Step 5 は規模が大きく (5 モジュール + schema + 例 + ドキュメント)、扱う論点が広いため、レビュー 3 回が自然な流れになった。

| Step | レビュー回数 | 補修コミット数 |
|---|---|---|
| Step 0〜2 | 1〜2 | 各 1 (+ Step 2 は巻き戻し 1) |
| Step 3 | 1 | 1 |
| Step 4 | 1 | 1 |
| **Step 5** | **3** | **4** |

**「レビュー 3 回が異常」ではなく、「Step 5 は規模に応じてそれだけのレビューが要った」と読むのが正しい。** 大きな縦串は一度に完成しない。

### 2. 思想憲章を主軸にした取捨選択は機能した

各レビューで Codex は重大/中/軽微で指摘してきたが、すべてを即補修するのではなく:

- **即補修**: 重大 + 中の一部 (思想憲章違反、構造的問題)
- **次 Step に申し送り**: 中の一部 + 軽微 (実装の細部、優先度低)
- **見送り**: なし (今期は採用しないケースなし)

の 3 段で判断した。`detailed-design.md §12` の Step 6 申し送りテーブルは、この判断を可視化するために使った。

### 3. **ユーザーのスコープ指摘がレビューより本質的に効くケースがある**

Codex 二次レビュー後の Step 6 申し送りリストは、各論点が「Step 6 でやればいい」という個別判断で積まれていた。これは間違いではなかったが、**全体を俯瞰すると「Step 5 系の意味論」と「Step 6 系のスコープ」が混ざっていた**。

ユーザーから:

> Step6送りにされているもののうち、『設計フェーズ系コマンドの構築』というスコープから逸脱しているものはないですか

と問われて初めて、リストを A/B/C 分類で精査した。Codex は個別論点では正しいが、**「複数論点をまとめて見たときのスコープ整合性」は人間判断が一段強い** という学びになった。

### 4. レビューの回答も次のレビューの対象になる

四次補修で発覚した `r0000` 問題は、二次レビュー追加チェック #1 への私の回答 (「schema と生成は一致」) の誤りだった。Codex の追加チェック項目に対して即答するときも、その回答が次のレビューで点検される。

これは Phase 5 スキル化のときに重要になる: スキルが LLM 主観で回答した内容は、別 LLM のレビューで再点検されるべき (P6 の機械化と整合)。

### 5. 「完結」の定義を明示することの価値

Step 5 系の補修 4 段は最終的に「Step 5 完結」を `detailed-design.md` v0.10 に明記して閉じた。これは:

- どこまで Step 5 で閉じたかを git log / 詳細設計の両方から追えるようにする
- 次の Step (Step 6) で「Step 5 の証跡意味論は確定済み」という前提を持てる
- 残課題は「Step 6 と一緒に扱う」と明示することで、忘却を防ぐ

「**完結を明記する**」というのは、補修が複数段にわたるケースで特に効く規律になった。

## コミット履歴 (Step 5 系)

```
a42b1b0 Phase 1 Step 5 四次補修: schema と生成規則の完全整合 + Step 5 完結
eb5f2fb Phase 1 Step 5 三次補修: timestamp と run_id の責務分離 + preflight 5 関数分割
8864913 Phase 1 Step 5 二次補修: Codex 二次レビュー指摘の修正
6e51f47 Phase 1 Step 5 補修: Codex レビュー指摘の修正
7bef1b3 Phase 1 Step 5: qgb run の縦串を実装
050b01b Phase 1 Step 3〜4 の作業記録を追加  # 前回 journal
```

## テストと品質指標の推移

| 段階 | テスト件数 | ruff |
|---|---|---|
| Step 4 補修後 | 156 | clean |
| Step 5 本体実装後 | 173 | clean |
| Step 5 補修後 | 178 | clean |
| Step 5 二次補修後 | 184 | clean |
| Step 5 三次補修後 | 196 | clean |
| Step 5 四次補修後 | **204** | clean |

## 関連 Issue / 文書

- [#20](https://github.com/Yumeno/Quality-gate-builder/issues/20) Step 5: `qgb run` 最小実装 (本期で完結扱い)
- `development/docs/detailed-design.md` v0.10 (Step 5 完結を明記)
- `development/docs/philosophy.md` v1.0 (P5/P6/P7/P9 が本期の判断軸)

## 次のステップ

### Step 6: 設計フェーズ系コマンドの構築 (本来スコープ)

Step 5 完結により、Step 6 は **純粋に「設計フェーズ系コマンドの構築」スコープ** に絞られる:

- `qgb detect` — 対象系の言語/フレームワーク推定
- `qgb design-stages` (+ `--commit`)
- `qgb scaffold REQ-APP-001`
- `qgb validate-policy` (stage-design.md §11 の本体)
- `qgb verify` (揮発側のみで gate.json を更新しない軽量チェック)
- `qgb run --yes`
- fixture 復活 (`missing_required/` `dangling_ref/` `misplaced_contract/`)

加えて、Step 5 三次補修で前倒した B 部分 (preflight 5 関数分割 + severity) の **API 妥当性が validate-policy 実装で初めて実コードで検証される**。Codex 三次レビューでは:

> 5 関数の境界は妥当。severity は dead code ではなく先行型定義。Step 6 で `PreflightReport.ready()` が「issue 空」基準のままだと warning でも NOT_READY になるので、`blocking_issues()` / `warnings()` / `ready_for_run()` の API 整理が必要になる

と指摘されている。これは Step 6 着手時の最初の論点になる。
