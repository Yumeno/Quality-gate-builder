# 作業記録: Phase 1 Step 0〜Step 2

期間: 2026-05-17 〜 2026-05-21

## 目的

本書は Phase 1 Step 0〜2 の作業経緯を時系列で記録する。実装の最終形は他文書 (`detailed-design.md`, コード本体, テスト) を見ればわかるが、**そこに至るまでの判断と試行錯誤** は git log と Issue だけでは追いにくいため、本記録に残す。

特に「外部レビュー (Codex) と Claude 自身のレビューを使い分けながら、思想と設計方針からブレないように補修と巻き戻しを繰り返した」プロセスを次回以降の Step でも再現できるようにする。

## 全体の流れ

```
Step 0   プロジェクト基盤        (実装 -> Codex レビュー -> 補修)
   ↓
Step 1   JSON Schema 群          (実装 -> Codex レビュー -> 補修 -> Codex 再レビュー -> 第 2 弾補修)
   ↓
Step 2   qgb validate            (実装 -> Codex レビュー -> 補修第 2 弾 -> 思想チェック -> 巻き戻し)
```

外部レビューを毎 Step 入れる方針が定着。「思想憲章と要件定義書を共有して再レビュー」のパターンが特に重要 (Step 2 で発見)。

## Step 0: プロジェクト基盤

### 実装内容 (commit `0e5794c`)

- `pyproject.toml` (setuptools + jsonschema + pytest + ruff)
- `qgb/__init__.py`, `__main__.py`, `cli.py`
- `qgb/core/`, `qgb/adapters/`, `qgb/schemas/`, `qgb/templates/` ディレクトリ予約
- `tests/test_cli_smoke.py` (4 件)
- `.gitignore`, `README.md`

`python -m qgb --help` / `--version` / 未実装サブコマンド dispatch のみが動作する最小状態。

### Codex 第 1 回レビュー

Codex が指摘した 9 件:

| # | 区分 | 指摘 |
|---|---|---|
| 1 | 重大 | argparse の exit 2 が NOT_READY と衝突 |
| 2 | 重大 | 64=未実装 の意味が要件定義に不在 |
| 3 | 重大 | `[project.scripts]` qgb が CLAUDE.md と衝突 |
| 4 | 中 | `__version__` と pyproject.toml の version の二重管理 |
| 5 | 中 | 各 subparser に `set_defaults(handler=...)` を仕込む構造 |
| 6 | 中 | `python -m qgb` の subprocess smoke test がない |
| 7 | 中 | assertion が緩い |
| 8 | 低 | `license = { file = ... }` の PEP 639 警告 |
| 9 | 低 | `importlib.resources` での schemas 読み込み |

### Step 0 補修 (commit `03cabe5`)

