# Phase 1 Step 6d — qgb design-stages + qgb scaffold 作業記録

着手: 2026-05-31
完結: 2026-05-31 (本体 1 コミット + Codex 横断レビュー指摘 9 件のうち中以上 6 件を本体に吸収)

## Step 6d のスコープ

detailed-design.md §12.6d より:

- `qgb design-stages` 提案フェーズ (Phase 1: ルールベース推定 + ユーザー確認、stage-design.md §10.1)
- `qgb design-stages --commit` 採用フェーズ (`policy.json` に書き込み + `validate-policy` を内部で呼ぶ)
- `qgb scaffold REQ-APP-001` (REQ + contract + テスト雛形生成)
- examples は最小 1 件のみ (重い設計例パック化は Step 7 / 8 送り)
- 既存ファイルがある場合の挙動 (idempotency) を 6d の完了条件に含める

要件 §6.2.1 で qgb design-stages / qgb scaffold は Phase 1 必須コマンド。Phase 1 の最後の機能ブロック。

## 着手前: Codex 計画レビュー

Step 6c と同じく、8 観点の相談で計画を Codex に確認。Codex の最優先指摘 2 点を着手前に取り込んだ:

1. **「生成物を validate できる状態で出す」** — scaffold の成果物が即 `qgb validate` で落ちると UX が崩れる。schema-valid な placeholder を使う (`null` でなく `"TODO: ..."`)、run で誤って PASS しない値にする
2. **`design-stages --commit` は validate-policy 通過まで含めて 1 操作** — 失敗時に既存 `policy.json` を破壊しない atomic 性を Phase 1 でも保証

8 観点それぞれの判断:
- template 表現: A (実ファイル) — Phase 1 は `examples/generic-minimal` のみ template として使う、Python CLI / Markdown も generic に fallback、matcher は language ベース 1 対 1
- atomic commit: tmp project copy → validate-policy(tmp) → 本物に os.replace
- REQ id: scaffold 入口で正規表現チェック、不正は exit 64
- contract 雛形: schema-valid placeholder、run で誤 PASS しない値
- tests/quality/: L1 / L5 のみ
- idempotency: refuse + --force (対象 REQ のみ)
- exit code: 0 / 2 / 64 のみ。1 は使わない (DENY 概念なし)
- out-of-scope 宣言: concurrent / file locking / interactive / LLM matcher / git / full six-layer

## 実装の流れ (3 項目 + Codex 横断レビュー)

### 項目 1: design-stages 提案フェーズ

`qgb/core/design_stages.py`:

```python
@dataclass(frozen=True)
class StageProposal:
    id: str
    name: str
    responsibility: str
    depends_on: list[str]
    verification_type: str
    required_contract_fields: list[str]


@dataclass(frozen=True)
class DesignProposal:
    template: str
    stages: list[StageProposal]
    detect: DetectionResult
    warnings: list[str] = []

def propose_design(project_root) -> DesignProposal:
    detect = run_detect(project_root)
    template = _pick_template(detect)  # Phase 1: 常に generic-minimal
    stages = _load_template_stages(template)
    return DesignProposal(template=template, stages=stages, detect=detect)
```

CLI 側:
- `qgb design-stages [--path P] [--json]` → 提案のみ (policy 不変)
- text: `Detected: ...` + `Recommended template: ...` + `Proposed stages: ...`
- JSON: `{schema_version: 1, ok: true, committed: false, detect: {selected, candidates}, proposed: {template, stages}}`

テスト 8 件 (text / JSON / detect 反映 / policy 不変 / template name / usage error / stage 構造)。

### 項目 2: design-stages --commit (atomic)

`commit_design()`:

```python
def commit_design(project_root, proposal, *, force=False) -> CommitOutcome:
    # 1. policy.json なしなら refuse (qgb init 未)
    # 2. 既存 stages 非空 かつ not force → refuse
    # 3. sibling staging dir に project を copy
    # 4. staging の policy.json#stages を proposal で書き換え
    # 5. validate_policy_preflight(staging)
    # 6. blocker あれば policy 不変で refuse
    # 7. 本物の policy.json を atomic に入れ替え
```

