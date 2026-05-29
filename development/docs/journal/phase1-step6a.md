# 作業記録: Phase 1 Step 6a (本体 3 コミット + 補修 2 段)

期間: 2026-05-23〜2026-05-30 (Step 5 完結記録の続き)

## 目的

Step 6a (`qgb validate-policy` 本体 + preflight 診断 API + fixture 3 件) と、それに続く **2 段の補修** の経緯を時系列で残す。Step 5 記録 (`phase1-step5.md`) の続編。

Step 6a は Step 6 全体の土台にあたるサブステップで、後続 6b/6c/6d が全て 6a の API に依存する。Codex レビューは 2 回、補修コミットは合計 2 本。本記録の目的:

1. なぜ Step 6a で **計画→本体 3 コミット→補修 2 コミット** という構成になったかの判断経緯を残す
2. Step 5 で確立した「Codex レビューを思想憲章で取捨選択する」規律が今期どう機能したかを残す
3. 「ユーザーが計画段階から Codex に意見を聞かせた」ことが Step 6 全体スコープの整理にどう寄与したかを残す
4. Step 5 の補修 4 段とは異なる「コミット粒度をあえて細かく切る」判断を採った理由を残す

## 全体の流れ

```
Step 6 計画確定                4 サブステップ分割 (Codex 計画レビュー反映)  commit f79282b
   ↓
Step 6a Commit 1               PreflightReport 診断 API 整理                commit ddccef4 (207 件)
Step 6a Commit 2               検査追加 + severity 振り分け + L3            commit 7a65bc7 (223 件)
Step 6a Commit 3               qgb validate-policy CLI + L2 + fixture 3 件  commit 61d5781 (234 件)
   ↓ Codex 一次レビュー
Step 6a 補修 1 次              M1 / M2 / m1 / m3                            commit 8c9278a (238 件)
   ↓ Codex 二次レビュー
Step 6a 補修 2 次              設計意図の明文化 + Step 6a 完結              commit e282452 (238 件)
                                                                            → Step 6a 完結
```

## 計画フェーズ: Codex に計画段階から相談 (commit `f79282b`)

### 規模認識

Step 6 全体のスコープ (detect / design-stages / scaffold / validate-policy / verify / run --yes / fixture 復活) は Step 1〜5 全体に匹敵する規模だった。Step 5 でやった「本体 1 コミットで一気に進めて補修で吸収」では破綻するリスクがあった。

### サブステップ分割案

Claude 案として 4 分割を提案:

- 6a 検査強化 (validate-policy + preflight 診断 API + fixture 復活)
- 6b 実行系小修正 (verify + run --yes + atomic + QGB_KEEP_RUNS)
- 6c 検出系 (detect + adapters)
- 6d 生成系 (design-stages + scaffold)

着手順: 6a 先行 (validate-policy が後続全部の検査土台、preflight 既存資産が一番多い)。

### Codex 計画レビュー (Step 5 までと違うパターン)

Step 5 までは「本体実装後にレビュー」だったが、Step 6 は規模が大きいので **計画段階で Codex に相談** した。Codex 指摘:

| 指摘 | 内容 |
|---|---|
| 6a の API 確定の巨大化を避ける | `iter_issues(severity)` を主 API に、`ready_for_run` は runner 専用 |
| fixture 復活を「仕様固定装置」として位置づける | 6a の完了条件にする |
| Step 5 残課題を性質別に分散 | loader_error / byte offset → 6a、atomic / QGB_KEEP_RUNS → 6b |
| `qgb verify` を 6b の最初に | preflight API の最初の消費者として 6a の過不足を早期に見る |
| adapters は 6c で `DetectedProjectProfile` データ境界を固定 | validate-policy 経路と混ざらないようにする (P9 維持) |
| 6d 規模は 0.7 → 0.9〜1.2 に上方修正 | 生成系の出力仕様整合・idempotency で補修が出やすい |

これを **全面採用**。詳細設計 v0.11 に Codex 修正版を明文化。

### 「計画段階から Codex」が機能した理由