重大 3 件 + 中 3 件 (#5, 6, 7) を即時対応:

- `QgbArgumentParser` を導入、`error()` を override して exit 64 に逃がす
- 要件定義書 §6.2.3 に「64 = CLI usage error」を追加 (BSD sysexits EX_USAGE 準拠)
- `[project.scripts]` の `qgb` を削除
- 各 subparser に handler を仕込む構造に変更
- subprocess smoke test を 5 件追加
- assertion を厳格化

持ち越し: #4 (`__version__`), #8 (PEP 639)、#9 (`importlib.resources`)

### 学び

- argparse のデフォルト挙動 (exit 2) が qgb の状態空間 (NOT_READY = 2) と衝突する問題は、外部レビューが無いと気づきにくかった
- 「parser に登録だけしておく」未実装 subcommand 構造はそのまま使えた

## Step 1: JSON Schema 群

### 実装内容 (commit `1db236c`)

- 7 種類の Schema (config / policy / req-meta / contract / gate / gate.runtime / knowledge)
- `qgb/schemas/README.md` で人間向け補足
- `qgb/core/schema.py` で `importlib.resources` 経由のロード API
- `tests/test_schemas.py` 33 件追加

設計判断:
- 採用判定証跡 (gate.schema.json) だけ `additionalProperties: false`
- ALLOW/DENY と failed_stage の整合性は if/then で強制
- exit_code は null 許容
- REQ id は core 互換 (`^REQ-[A-Z0-9]+-[0-9]{3,}$`)
- contract.command は argv 配列限定

### Codex 第 1 回レビュー

14 件の指摘:

| # | 区分 | 指摘 |
|---|---|---|
| 1 | 重大 | gate.schema は status=ALLOW でも stages[].result=failed を許す |
| 2 | 重大 | `format: date-time` が schema.py で検証されない |
| 3 | 重大 | gate.schema の stages[].contract_ref/log_ref/exit_code が必須でない |
| 4 | 重大 | schemas_root() の importlib.resources 対応が半端 |
| 5-8 | 中 | decision.result 不一致テスト不在、contract field 混在の仕様、req-meta schema_version 不在、timestamp_utc regex 緩い |
| 9-11 | テスト | failure fixture が「狙い撃ち」してない、nested strict 未検証、contract negative が command のみ |
| 12-14 | API | ValidationIssue.path が RFC 6901 でない、エラー順不安定、cache なし |

### Step 1 補修 (commit `4b04d94`)

重大 4 件、中 3 件、テスト 3 件、API 2 件を反映:

- gate.schema.json の if/then を強化 (ALLOW で全 stages passed、DENY で 1 件以上 failed、decision.result と status 同値)
- gate.schema.json の stages[] に contract_ref / log_ref / exit_code 必須化
- `schema.py` で `format_checker` を有効化、stdlib (re + datetime) ベースの RFC3339 checker を自前で追加登録
- `load_schema()` を `Traversable.open()` ベースに書き換え
- `ValidationIssue.path` を RFC 6901 準拠に
- `validate()` の結果を `(path, schema_path, message)` で sort
- req-meta.schema.json に schema_version をオプショナル追加

### 戻りループ: Codex 再レビュー

ここで「Step 0/1 でそれぞれの Codex 指摘を満たす修正が完了しているか」を確認する再レビューを実施。

Codex 再レビューの追加指摘 (4 件):

| # | 指摘 |
|---|---|
| A | JSON Pointer escape テストが空振り (実際には `/policy_id` だけ確認していて escape を実証していない) |
| B | `schemas_root()` の説明とコード不一致 (削除済みなのに「残している」と書いた) |
| C | gate.runtime.schema.json に意味論整合性が無い (curated にだけ if/then 入れた) |
| D | contract field 混在の Step 6 持ち越し方針 (warning) は弱い、error にすべき |

### Step 0/1 補修第 2 弾 (commit `eda424f`)

すべて対応:

- JSON Pointer テストを `/` や `~` を含むキーで実証する形に書き換え
- `schemas_root()` を Traversable 返却で復活
- gate.runtime.schema.json にも意味論整合性 (ALLOW/DENY と stages[].result の整合) を追加
- 要件定義書 §F-005 に「contract field 混在は qgb validate 系で error として扱う」を明文化
- `__version__` を `importlib.metadata.version()` に移行 (持ち越し # 4)
- timestamp_utc の regex を厳密化 (パラメトリックテスト 8 ケース)
- EXIT_USAGE のコメントを「Phase 1 transitional」と明示
- date-time checker のコメントを「qgb が必要とする RFC3339 shape」に弱化

### 学び (Step 1)

- 「補修した」と思っても、**テスト自体が空振り**しているケースがある (JSON Pointer の件)。assertion が実証しているかを再確認する規律が必要
- 揮発側スキーマと採用側スキーマで「意味論整合性は同じ、フィールド許容性だけが違う」という設計が筋良かった
- 「Step N で対応」と持ち越したものは、本当に Step N で対応するか、もっと早く潰せるか毎回見直す

## Step 2: qgb validate

### 実装内容 (commit `805d549`)

- `qgb/core/validate.py`: `run_validate(root)` で `.quality-system/` ツリーを走査検証
- `qgb/cli.py` に `validate` subcommand 接続 (`--path`, `--json`)
- 4 種類の fixture (`valid` / `schema_violation` / `field_mismatch` / `invalid_json`)
- subprocess テストに UTF-8 強制 (`PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`) を導入

Step 1 持ち越し # 6 (contract field 混在検出) も Step 2 で前倒し対応 (要件定義書 §F-005 明文化済みなので validate に組み込むのが自然と判断)。

### Codex 第 1 回レビュー

13 件の指摘。**特に重大 3 件**:

| # | 指摘 |
|---|---|
| 1 | `--path` がファイルでも通る |
| 2 | 必須ファイル欠落・参照整合性を一切検出しない |
| 3 | contract field 混在判定が「全 extra field 拒否」になっており、`additionalProperties: true` の拡張性方針と矛盾 |

Codex は「現実のユーザーが期待する qgb validate は『正本ツリーとして成立しているか』まで」と述べ、**integrity check の `qgb validate` への統合 ((2) 案)** を推奨した。

### Step 2 補修第 2 弾 (commit `dccdf4a`) ← 後に巻き戻し対象

Codex の助言に従って integrity check を統合:

- `IntegrityIssue` クラスを導入: `missing_file`, `misplaced_contract`, `dangling_contract_ref`, `unknown_stage_id`
- contract field 混在を「禁止リスト方式」に再設計 (未知 forward-compatible field 許容、他 type 専有 field だけ拒否)
- `--path` is_dir チェック
- `ReadError` dataclass 化
- JSON 出力に `summary.ok` / `summary.total_problems`
- `--json` の stderr 空テスト
- 新規 fixture 4 種 (`missing_required` / `dangling_ref` / `misplaced_contract` / `forward_compat_field`)

テスト 105 件全成功、ruff 警告ゼロ。

### **転換点: 思想チェック (ユーザー指摘)**

ユーザーから「元々の理念、それに基づく設計方針からぶれる拡張ではないか確認をしてください」との指摘。

要件定義書を再読すると:

- **§6.3.2 判定フロー**: `qgb validate` と「contract_ref 不在 / stage_id 未定義 / DAG / required 空 / manual_check」が **並列に列挙** されている。これらをまとめて実行するのが `qgb run` の preflight。
- **§F-009**: 「REQ メタの stage_id が policy に存在」「contract_ref の指す contract が存在」は `qgb validate-policy` の検査項目として明示。
- **stage-design.md §11**: 同様に `validate-policy` の責務として書かれており、思想 P7 / P9 / P6 と紐づけ。
- **§12 受け入れ条件**: 条件 6 (qgb validate) と条件 7 (qgb validate-policy) が別物として並ぶ。

つまり Step 2 補修第 2 弾の判断は **思想憲章 P9 (単一責任原則) と要件定義書の責務分離に違反** していた。Codex の助言は「ユーザーの素朴な期待」を優先しており、本プロジェクトの上位仕様を見落としていた。

### Codex 再レビュー (思想憲章を共有して)

思想憲章と要件定義書の責務分離をコンテキストに含めて Codex に再レビュー依頼。

Codex の自己訂正:

> **Claude の「巻き戻すべき」に賛成です。前回の私の統合推奨は、このプロジェクトの仕様体系に照らすと誤りです。**
> 「一般的な CLI 利用者が `validate` に期待しそうなこと」を優先して、すでに文書化されている qgb の責務分離を崩していました。これは設計レビューとして筋が悪いです。

- 思想 P9 と衝突
- §6.3.2 / §F-009 / §12 と非整合
- stage-design.md §11 の明示的責務を validate に横取り
- 「壊れた .quality-system を OK と言う」問題は qgb 文脈では過剰指摘 (preflight / validate-policy で検出されるため)
- 巻き戻し採用条件: validate の仕様を「存在する JSON ファイルのスキーマ検証」と明文化、missing_file は validate-policy / run preflight で必ず検出
- 共有モジュール名は `integrity` ではなく `policy_checks` / `preflight_checks` が良い

#### Codex への追い質問 (missing_file の議論余地)

「missing_file は議論余地あり」として保留した点について再質問:

- Claude の意見: missing_file も validate から削除推奨 (6 理由を提示)
- Codex 結論: **概ね妥当**。ただし採用条件 4 つ (validate 仕様明文化、validate-policy で必須検出、run preflight で必須検出、ユーザー案内) を満たすこと

Claude の理由のうち「init があるから想定されにくい」「上級者なら認識している」は弱い論法と指摘された (CLI 設計の根拠としてはユーザー行動を楽観視しすぎ)。本当に強い根拠は **P9 と §6.3.2 の責務分離** であり、missing_file は「正本ツリー readiness / integrity の問題」として扱うべき。

### Step 2 巻き戻し (commit `6222035`)

巻き戻した内容:

- `IntegrityIssue` クラスと `_check_integrity` 関数を削除
- `_iter_misplaced_contracts` 関数を削除
- `contracts` 走査を direct child のみに戻す
- `ValidateReport.integrity_issues` を削除
- 関連 fixture 3 種を削除 (Step 6 で復活予定)
- 関連テスト 5 件を削除

残した修正 (Step 2 補修第 2 弾で正しかった部分):

- `--path` is_dir チェック
- contract field 混在の禁止リスト方式 (forward-compatible 許容)
- `FieldMismatch.owning_verification_type`
- `ReadError` dataclass 化
- JSON 出力の `summary.ok` / `summary.total_problems`
- `--json` の stderr 空テスト
- `forward_compat_field` fixture

仕様明文化:

- 要件定義書 §F-009: validate-policy の検査項目に必須ファイル存在 / canonical layout を追加、validate との責務分離を P9 で根拠付け
- stage-design.md §11: 同様の追加
- CLAUDE.md: Per-command single responsibility (P9) セクションを新設、巻き戻し経緯を将来セッション向けに記録

副次修正:

- `validate --help` の description と docstring から em-dash (U+2014) を除去 (Windows CP932 ターミナルで UnicodeEncodeError を起こしていた)

テスト 99 件全成功、ruff 警告ゼロ。

### 学び (Step 2)

- **外部レビュー (Codex) が常に正しいわけではない**。Codex は「ユーザーの素朴な期待」を優先するバイアスがあり、プロジェクト固有の設計方針より一般的な慣習を優先することがある
- **「思想と設計方針を共有して再レビュー」** すると、外部レビュアー自身が前回助言を訂正することがある。これは強力なパターン
- **責務越境は「便利だから」では正当化できない**。思想 P9 (単一責任) を守るために、機能を増やす方向ではなく減らす方向の判断が必要なときがある
- **CLI の出力に非 ASCII 文字を入れない**。Windows コンソールの CP932 では即座に UnicodeEncodeError になる。これは subprocess test の UTF-8 強制とは別系統の問題
- **巻き戻しは恥ではない**。誤った方向に進んだと気づいた時点で巻き戻し、その経緯を文書に残すほうが、誤った設計を温存するより遥かに良い

## 振り返り: 各 Step での反復パターン

```
[実装]
  ↓
[テスト + ruff で確認]
  ↓
[git commit] (Step N の本体実装)
  ↓
[ユーザーが Codex レビュー依頼]
  ↓
[Codex から指摘リスト]
  ↓
[Claude が指摘を分類] (重大/中/低、対応/持ち越し)
  ↓
[補修コミット] (Step N 補修)
  ↓ 場合により
[ユーザーが「思想と整合しているか」を問う]
  ↓
[再レビューまたは思想チェック]
  ↓ 場合により
[巻き戻し or 第 2 弾補修]
  ↓
[Issue 更新、トラッキング Issue にチェック]
  ↓
[次の Step へ]
```

この反復で得られたメタ知見:

1. **Codex 指摘の重要度を Claude 側で再判定する**。Codex が「重大」と言っても本プロジェクトの方針から見ると低優先度のこともあるし、逆に「低」と言ったものが思想に直結することもある
2. **「Step N で対応」「Step N+M で対応」「保留」を明示する**。持ち越しを曖昧にしない。本書のような作業記録に残す
3. **思想憲章を毎回参照する**。要件定義書だけでは曖昧なときも、思想憲章 P1〜P11 のどれに該当するかを問えば判断できる
4. **巻き戻し可能な粒度でコミットする**。1 コミットで複数の関心事を混ぜると、「これだけ巻き戻したい」ができなくなる
5. **外部レビューにはコンテキスト (思想憲章 + 関連スペック) を必ず添える**。これを怠ると「一般論」に流される

## コミット履歴 (Step 0〜2)

```
6222035 Phase 1 Step 2 巻き戻し: qgb validate の責務をスキーマ検証に限定
dccdf4a Phase 1 Step 2 補修: Codex レビュー指摘の修正 (巻き戻し対象)
805d549 Phase 1 Step 2: qgb validate を実装
eda424f Phase 1 Step 0/1 補修第 2 弾: Codex 再レビュー指摘の修正
4b04d94 Phase 1 Step 1 補修: Codex レビュー指摘の修正
1db236c Phase 1 Step 1: JSON Schema 群を追加
03cabe5 Phase 1 Step 0 補修: Codex レビュー指摘の修正
0e5794c Phase 1 Step 0: プロジェクト基盤を追加
c29825e .gitignore を追加 (Python / venv / build / cache / qgb skill dist)
61f8728 要件定義書を v0.3 へ全面改訂、関連文書 3 本を分離
```

## 関連 Issue

- [#14](https://github.com/Yumeno/Quality-gate-builder/issues/14) Phase 1 MVP 実装トラッキング
- [#15](https://github.com/Yumeno/Quality-gate-builder/issues/15) Step 0: プロジェクト基盤 (closed)
- [#16](https://github.com/Yumeno/Quality-gate-builder/issues/16) Step 1: JSON Schema 群 (closed)
- [#17](https://github.com/Yumeno/Quality-gate-builder/issues/17) Step 2: qgb validate (closed)
- [#21](https://github.com/Yumeno/Quality-gate-builder/issues/21) Step 6: 残りコマンド群 (Step 6 で IntegrityIssue 復活)

## 次のステップ

#18 Step 3: `qgb init` 最小実装に進む。