判断ポイント:
- staging dir / tmp file は当初固定名で書いたが、Codex 横断レビューで指摘されて tempfile.mkdtemp / mkstemp に変更
- validate-policy は file-on-disk 前提なので、memory 上で validate するより tmp tree で実行する方が単純

テスト 9 件 (commit / preserve non-stage / JSON / refuse 既存 / --force / no policy / atomic 失敗 / staging cleanup / validate-policy gate)。

### 項目 3: scaffold (REQ + contract + L1/L5 雛形)

`qgb/core/scaffold.py`:

```python
REQ_ID_PATTERN = re.compile(r"^REQ-[A-Z0-9]+-[0-9]{3,}$")  # schema と同一

def scaffold_req(project_root, req_id, *, force=False) -> ScaffoldOutcome:
    # 1. REQ id regex バリデート (不正は invalid REQ id message → CLI で EXIT_USAGE)
    # 2. policy.json なし → NOT_READY
    # 3. policy.stages 空 → NOT_READY
    # 4. policy shape 防御 (Codex 補修 5)
    # 5. 既存 meta/contracts と --force 判定
    # 6. REQ meta 生成 (全 stage required:true)
    # 7. 各 stage に schema-valid placeholder contract 生成
    # 8. tests/quality/L1_behavior + L5_contract + .gitkeep
```

contract placeholder の verification_type 別ロジック:
- `command`: `command=["TODO-replace-with-command-argv"]`, `expected_exit_code=0`
- `file_exists`: `target="TODO/<stage>/placeholder-target.txt"` (project 内に実在しない)
- `substring_match`: `target` + `must_contain=["TODO-replace-with-substring"]`
- `json_schema`: `target` + `schema` で placeholder
- `manual_check`: `description` (P6 注記つき)

CLI 側:
- `qgb scaffold REQ-XXX-NNN [--path P] [--force] [--json]`
- invalid REQ id → EXIT_USAGE (typo は usage error)
- その他失敗 (no policy, existing) → EXIT_NOT_READY

テスト 17 件 (meta / contracts / schema-valid / L1L5 / not L2-4/6 / JSON / REQ id validation / no policy / idempotency / --force scope / 他 REQ 不変 / usage error / end-to-end with run = DENY)。

### Codex 横断レビューと補修

本体実装後、Codex に 7 観点でレビューを依頼。指摘 9 件:

| # | 重要度 | 内容 | 対応 |
|---|---|---|---|
| 1 | **対応 (致命的)** | staging dir 固定名で pre-existing 削除 | `tempfile.mkdtemp` 化 |
| 2 | 対応 (中) | 固定 staging/tmp で並行競合 | 1 と同時解消 |
| 3 | 対応 (中) | `policy.json.tmp` 固定名 → 既存破壊 | `tempfile.mkstemp` 化 |
| 4 | 対応 (中) | scaffold --force が atomic でない | **docstring out-of-scope** (Phase 2) |
| 5 | 対応 (中) | scaffold が KeyError で落ちうる | stage shape 防御チェック追加 |
| 6 | 対応 (中) | command placeholder で PATH 上同名 → 誤 PASS | preflight unsupported で弾かれることを担保するテスト |
| 7 | Phase 2 (採用) | DesignProposal.committed の責務曖昧 | dataclass フィールド削除 |
| 8 | Phase 2 | ScaffoldOutcome.created の分類弱 | docstring out-of-scope |
| 9 | docstring | stage id 重複防御は preflight 任せ | docstring out-of-scope |

中以上 6 件 (1/2/3/5/6/7) を本体に吸収。4/8/9 は docstring に明記。

補修テスト 5 件:
- `test_commit_does_not_delete_pre_existing_user_staging_dir` (補修 1)
- `test_commit_does_not_clobber_pre_existing_policy_tmp` (補修 3)
- `test_scaffold_returns_not_ready_for_broken_policy` (補修 5)
- `test_command_placeholder_does_not_falsely_pass` (補修 6)
- `test_design_proposal_dataclass_has_no_committed_field` (補修 7)

## コミット履歴 (Step 6d)

