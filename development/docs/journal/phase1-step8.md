# Phase 1 Step 8 — json_schema + 設計例パック 2 例追加 作業記録

着手: 2026-05-31
完結: 2026-06-01 (本体 1 コミット + 統合レビュー 5 段完走)

## Step 8 のスコープ

detailed-design.md §12 + 受け入れ条件 §12-19:

- **A**: json_schema verification_type の実装 (Phase 1 必須 verification_type の追加)
- **B**: examples/python-cli-pytest 構築 (受け入れ条件§12-19 の 3 例のうち 2 例目)
- **C**: examples/markdown-docs 構築 (3 例目)

Codex 計画レビューで採用した順序: A → B → C。A が後段の C で json_schema 例として消費されるため、先に runner 実装を固める。

## 着手前: Codex 計画レビュー

Step 6+7 と同じく 8 観点で相談。Codex の最優先指摘:

1. **json_schema は `$ref` present → failed** で押さえる (Phase 1 では `$ref` unsupported を明示)。`jsonschema` の resolver 経路を一切呼ばないことで R1 境界を維持
2. **項目順 A → B → C**: json_schema runner を先に固めて、後で markdown-docs が消費する
3. **examples の reference gate 比較**: command stage は環境差 (pytest 実行時間、platform-dependent 表示) が log に混ざる。durable signal は exit_code、reference との「完全一致」と「安定フィールドのみ比較」の判断を慎重に
4. **python-cli-pytest**: `python -m pytest -q` 経由で起動、pytest を optional dependency に
5. **markdown-docs**: 検証対象は docs/ に寄せ、README は example 説明に専念
6. **out-of-scope 文言**: 「Phase 1 では `$ref` unsupported」を明示

## 実装の流れ

### 項目 A: json_schema verification_type 実装

`qgb/core/runner.py` に `_run_json_schema` + `_schema_contains_dollar_ref` を追加:

```python
def _schema_contains_dollar_ref(node):
    """Recursively detect any $ref key in a parsed JSON Schema."""
    if isinstance(node, dict):
        if "$ref" in node:
            return True
        return any(_schema_contains_dollar_ref(v) for v in node.values())
    if isinstance(node, list):
        return any(_schema_contains_dollar_ref(v) for v in node)
    return False


def _run_json_schema(project_root, stage):
    # 1. target / schema 両方を resolve_project_relative (R1 ガード)
    # 2. JSON parse 失敗 → failed
    # 3. $ref present → failed (Phase 1 unsupported)
    # 4. check_schema で schema 自身の妥当性
    # 5. validator.iter_errors で target を検証
    # 6. errors を absolute_path で sort して log に記録
```

`_SUPPORTED_RUNTIME_TYPES` に `"json_schema"` を追加。

**Phase 1 out-of-scope (docstring 明記)**:
- $ref resolution (Phase 2 allowlist-based)
- format assertions (Phase 2 strict-mode opt-in)
- streaming validation / memory caps for large JSON
- remote / network schema fetch (常に unsupported)

テスト 12 件 (happy path / validation error / target/schema missing / JSON malformed / schema invalid / R1 escape / $ref unsupported / preflight support)。

### 項目 B: examples/python-cli-pytest 構築

最小構造で組み立て:
- `src/demo_cli/__init__.py`, `__main__.py`, `main.py` (argparse + greet サブコマンド)
- `tests/test_demo_cli.py` (4 件のユニットテスト)
- `pyproject.toml` (PEP 621, setuptools, pytest を optional dep)
- `.quality-system/` (config / policy / req meta / contracts)
- `evidence-reference/REQ-APP-001/latest/` (frozen gate / summary / stage logs)

stages 構成:
- S1 (command): `python -m pytest -q` が exit 0
- S2 (command): `python -m demo_cli --help` が exit 0 (S1 に depends_on)
- S3 (substring_match): README.md に "Installation" が含まれる

design-notes.md は **7 セクション完備** (generic-minimal と同じ section template):
1. 対象系の特徴
2. 段階数の決定根拠
3. 採用した段階と理由
4. 採用しなかった段階と理由
5. 思想憲章のどの項目が特に効くか
6. 段階間の依存関係
7. 既知の限界

実 host で `pip install -e ".[test]"` → `pytest` 動作確認 → `qgb run REQ-APP-001 --yes --path examples/python-cli-pytest` で ALLOW を確認。生成された gate.json を normalize (timestamp / run_id を 2026-05-21T120000Z / r0001 に固定) して `evidence-reference/` に配置。

### 項目 C: examples/markdown-docs 構築

Markdown 文書群の最小例:
- `docs/index.md`, `docs/api.md`, `docs/metadata.json`
- `schemas/metadata.schema.json` (JSON Schema 2020-12、$ref なし)
- `.quality-system/` (config / policy / REQ-DOC-001 meta / 3 contracts)
- `evidence-reference/REQ-DOC-001/latest/`

