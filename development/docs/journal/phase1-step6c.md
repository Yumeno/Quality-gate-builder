# Phase 1 Step 6c — qgb detect / adapters/python / adapters/generic 作業記録

着手: 2026-05-31
完結: 2026-05-31 (本体 1 コミット + 補修なし、Codex 横断レビュー指摘は本体に含めて反映)

## Step 6c のスコープ

detailed-design.md §12.6c より:

- adapters/python, adapters/generic の 2 種で起動
- adapter base 規約 (detect() の返り値型を含む)
- DetectedProjectProfile 的なデータ境界を固定: language / framework / test_runner / confidence / evidence[]
- 重要 (P9 維持): validate-policy は「採用済み policy が妥当か」、detect は「候補 stage を提案する材料」を返す

要件 §6.2.1 で qgb detect は Phase 1 必須コマンド。

## 着手前: Codex 計画レビュー

Step 6 のサブステップ慣例 (Step 6a の前と同じ) で、着手前に Codex に計画レビューを取った。6 観点の相談点をぶつけ、構造変更を 3 件もらった:

1. **`run_detect()` の返り値を単一 profile でなく `DetectionResult(selected, candidates)` に変える** — Step 6d 接続性のため
2. **JSON を flat でなく `selected`/`candidates` 形にする** — schema 拡張性のため
3. **generic fallback の理由付けは `GenericAdapter` でなく `core.detect` に置く** — adapter 責務分割の純度のため

これらを着手前に取り込んだ上で本体実装に入った。

## 実装の流れ (4 項目 + Codex 横断レビュー)

### 項目 1: adapter base 規約 + DetectedProjectProfile

`qgb/adapters/base.py` に以下を定義:

```python
@dataclass(frozen=True)
class DetectionEvidence:
    kind: str
    where: str       # project-root 相対パス or 論理位置
    note: str = ""

@dataclass(frozen=True)
class DetectedProjectProfile:
    language: str
    framework: str | None
    test_runner: str | None
    confidence: float    # heuristic ranking score (not probability)
    evidence: list[DetectionEvidence] = []
    adapter_name: str = ""

@dataclass(frozen=True)
class DetectionResult:
    selected: DetectedProjectProfile
    candidates: list[DetectedProjectProfile] = []

class BaseAdapter:
    name: str = ""
    def detect(self, project_root: Path) -> DetectedProjectProfile | None: ...
```

docstring に Phase 1 out-of-scope を明記:
- adapters はコマンドを実行しない
- lockfile / dependency resolver を見ない
- monorepo subproject を扱わない
- shebang を読まない
- multiple framework / test_runner を出さない
- evidence.where は project-root 相対 (絶対パスを漏らさない)

テスト 12 件。

### 項目 2: adapters/generic フォールバック

`qgb/adapters/generic.py`:

- `language="generic"`, `framework=None`, `test_runner=None`, `confidence=0.1` を常に返す
- 探索除外: `.venv` / `venv` / `node_modules` / `.git` / `dist` / `build` / `.tox` / `.mypy_cache` / `.pytest_cache` / `.ruff_cache` / `__pycache__` / `.idea` / `.vscode`
- evidence: `dir_readable` / `dir_empty` / `dir_unreadable` / `dir_missing` / `entry_observed`
- 「fallback として選ばれた理由」は GenericAdapter は知らない (Codex 計画指摘 3)

テスト 7 件。

### 項目 3: adapters/python 検出

`qgb/adapters/python.py`:

マーカーファイル:
- `pyproject.toml` / `setup.py` / `setup.cfg` / `requirements*.txt` (glob)

framework (順序付き、最初のヒットが勝つ):
- fastapi → django → flask

test_runner:
- pyproject に pytest dep
- `[tool.pytest.*]` セクション
- `tests/` + `test_*.py` 2 件以上 (規約推定)

ロード方針:
- Python 3.11+ では `tomllib` で構造化 parse
- Python 3.10 では正規表現 grep フォールバック (依存追加なし)

confidence ランキング:
| 条件 | confidence |
|---|---|
| pyproject + framework + test_runner | 0.9 |
| pyproject + (framework or runner) | 0.75 |
| any marker のみ | 0.6 |
| loose .py が 5 個以上 | 0.4 |
| loose .py が 2〜4 個 | 0.3 |