- 計画段階で API 設計が確定すると、本体実装中に「後で書き直し」が起きにくい
- 「6a を巨大化しない」「6b の最初に verify」など、本体着手後では気付きにくい順序最適化が前倒しできた
- Step 5 までと違って Codex 指摘との衝突がほぼなくなり、補修サイクルが短くなった (Step 5 補修 4 段 → Step 6a 補修 2 段)

## Step 6a Commit 1: PreflightReport 診断 API 整理 (commit `ddccef4`)

### 実装内容

Codex 計画レビューの指摘通り、`iter_issues(severity)` を主 API として整備:

```python
def iter_issues(self, severity: PreflightSeverity | None = None) -> Iterator[PreflightIssue]:
    ...

def blocking_issues(self) -> list[PreflightIssue]: ...
def warnings(self) -> list[PreflightIssue]: ...
def has_blockers(self) -> bool: ...
def ready_for_run(self) -> bool: ...  # qgb run 専用
def ready(self) -> bool: ...  # Step 5 後方互換、ready_for_run() に委譲
```

- 主 API は severity フィルタ付き iter (拡張可能性)
- `has_blockers()` は **中立 API** (validate-policy で使う、P9: 意味の混在を避ける)
- `ready_for_run()` は **run 専用** (名前で意図を表す)
- `ready()` は Step 5 callers の後方互換のため残す (新規コードは使わない)

### コミット粒度の判断

ユーザー指摘:

> 途中でCompactingが走るとか障害がおきるとかのリスクがあるから、Step6全体完了までコミット待つべきかというと、それはリスクでは

これを受けて、Step 6a 内も **API 整理 / 検査追加 / CLI** の 3 コミットに切ることに決定。各コミット時点で:

- テストは全て pass
- ruff clean
- 既存機能は壊れない (中間状態でも safe)

### テスト追加 (3 件)

- `test_preflight_report_diagnostic_api`: severity フィルタ、便利メソッド、has_blockers/ready_for_run の組合せ
- `test_preflight_report_warnings_only_is_ready_for_run`: warning だけは続行可
- `test_preflight_legacy_ready_matches_ready_for_run`: 後方互換確認

## Step 6a Commit 2: preflight 検査追加 + severity 振り分け + L3 (commit `7a65bc7`)

### 新 issue kind 5 件

| kind | severity | 思想 | 検査内容 |
|---|---|---|---|
| `duplicate_stage_id` | blocker | P9 | policy.stages の id 重複 |
| `misplaced_contract` | blocker | P7 | contract_ref が canonical layout 違反 |
| `missing_contract_field` | blocker | P9 | policy の required_contract_fields が contract に欠落 |
| `stage_count_out_of_range` | **warning** | P9 | 段階数が推奨レンジ 3..7 を外れる |
| `wrong_type` | blocker | NF-007 | LoaderError.wrong_type を missing_contract から分離 (L3) |

**`stage_count_out_of_range` が Phase 1 初の warning 実コード使用**。Step 5 三次補修で型だけ前倒した `PreflightIssue.severity` の最初の本番利用。generic-minimal (2 段階) で実際に warning が出ることをテストでロック。

### severity 振り分け (mode 切り替え)

```python
PreflightMode = Literal["run", "validate_policy"]

def check_runtime_support(adopted, report, *, mode: PreflightMode = "run"):
    severity = "warning" if mode == "validate_policy" else "blocker"
    # manual_check_required / unsupported_verification_type を severity で分岐
```

同じ findings (`manual_check_required` / `unsupported_verification_type`) を:
- `qgb run`: blocker (実行不能)
- `qgb validate-policy`: warning (policy 自体は malformed ではない、Phase 1 runtime が未対応)

として記録。**kind は分けず severity だけ変える** 設計を Codex 計画レビューが推奨していた。

### `validate_policy_preflight()` 新規 entry point

`run_preflight` と同じ 4 helper を別の orchestration で組み立てる。`req_id=None` で project-wide 整合性のみ、`req_id` 指定で REQ レベルまで。

### Step 5 残課題 L3 の解消

LoaderError.wrong_type を `missing_contract` に collapse していた件を解消。`_loader_kind_for_policy` / `_loader_kind_for_meta` を helper として切り出し、kind マッピングを集約。

### テスト追加 (16 件) + 既存 2 件の更新