stages 構成:
- S1 (file_exists): `docs/index.md` が存在
- S2 (substring_match): `docs/index.md` に `# ` (H1 header) が含まれる (S1 に depends_on)
- S3 (json_schema): `docs/metadata.json` が `schemas/metadata.schema.json` を満たす (S1 とは独立)

design-notes.md 7 セクション完備。Python 依存ゼロで動作 (`qgb detect` は generic にフォールバック)。

実 host で `qgb run REQ-DOC-001 --yes --path examples/markdown-docs` で ALLOW を確認、reference gate を配置。

### tests/test_examples.py 拡張

`_STEP8_EXAMPLES` リストでパラメタライズ:
- 各 example が `qgb validate` を通る (6 ファイル: config + policy + meta + 3 contracts)
- reference gate が strict schema を通る
- REQ meta の stage_id が policy に存在
- contract_ref が実ファイルに解決
- gate.basis に期待する KNOWLEDGE-* / CONTRACT-* が含まれる
- gate.decision.scope が存在 (Step 6+7 統合レビュー RA2)
- timestamps の compact <-> rfc3339 整合
- stage log_ref が実ファイルに解決
- design-notes に 7 セクション存在
- contract の verification_type が policy stage と一致
- substring target が実際に keyword を含む
- markdown-docs metadata.json が schema を本当に満たす (独立テスト)

13 件追加。`test_preflight_checks.py` の "unsupported verification_type" テストを Step 8 で json_schema が runtime supported になったことに合わせて `future_unsupported_type` (架空値) で書き換え。

### 統合レビュー (段 1〜5 完走)

memory review-process の正しい姿で完走:

#### 段 1: Claude subagent 5 観点並列

correctness / P9 / philosophy / NF-004 / spec-drift の Explore agent を並列起動。22 件超の finding を収集。

#### 段 2: 集約

| 観点 | # | 重要度 | 内容 |
|---|---|---|---|
| correctness | C1 | low | jsonschema validator 例外の defensive guard 不在 |
| correctness | C2 | minor | `e.path` (deque) ソートが non-deterministic |
| P9 | -- | clean | 全観点 clean |
| philosophy | Ph1 | minor (P7) | pytest 出力 (`0.02s`) が非決定的 |
| NF-004 | W1 | minor | json_schema runner が resolved path を log に出さない |
| NF-004 | W2 | major | markdown-docs schema pattern が backslash を reject |
| NF-004 | W3 | blocker? | python-cli-pytest contracts で `python` が Windows で見つからない |
| spec-drift | S1 | minor | detailed-design.md §2/§7 が Step 8 を反映していない |

#### 段 3: Codex 横断レビュー

Codex の判定:
- **W3 → docs 対応**: contract に Windows 固有 launcher 知識を背負わせない (target project の責務)
- **W2 → docs 対応 (b)**: pattern はそのまま、README で forward slash 規約を明文化
- **W1 → 本体補修**: resolved path log で他 runner と慣行統一
- **C1 → 本体補修**: validator/iter_errors の defensive try/except
- **C2 → 本体補修**: sort key を `list(e.absolute_path)` に
- **Ph1 → docs 対応**: design-notes で「pytest 実時間は audit 対象外、exit_code が durable signal」を明示

横断的指摘: 「Windows first-class」を「target project の toolchain 名解決まで qgb が吸収」と読まないこと。design-notes に明文化推奨。

#### 段 4: 補修

- W1: `_run_json_schema` の R1 解決成功直後に `resolved target/schema` log
- C1: `try/except Exception` で defensive failed handling
- C2: `sorted(..., key=lambda e: list(e.absolute_path))` に変更
- W3: python-cli-pytest README に "Windows note" 32 行、design-notes に既知の限界 10 行
- W2: markdown-docs README に "Path convention" 15 行、design-notes に既知の限界 8 行
- Ph1: python-cli-pytest design-notes 既知の限界に pytest 実時間 + durable signal 注記

補修テスト 3 件 (W1/C1/C2)。

#### 段 5: 収束ループ

**1 周目**: Codex 環境 (windows sandbox 失敗) で実コード確認不可だが、**新規 finding 1 件** を出した:
> `sorted(..., key=lambda e: list(e.absolute_path))` のままだと、path 要素に `str` と `int` が混在するケースで比較不能になる可能性

Python 3 では `int < str` が TypeError、JSON Schema absolute_path が array index (int) と object key (str) を混ぜることに対応する真の指摘。

**2 周目補修 (C2 再)**:
```python
errors = sorted(
    validator.iter_errors(target_data),
    key=lambda e: [str(p) for p in e.absolute_path],
)
```

`str` 変換で混在型に対応。テスト `test_json_schema_errors_with_mixed_int_str_paths_do_not_crash` を追加 (`pages[0].path=123` (型違反、index 0) と `pages[1]={}` (required 欠落、index 1) で int + str 両方を含む absolute_path を生成)。

**2 周目 Codex 判定**: 「新規 finding なし、収束宣言可」。

memory review-process の収束条件達成。

## コミット履歴 (Step 8)

```
dd1f053 Step 8: json_schema verification_type + 設計例パック 2 例追加 (3 例完成)
```