`detect()` の入口で `is_dir()` 判定、`_scan()` で OSError 吸収 (補修 2 で追加)。

テスト 23 件 (空 / 純 Node / 各マーカー / 各 framework / 各 runner / confidence 範囲 / excluded dirs / realistic mini-project)。

### 項目 4: qgb detect CLI + core/detect.py

`qgb/core/detect.py`:

```python
def run_detect(
    project_root: Path,
    adapters: list[BaseAdapter] | None = None,
) -> DetectionResult:
    if adapters is None:                    # 補修 4: [] を default に化けさせない
        adapters = _default_adapters()
    ...
    for adapter in adapters:
        profile = adapter.detect(project_root)
        if profile is None: continue
        if adapter.name == "generic":       # 補修 5: 文字列 control plane
            generic_profile = profile
        else:
            profiles.append(profile)

    if profiles:
        selected = max(profiles, key=lambda p: p.confidence)
        return DetectionResult(selected=selected, candidates=profiles)

    # No language-specific match -> annotate generic fallback in core
    ...
```

`qgb/cli.py`:
- 既存の stub_commands から `detect` を削除、本物のハンドラに接続
- text 出力: `Detected: python / framework=fastapi / test_runner=pytest / confidence=0.90 / adapter=python` + Evidence + Other candidates
- JSON 出力: `{schema_version: 1, ok: true, selected: {...}, candidates: [...]}`
- `--path` 存在チェック / `is_dir()` で EXIT_USAGE (typo 検知)、それ以降は generic 安全網

テスト 11 件 (core composition / CLI text / CLI JSON / --path cwd)。

### Codex 横断レビューと補修

本体実装後、Codex に 6 観点でレビューを依頼。指摘 8 件:

| # | 重要度 | 内容 | 対応 |
|---|---|---|---|
| 1 | 対応 | CLI が EXIT_USAGE で止めるが GenericAdapter/core は "missing でも generic" と言っている矛盾 | base.py docstring で「CLI は usage error で typo 検知、それ以外は generic 安全網」に整理 |
| 2 | 対応 | PythonAdapter._scan() の OSError 未ガードで Generic 到達せず | `try/except OSError → None` を detect() に追加 |
| 3 | 対応 | GenericAdapter が unreadable と empty を誤分類 | `dir_unreadable` evidence を別 kind に分離、`_top_level_visible` は `(entries, readable)` を返す形に |
| 4 | 対応 | `adapters=[]` が `or` で default に化ける | `if adapters is None` に変更 |
| 5 | 対応 | core が `profile.adapter_name == "generic"` で制御判定 (脆い) | `adapter.name == "generic"` に変更 (control plane vs. data plane の分離) |
| 6 | docstring | `[dependency-groups]` / `[tool.uv]` / poetry group などの dependency coverage 不足 | base.py Phase 2 out-of-scope に明記 |
| 7 | 対応 | JSON に `schema_version` が無く Step 6d 接続時に互換性判定不能 | `"schema_version": 1` を JSON トップレベルに追加 |
| 8 | docstring | Windows case-insensitive (`.PY` 等) を仕様化していない | base.py Phase 2 out-of-scope に明記 |

補修テスト 8 件追加:
- `test_qgb_detect_json_has_schema_version` (補修 7)
- `test_run_detect_empty_adapters_list_raises_or_returns_generic` (補修 4)
- `test_qgb_detect_text_on_missing_path` (補修 1)
- `test_qgb_detect_path_to_file_returns_usage` (補修 1 補足)
- `test_python_adapter_oserror_in_scan_returns_none` (補修 2)
- `test_run_detect_falls_back_to_generic_when_specific_adapter_raises` (補修 2 統合)
- `test_generic_distinguishes_unreadable_from_empty` (補修 3)
- `test_qgb_detect_same_confidence_breaks_tie_by_registration_order` (補修 5)

中程度以上の指摘は全て本体コミット内で吸収できたので、Step 6a/6b パターンの「補修コミット」ではなく **本体 1 コミット** で完結。

## コミット履歴 (Step 6c)

```
0a77ca2 Step 6c: qgb detect + adapters/python + adapters/generic
```

## テストと品質指標の推移