```
a1e8cf4 Step 6d: qgb design-stages (proposal + commit) + qgb scaffold
```

## テストと品質指標の推移

| 段階 | テスト件数 | ruff |
|---|---|---|
| Step 6c 完結時 | 327 | clean |
| 項目 1 (design-stages 提案) | 335 | clean |
| 項目 2 (design-stages --commit) | 344 | clean |
| 項目 3 (scaffold) | 361 | clean |
| 補修 (Codex 9 件のうち中以上 6 件) | **366** | clean |

## 振り返り

### 1. 計画レビューの効果が累積している

Step 6a → 6b → 6c → 6d と通して「実装前に Codex 計画相談」を続けた結果、本体実装後の Codex 横断レビューで「設計が大幅に変わる」レベルの指摘がほぼ出なくなった。今回も中以上 6 件は全て「実装の細部」(tempfile 化、shape 防御、docstring 整理) で、構造変更ゼロ。これは計画レビューが**累積的に効く**ことを示している。Step 6a の前に始めたパターンが、Step 6d で「実装に近い局所修正だけで済む」状態を作っていた。

### 2. Step 6b の atomic swap パターンが再利用された

design-stages --commit の atomic 性は Step 6b 項目 2 (curated/latest/ の atomic swap) と本質的に同じパターン: tmp に書く → validate → 失敗なら原本不変 / 成功なら os.replace。Step 6b で確立した思考を別文脈に持ち込めたのは、メモ的に書くと **「atomic に書きたいときは sibling tmp + os.replace」が memory pattern として残っている** からだと思う。新しく考えなくてよい。

### 3. Phase 1 の最後で受け入れ条件を再チェック

Step 6d で Phase 1 必須コマンドが揃った。要件 §12 の 24 件 (旧 8 削除済み) と現状の対応:

| # | 条件 | 状態 |
|---|---|---|
| 1 | Python で qgb CLI を起動できる | ✅ Step 1 で完了 |
| 2 | `python -m qgb init` で `.quality-system` を生成 | ✅ Step 3 |
| 3 | `python -m qgb detect` で対象系推定 | ✅ Step 6c |
| 4 | `python -m qgb design-stages` で段階提案、`--commit` で採用 | ✅ Step 6d |
| 5 | config.json、policy.json、REQ、contract.json を生成 | ✅ Step 6d (scaffold) |
| 6 | `python -m qgb validate` で JSON 正本を検証 | ✅ Step 2 |
| 7 | `python -m qgb validate-policy` で段階設計の品質検査 | ✅ Step 6a |
| 8 | `python -m qgb run <REQ>` で採用判定、常に全 stage 実行 | ✅ Step 5 + 6b |
| 9 | gate.json、summary.md、stages/*.log を出力 | ✅ Step 5 |
| 10 | 採用側 + 揮発側の 2 系統に書き込み | ✅ Step 5 (Step 6b で atomic 化) |
| 11 | 検査成功時に ALLOW | ✅ Step 5 |
| 12 | 検査失敗時に DENY | ✅ Step 5 |
| 13 | 構成不備時に NOT_READY、gate.json を生成しない | ✅ Step 5 |
| 14 | `phase: red` の DENY を期待結果として証跡化 | ⚠️ Step 7 予定 (基盤は Step 5 で確定) |
| 15 | `manual_check` を含む REQ の run は NOT_READY | ⚠️ Step 7 予定 |
| 16 | waived を理由つきで `knowledge.jsonl` に記録 | ⚠️ Step 7 予定 |
| 17 | Project Knowledge Base にユーザー明示情報を保存 | ⚠️ Step 9 予定 |
| 18 | 外部由来情報に `requires_human_review` 付与 | ⚠️ Step 9 予定 |
| 19 | 設計例パック 3 例が動作 (generic-minimal / python-cli-pytest / markdown-docs) | ⚠️ Step 8 予定 (Phase 1 では generic-minimal のみ) |
| 20 | 導入マニュアルが存在 | ⚠️ Step 9 予定 |
| 21 | 依存ライブラリ採用方針 + セキュリティ確認手順が文書化 | ⚠️ Step 9 予定 |
| 22 | LLM レビュー単独で ALLOW を出さない方針が明示 | ✅ philosophy.md P6 |
| 23 | 思想憲章、段階設計仕様、フレームワーク境界の 3 文書が並列維持 | ✅ |
| 24 | `skills/source/` の構造が予約、Phase 5 エージェント中立スキルが要件確定 | ⚠️ Step 9 予定 |

**Step 6 完結時点 (Phase 1 の中間マイルストーン):** 14 件達成、10 件残 (Step 7-9 で消化予定)。コアの 4 / 5 / 8 / 13 はすべて Step 6 内で達成。

### 4. Phase 1 の純度を守れた

Step 6 全体で扱った "Phase 1 out-of-scope" 宣言の合計は (粗く数えて) 30 件以上。fsync、並行制御、entry_points、template merge、interactive edit、LLM 推論、monorepo、shebang、windows case-insensitive、dependency-groups、etc. これらを docstring out-of-scope として明示することで、「Phase 1 MVP として何を作って何を作らないか」が後段の Phase 2 設計時に **手戻りなく** 再利用できる状態になっている。

### 5. 「自走サイクル」が機能した

Step 6c / 6d を Step 6 全体での自走として完走した。サイクル: 計画 Codex 相談 → テストファースト → 実装 → ruff/pytest → Codex 横断レビュー → 三分類 → 補修 → 本体 1 コミット → ジャーナル。**判断を仰がず進めても精度が落ちないことが確認できた** のは、計画レビューと横断レビューの 2 段階で人間判断の代替が成立しているから。memory の review-process (高速化でなく手戻り削減) がここまで通底している。

### 6. 「context まとめは Read + Write」を思い出せた

Step 6c / 6d の Codex 横断レビュー context 組み立てで、複数ファイルを 1 つの context にまとめる必要があったが、memory の `codex-context-files.md` ルール通り **Read + Write の組み合わせ** で組み立てた。CLAUDE.md にフックを入れたおかげで、compaction 越しでも「Codex context を作るときは memory を見る」が思い出せる構造になっている。これは前ステップの failure mode を memory + CLAUDE.md hook で構造的に予防できた最初の例。

## Step 6 全体の振り返り (6a → 6b → 6c → 6d)

Step 6 は Phase 1 の中で最も大きいブロック (規模相対値 6a 1.0, 6b 0.6, 6c 0.7, 6d 1.0 で合計 3.3)。サブステップ分割と計画 Codex レビューを 4 回繰り返すことで完走できた。

**確立できたパターン:**
- 計画 Codex 相談 → 構造修正の着手前取り込み → 実装 → Codex 横断レビュー → 三分類 → 本体に補修吸収
- atomic swap (sibling tmp + os.replace) を core 全体で再利用
- schema_version=1 を JSON 出力に固定して Phase 2 互換性の入口にする
- core / adapters 分離 (P9) を厳格に維持
- Phase 1 out-of-scope を docstring で明示 (memory より長持ちする方法)

**学び:**
- spec 議論は実装前に解決する (verify 撤回が好例)
- Codex 横断レビューの指摘は「対応 / Phase 2 / docstring out-of-scope」三分類で受け止める
- memory + CLAUDE.md hook で compaction 越しの failure を予防できる
- 補修コミットを別に切るかは「補修内容が独立に意味を成すか」で判断 (Step 6a/6b は別切り、6c/6d は本体吸収)

## 次のステップ (Step 7)

Step 6 完結により Phase 1 必須コマンドは全揃い。Step 7 以降は機能拡張と仕上げ:

- **Step 7**: TDD phase=red の expected-failure 本実装 / `command` / `json_schema` verification_type の実装 / `manual_check` を含む REQ の NOT_READY 化 / waived の knowledge.jsonl 記録
- **Step 8**: 設計例パック 2 例追加 (python-cli-pytest / markdown-docs)
- **Step 9**: knowledge 追加コマンド、導入マニュアル、依存調査ポリシー文書

Phase 1 受け入れ条件§12 の残 10 件 (14, 15, 16, 17, 18, 19, 20, 21, 24) は Step 7-9 で消化予定。