本体 + 統合レビュー補修を 1 コミットにまとめた (Step 6c/6d/7 と同じパターン)。

## テストと品質指標の推移

| 段階 | テスト件数 | ruff |
|---|---|---|
| Step 7 完結時 | 406 | clean |
| 項目 A (json_schema runner) | 431 | clean |
| 項目 B (python-cli-pytest) | 444 | clean |
| 項目 C (markdown-docs) | 444 | clean (test_examples で 2 例分追加) |
| 段 4 補修 | 447 | clean |
| 段 5 (C2 再) | **448** | clean |

## 振り返り

### 1. 段 1〜5 完走の効果が出た

Step 6+7 統合レビューで確立した「段 1〜5 完走 + 収束ループ」を Step 8 で再現できた。特に **段 5 1 周目で Codex が C2 の新規指摘 (int/str 混在)** を出したのが大きい。1 周で打ち切っていたら、JSON Schema の混在 absolute_path で TypeError が出る経路が残っていた。memory review-process の「新規 finding 連続ゼロまで」が機能した瞬間。

### 2. W3 の docs 対応判断が綺麗だった

Codex の「contract に Windows 固有 launcher 知識を背負わせない」は P9 (target project の知識は qgb に紐づかない) と一貫した判断。`python` を `py -3` に書き換えると POSIX を壊し、`sys.executable` を使うと contract の説明力が落ちる。利用者責任として README で誘導するのが Phase 1 として最適。「Windows first-class を target toolchain の resolver まで qgb が吸収するわけではない」という境界が見えるようになった。

### 3. examples 3 例で 4 verification_type を網羅

| example | file_exists | substring_match | command | json_schema |
|---|---|---|---|---|
| generic-minimal | S1 | S2 | - | - |
| python-cli-pytest | - | S3 | S1, S2 | - |
| markdown-docs | S1 | S2 | - | S3 |

3 例で Phase 1 の 4 runtime-supported verification_type が完全網羅。教材としても重複なく機能の責務が分かれていて、利用者が「自分の対象系に近い例」を選びやすい。

### 4. subagent prompt ルールを memory に追記

段 1 を実行中に observe された「subagent が個別 Bash パスを追加し続けて settings.local.json が肥大化」問題への予防策。memory `parallel-strategy.md` に「Explore agent prompt は副作用最小」のルールを追記し、settings.local.json も整理 (個別 15 件を 6 件の傘に統合)。

これは「memory 更新が次回の subagent 並列で効く」設計。Step 9 以降の subagent 起動時には、prompt に「Read/Grep/Glob 優先、Bash 副作用最小」を含める運用が定着する。

### 5. command runner のメモリ上限は依然 Phase 1 では「log cap であり実メモリ cap でない」

Step 7 で確立した「64 KiB tail-truncate は log cap、実メモリ cap でない」が Step 8 でも継続。pytest 出力が 64 KiB を超えても log は truncate されるが、`subprocess.run(capture_output=True)` で全部メモリに載る。Phase 2 で `Popen` incremental に移行する余地は変わらず docstring に残っている。

### 6. Phase 1 受け入れ条件§12 進捗

Step 7 完結時点 17/24 → **Step 8 で 18/24** (19 が追加で達成)。残 6 件:

| # | 条件 | 状態 |
|---|---|---|
| 17 | Project Knowledge Base にユーザー明示情報を保存 | Step 9 予定 |
| 18 | 外部由来情報に requires_human_review 付与 | Step 9 予定 |
| 20 | 導入マニュアルが存在 | Step 9 予定 |
| 21 | 依存ライブラリ採用方針 + セキュリティ確認手順 | Step 9 予定 |
| 24 | skills/source/ 構造 + Phase 5 エージェント中立スキル要件 | Step 9 予定 |

(23 は Step 6 完結時に既達確認済み)

Step 9 で残 5 件すべて消化予定 (knowledge / 導入マニュアル / 依存ポリシー / skills/source/)。

## Step 8 で確立した API / 規約 (Step 9 入力)

- `verification_type=json_schema` の contract 規約 (target + schema、Phase 1 では $ref unsupported)
- gate.json `stages[].synthetic` / `synthetic_reason` フィールドは継続 (Step 6+7 統合レビュー RA1)
- decision.scope は継続 (Step 6+7 統合レビュー RA2)
- examples design-notes.md の 7 セクション template (test_examples.py で enforce)
- examples evidence-reference / .quality-system 分離 (Step 4 で確立、Step 8 で 3 例分維持)

## 次のステップ (Step 9)

- knowledge.jsonl 関連の追加実装 (受け入れ条件 17/18)
- 導入マニュアル (受け入れ条件 20)
- 依存ライブラリ採用方針 / セキュリティ確認手順 (受け入れ条件 21)
- skills/source/ 構造 + Phase 5 エージェント中立スキル要件 (受け入れ条件 24)

Phase 1 受け入れ条件§12 の残 5 件はすべて Step 9 で消化、Step 9 完結で Phase 1 全体達成の予定。