| 段階 | テスト件数 | ruff |
|---|---|---|
| Step 6b 完結時 | 266 | clean |
| 項目 1 (base) | 278 | clean |
| 項目 2 (generic) | 285 | clean |
| 項目 3 (python) | 308 | clean |
| 項目 4 (CLI + core) | 319 | clean |
| 補修 (Codex 8 件) | **327** | clean |

## 振り返り

### 1. 計画レビューが効いた

Step 6a の前に始めた「実装前に Codex に計画相談する」パターンが Step 6c でも効いた。具体的には:

- `run_detect()` を単一 profile 返却で書きかけていたところを **着手前に DetectionResult 構造に変更** できた
- JSON も flat → `selected`/`candidates` 形に着手前に変更
- generic adapter の責務範囲を「fallback 理由を adapter 内に書かない」に着手前に絞れた

これらは実装後に Codex から指摘されたら **大きな書き直し** になっていた可能性が高い。計画レビューはコストではなく、後段の手戻りを減らす投資という Step 6 全体の方針が再度実証された。

### 2. 横断レビュー指摘の本体吸収

Step 6a/6b では Codex 横断レビューを受けてから補修コミットを別に切ってきたが、Step 6c は **本体コミット内で吸収** した。判断基準は「補修内容が独立に意味を成すか」「commit log の可読性」。今回は 8 件全てが Step 6c 内の整合性の話なので、別コミットにすると関連性が見えづらくなると判断。

これは memory の review-process 方針 (手戻り削減が目的) と矛盾しない。**コミット分割は粒度の問題、手戻り削減は品質の問題**で、独立。

### 3. Phase 1 出力の安定 schema 化

Codex 補修 7 (`schema_version` 追加) は Step 6d 接続を見据えた **下流互換性** の話。Phase 1 で安定 schema を JSON に固定しておくと、Phase 2 で破壊的変更を入れるときに consumer が気付ける。これは Phase 1 MVP の「実装の純度」ではなく「将来の拡張性」の保険で、出費としては小さい (3 行) のに効果が高い。

### 4. P9 / P3 の本番運用

Step 6c は P9 (単一責任) の最初の真剣勝負だった。core/adapters の分割、validate-policy / detect の責務分離、adapter 内の dependency resolver 排除 — どれも「分離した方が複雑」に見えるが、Phase 2 の plugin 化と Phase 1 MVP の純度を両立するための投資。Codex の補修 5 (`profile.adapter_name` でなく `adapter.name` で control flow) は **control plane と data plane の分離** という具体形でこの原則を強化した。

### 5. Python 3.10 サポートを依存追加なしで保った

`tomllib` は 3.11+ 標準。3.10 でも動かすために `tomli` を追加するか、フォールバックするか迷ったが、CLAUDE.md の「Minimum dependencies, supply-chain-aware」方針に従って **regex grep でのフォールバック** を選んだ。3.10 では framework / runner 検出が若干緩くなる (test の存在は確認、precision は若干下がる) が、3.11+ で構造 parse を取れば実用上問題なし。依存追加の判断軸として「PyPI 1 つを追加するコスト vs. fallback 実装のコスト」という比較は今後の判断にも使える。

## Step 6c で確定したもの (Step 6d 入力)

Step 6d (design-stages / scaffold) の入力として、以下の API が確定:

- `qgb detect --json` 出力 (schema_version=1):
  ```json
  {
    "schema_version": 1,
    "ok": true,
    "selected": {
      "language": "python",
      "framework": "fastapi" | null,
      "test_runner": "pytest" | null,
      "confidence": 0.9,
      "adapter_name": "python",
      "evidence": [{"kind": "...", "where": "...", "note": "..."}, ...]
    },
    "candidates": [...]
  }
  ```
- `run_detect(project_root)` を Step 6d は内部で呼んで `DetectionResult` を取得できる
- adapter / framework / test_runner の取りうる値は base.py 参照、Step 6d でこれらを stage 命名に使う

## 次のステップ (Step 6d)

design-stages 提案フェーズ + 採用フェーズ + scaffold。stage-design.md §10.1 のルールベース推定 + ユーザー確認、policy.json 書き込み + validate-policy 連携、REQ + contract + テスト雛形生成。詳細は Step 6d 着手時に Codex 計画レビューを取って固める (Step 6c と同じパターン)。
