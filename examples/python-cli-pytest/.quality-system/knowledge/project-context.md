# プロジェクトコンテキスト (記入例: Python CLI + pytest)

これは Phase 3 Step 3.0 で `project-context.md` の **記入例** として作成した
サンプル。実プロジェクトに `qgb init` した直後はもっと簡素な雛形が生成され、
利用者が中身を書いていく。`design-notes.md` のような設計判断の記録とは
別に、本ファイルは「**このプロジェクトは何で何が大切か**」の自己定義を
人間向け自然言語で書く場所として使う。

補佐 Agent (Claude Code / Codex CLI / Gemini CLI 等) は本ファイルを読んで
構造化し、`.quality-system/project-context.json` (機械正本) を生成または
更新する。`json` の `human_reviewed: true` は人間がレビューしてから付ける。

## 目的

このプロジェクトに quality-gate-builder を導入したのは、`demo_cli`
というシンプルな Python CLI ツールに対して、「成果物が要求通りに動く」
ことの証跡を機械的に残す体験を Phase 2 設計例として示すため。実プロダクト
ではなく `qgb` の使い方を学ぶための例。

## 対象範囲

### in scope

- `src/demo_cli/` 配下の Python ソース
- `tests/` 配下の pytest テスト
- CLI の文字列出力 (substring_match 検査の対象)

### out of scope

- パッケージ配布 (PyPI 等)
- パフォーマンスベンチマーク
- 統計的品質指標 (qgb は ALLOW/DENY を出すだけで「コードカバレッジ何%」
  のような数値スコアは出さない、philosophy P11)

## 既知の制約・前提

### 技術スタック (technologies)

- Python 3.10+
- pytest (test_runner)
- 標準ライブラリ中心 (依存追加は qgb の §6.9.2 checklist と同じ規律で
  最小化、NF-010 を対象プロジェクトにも適用)

### 成果物の種類 (artifact_kinds)

- ソースコード (`source-code`)
- テスト (`tests`)
- CLI 起動ラッパー (`cli-entry-point`)

### 対象プラットフォーム

- Windows (NF-004: PowerShell first-class)
- Linux (CI で検証する想定、Phase 3 Step 3.1 で qgb 本体の CI 雛形と同形)

### 採用しないテスト方式

- **snapshot testing**: 出力に環境依存値が混じる場合 (path / 日時)、意味の
  ある diff にならないため
- **property-based testing (hypothesis)**: シンプル CLI には過剰、学習例
  としてのシグナル/ノイズ比が悪い

## Python プロジェクト観察観点 (Phase 1 PythonAdapter の知見を転記)

Phase 3 Step 3.0 で `qgb/adapters/python.py` は撤去されたが、そこで蓄積した
「Python プロジェクトを観察するための観点」は記入例として活きる。スキル
(Phase 5) や補佐 Agent が対象を読むときの参考にしてほしい。

### marker file の信頼度順序

1. `pyproject.toml` (最も強い、PEP 621 標準)
2. `setup.py` / `setup.cfg` (legacy だが現役)
3. `requirements*.txt` (依存管理のみ、build system 情報なし)

### pyproject.toml から読み取れること

- `[project] dependencies` でフレームワーク推定 (fastapi / django / flask 等)
- `[tool.pytest.ini_options]` の存在で pytest 採用が確定
- `[tool.ruff]` / `[tool.mypy]` 等で品質ツール採用が分かる

### test_runner の判定順序

- pyproject に `pytest` 依存 → 確定 pytest
- pyproject に `[tool.pytest...]` セクション → 確定 pytest
- `tests/test_*.py` の存在 → pytest 慣行 (但し unittest discovery でも動く)
- どれもなければ unknown (LLM 側で対象を読んで判断)

### 除外したいディレクトリ

`.git` / `.venv` / `venv` / `node_modules` / `dist` / `build` / `.tox` /
`.mypy_cache` / `.pytest_cache` / `.ruff_cache` / `__pycache__` /
`.idea` / `.vscode`

これらは marker file 探索でも skip するのが慣行。

## 参照文書

- `design-notes.md` — このプロジェクトの段階設計判断の記録 (機械検査の
  対象外、人間の意思決定の歴史)
- `README.md` — プロジェクト全体の説明 (利用者向け)
- (実プロジェクトでは ADR や Issue へのリンクも書く)

## 補佐 Agent への伝達事項

このファイルを読んで `project-context.json` を更新する補佐 Agent への
お願い:

- `human_reviewed: true` は **私 (利用者) が json を読んでレビューを
  終えてから手で書き換える**。あなたは false のまま残してよい
- `source_metadata.source_md_sha256` には本ファイルの SHA-256 を入れて
  ほしい。後で md だけ更新された場合の検出に使う
- `technologies` / `artifact_kinds` / `platform` の語彙は本ファイルから
  抽出して構造化してほしい。新規語彙の創出は控えめに