新ファイル `tests/test_preflight_checks.py` で各検査と mode 切り替えを単体テスト。

既存 2 件 (`test_preflight_issue_defaults_to_blocker_severity` / `test_preflight_helpers_are_individually_callable`) は generic-minimal で `stage_count_out_of_range` が warning として出ることを認識する形に書き換え (Phase 1 初の warning 混在テストの追随)。

## Step 6a Commit 3: qgb validate-policy CLI + L2 + fixture 3 件 (commit `61d5781`)

### CLI 実装

```
qgb validate-policy [REQ-ID] [--path] [--json]
```

exit code 規約:
- blocker あり → 2 (NOT_READY)
- warning のみ → 0、stderr に warning 列挙
- 全クリア → 0、stdout に "OK"

text 出力では blocker と warning を別ブロックで列挙、warning は "qgb run will still proceed" と明示。

### L2 (substring_match の char offset 表記)

runner.py のログ表記を `byte offset` → `char offset` に変更。Python str.index が返すのは code point index (UTF-16 code unit ではない、UCS-4 でもない: Python の str は内部表現に依存しない code point の列) であり、"byte offset" は誤りだった。

reference (`examples/generic-minimal/evidence-reference/.../S2.log`) も追随。

### fixture 3 件 (仕様固定装置として)

`tests/fixtures/validate_policy/` に作成:

| fixture | 期待 blocker | 役割 |
|---|---|---|
| `missing_required/` | `missing_required_file` (policy.json) | 正本欠落を検出 |
| `dangling_ref/` | `unknown_stage_id` (S999) | stage_id の dangling reference 検出 |
| `misplaced_contract/` | `misplaced_contract` (sub/ 配下) | canonical layout 違反検出 |

各 fixture に `README.md` を添え、何を spec として固定しているかを明示。Codex 計画レビューでは「validate-policy の仕様固定装置」として位置づけることが推奨されていた (Step 2 巻き戻し時に validate から外した cross-file integrity の責務が validate-policy で復活していることの回帰防止)。

### NF-004 への配慮

CLI 出力と preflight メッセージから em dash `—` や `§` を除去 (Windows cp932 互換)。`"stage-design.md §11"` → `"stage-design.md section 11"` など。

### テスト追加 (11 件)

新ファイル `tests/test_validate_policy.py`:
- happy path (warning only, --json)
- usage error (nonexistent path / file path)
- 3 fixture それぞれの blocker 検出
- subprocess smoke (`--help` が "not yet implemented" を出さない、`--json` で OK)

## Step 6a 補修 1 次: Codex 一次レビュー反映 (commit `8c9278a`)

### Codex 一次レビュー (major 2 + minor 3)

| 区分 | # | 指摘 | 対応 |
|---|---|---|---|
| major | M1 | `misplaced_contract` が `wrong_type` を覆い隠す | 対応 (canonical 優先を仕様化) |
| major | M2 | `duplicate_stage_id` 後の解決継続が曖昧 | 対応 (graph integrity short-circuit) |
| minor | m1 | runner.py コメント "UTF-16 code unit" は不正確 | 対応 (code point index に修正) |
| minor | m2 | `check_runtime_support(mode=)` は第三モード前提なら policy 分離 | **保留** (Phase 2 で出てから、YAGNI) |
| minor | m3 | warning を stderr に出す方針の CI 互換性を docs に明記 | 対応 (CLI 出力規約節を新設) |

### M1 の判断: loader 先行 vs canonical 先行

Codex は両案を提示していた:

- (a) loader で path safety を先に確認 → 危険参照は wrong_type
- (b) canonical mismatch 優先を仕様化、wrong_type は policy/meta loader 用

私は (b) を採用。理由:

- 文字列マッチは I/O 不要・ファイルシステム状態に非依存で安定
- designer に「rename/move」という最小の修正を指せる (P9)
- root escape は canonical を満たした上での symlink 経由でのみ起きる狭い経路 → wrong_type の意義は残る

### M2 の判断: 何を short-circuit させるか

`_GRAPH_INTEGRITY_BLOCKER_KINDS = {"duplicate_stage_id", "depends_on_cycle"}`:

- duplicate id → policy_stages map が silent に最初の出現を選ぶ → どの定義を指しているか曖昧
- cycle → graph が DAG でない → depends_on_order_violation 診断が ill-defined

`depends_on_unknown` は意図的に **含めない**。一部 dangling でも per-stage 診断は意味を持つから。counter-spec として `test_dangling_depends_on_does_not_short_circuit` を追加。

### テスト spec lock の強化

「自分のレビュー回答が次のレビューで点検される」(Step 5 r0000 問題と同型のリスク) を意識し、テスト名と negative assertion を強化:

- `test_absolute_contract_ref_is_wrong_type` → `test_absolute_contract_ref_is_reported_as_misplaced_contract` にリネーム + `assert "wrong_type" not in blocker_kinds` 追加
- `test_root_escape_via_dotdot_is_wrong_type` → `test_root_escape_via_symlink_is_wrong_type` にリネーム (実体は symlink、名前と実装の一致)
- `test_dotdot_contract_ref_is_reported_as_misplaced_contract` を新規追加 (M1 spec の網羅性向上)

## Step 6a 補修 2 次: 設計意図の明文化 + Step 6a 完結 (commit `e282452`)

### Codex 二次レビュー結果

> **Step 6a は補修 1 次で完結扱いして Step 6b へ進んでよい。blocker は見当たらない。**

ただし条件付きで 2 件:

- major: validate-policy の short-circuit は設計意図を明文化すべき
- minor: "cheaper diagnostic first" を一般原則にしすぎない方がよい

### docs-only の小修正

major: `_has_graph_integrity_blockers` コメントに「validate-policy でも止める理由」を追記。

> `qgb validate-policy` は通常「できるだけ多くの設計診断を返す」役割を担うが、それは各診断が単独で正しいときに限る。誤った/不安定な findings を正しい一次 finding に重ねるとフィードバック品質が劣化するため、integrity blocker を先に修正させてから再実行する運用を選ぶ

minor: `resolve_adopted_stages` docstring の "cheaper diagnostic first" を「本ケース限定の judgment」に書き換え、M2 が逆方向のトレードオフ ("uncontaminated diagnostics first") を採用していることを明示。両者は併存し、各ケースの条件で選び分ける。

詳細設計 §12 の M1/M2 説明にも同じ趣旨を反映。

### 「完結」の宣言

詳細設計 v0.14 で `Step 6a 完結` を明文化。Step 5 で確立した規律 (「完結を明記する」) を踏襲。

## 振り返り

### 1. 計画段階の Codex レビューが補修サイクルを縮めた

Step 5 補修 4 段に対し、Step 6a は補修 2 段で完結した。違いは「Codex に計画段階から相談した」こと:

| | Step 5 | Step 6a |
|---|---|---|
| 計画への Codex 参加 | なし | あり (本体着手前) |
| 本体コミット | 1 | 3 (細分化) |
| 補修サイクル | 4 段 | 2 段 |
| 各サイクルでの新規実装 | あり (構造変更) | なし (補修中心) |

計画段階で API 設計が確定すると、本体実装中の手戻りが減る。これは Phase 2 以降のサブステップにも適用できる規律。

### 2. コミット粒度の判断は「リスク」で決まる

Step 5 では「本体 1 + 補修 4」だった。Step 6a で「本体 3 + 補修 2」に変えた理由は **ユーザー指摘**:

> 途中でCompactingが走るとか障害がおきるとかのリスクがあるから、Step6全体完了までコミット待つべきかというと、それはリスクでは

完成度ではなく Compacting / 障害リスクで粒度を決める、という判断軸。**各コミットが中間状態でも safe であること** を完了条件にした (テスト pass + ruff clean + 既存機能は壊さない)。

### 3. Step 5 の "warning" 先行型定義が Step 6a で初めて実利用された

Step 5 三次補修で `PreflightIssue.severity` を型として導入したが、当時は全件 blocker で、warning を出すコードはなかった。Step 6a Commit 2 で `stage_count_out_of_range` が初の warning として乗ったとき、既存テストが warning 混在を扱えず 2 件が落ちた。これは「先行型定義は実コードで使うまで本当の意味で確定しない」という Codex Step 5 三次レビューの指摘と一致する事象だった。

Step 6 計画レビューで Codex が「6a の API 確定の巨大化を避ける」と指摘したのもこの線。

### 4. spec lock テストの書き方

Step 5 の r0000 問題 (「自分のレビュー回答が次のレビューで点検される」) を踏まえ、Step 6a 補修 1 次では:

- テスト名を spec 内容で命名 (`test_absolute_contract_ref_is_reported_as_misplaced_contract`)
- negative assertion で「出ないこと」も lock (`assert "wrong_type" not in blocker_kinds`)
- counter-spec テスト (`test_dangling_depends_on_does_not_short_circuit`) で「意図的に対象外」も lock

Codex 二次レビューでは「negative assert は spec lock として実用上十分」と評価された。

### 5. ユーザー判断が補修判断に効くケース

m2 (mode の第三モード前提) を YAGNI で保留する判断は Claude が出したが、ユーザーが「OK」で承認してくれることで Phase 2 送りが確定した。Codex は「第三モードが出るときに helper に切る方がよい」と指摘していたが、出るかどうかわからない時点で構造を増やすコストは大きい。Phase 1 範囲では二分岐で十分という判断は人間判断軸。

Step 5 のユーザー scope challenge (B/C 分類) と同じく、**スコープ判断は人間の方が強い** ことを再確認。

## コミット履歴 (Step 6a 系)

```
e282452 Step 6a 補修 2 次: 設計意図の明文化 + Step 6a 完結
8c9278a Step 6a 補修 1 次: Codex レビュー M1/M2/m1/m3 反映
61d5781 Step 6a Commit 3: qgb validate-policy CLI + L2 + fixture 3 件
7a65bc7 Step 6a Commit 2: preflight 検査追加 + severity 振り分け + L3
ddccef4 Step 6a Commit 1: PreflightReport の診断 API を整理
f79282b Step 6 計画確定: 4 サブステップ分割 (Codex 計画レビュー反映)
e5ee893 Phase 1 Step 5 (本体 + 補修 4 段) の作業記録を追加  # 前回 journal
```

## テストと品質指標の推移

| 段階 | テスト件数 | ruff |
|---|---|---|
| Step 5 完結時 | 204 | clean |
| Step 6 計画確定後 | 204 | clean |
| Step 6a Commit 1 後 | 207 | clean |
| Step 6a Commit 2 後 | 223 | clean |
| Step 6a Commit 3 後 | 234 | clean |
| Step 6a 補修 1 次後 | 238 | clean |
| **Step 6a 補修 2 次後** | **238** | clean |

origin/main から ahead: 22 → 28 (Step 6a 系で +6 コミット)

## 関連 Issue / 文書

- `development/docs/detailed-design.md` v0.14 (Step 6a 完結を明記)
- `development/docs/philosophy.md` v1.0 (P9 単一責任原則 / P5 ALLOW 限定 / P7 再現可能な証跡 が本期の判断軸)
- `development/docs/stage-design.md` v1.0 (§11 validate-policy 検査表が本期の実装スコープ)

## 次のステップ

### Step 6b: 実行系の小修正

Codex 計画レビュー (再掲) で確定済みの順序:

1. `qgb verify` (validate-policy + 軽量 run。揮発側のみで gate.json は更新しない) — **6b の最初に実装**。preflight API の最初の消費者として 6a の過不足を早期に見る役目
2. `qgb run --yes` フラグ (実行前確認プロンプト)
3. `_replace_dir_contents()` の atomic 化 (Codex M4/M5、Step 5 残課題): `latest.tmp-<ts>` で書いて rename
4. `QGB_KEEP_RUNS` 不正値の warning (Codex L4、Step 5 残課題)

規模: Step 5 を 1.0 として 0.5〜0.7 (Codex 計画レビュー反映後)。

### 6b 着手時の論点候補

- `verify` 実装中に 6a API の過不足が出る可能性 (Codex 計画レビューが「6a を完全固定と呼ばない」と指摘した点)
- atomic 化と warning は性質が異なるので、6b 内も 2〜3 コミットに分割するか
- `qgb run --yes` の confirmation prompt は Windows PowerShell でどう動くか (NF-004)

これらは 6b 着手時の最初の論点として整理する。
