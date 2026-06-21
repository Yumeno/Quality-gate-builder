"""Step 9 項目 3/4/5 (受け入れ条件 20/21/24): lightweight docs presence tests.

Codex 計画レビュー方針:
- 文書中心の Step なので test は「壊れやすい契約」のみを固定
- ファイルの存在 + 重要キーワードの含有を担保
- 文章量の厳密一致や snapshot test は避ける (保守コストが本旨と釣り合わない)
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---- AC24: skills/source/ structural reservation -----------------------


def test_skills_source_readme_exists() -> None:
    """受け入れ条件 24: skills/source/ ディレクトリ + README を予約."""
    readme = REPO_ROOT / "skills" / "source" / "README.md"
    assert readme.is_file(), "skills/source/README.md must exist (受け入れ条件 24)"


def test_skills_source_readme_mentions_phase5_plan() -> None:
    """README には Phase 5 計画と中間表現の予定構成を含める."""
    text = (REPO_ROOT / "skills" / "source" / "README.md").read_text(
        encoding="utf-8"
    )
    # Phase 5 への送り / 中間表現の主要ファイル / F-019 への参照
    for keyword in (
        "Phase 5",
        "metadata.yaml",
        "body.md",
        "workflow.md",
        "references.md",
        "prompts/",
        "F-019",
        "tools/build_skill.py",
    ):
        assert keyword in text, f"skills/source/README.md missing: {keyword}"


# ---- AC20: 導入マニュアルが存在し 19 章をすべて持つ -------------------


def test_phase1_manual_exists() -> None:
    manual = REPO_ROOT / "development" / "docs" / "phase1-manual.md"
    assert manual.is_file(), "development/docs/phase1-manual.md must exist (受け入れ条件 20)"


def test_phase1_manual_has_all_19_required_chapters() -> None:
    """spec §8.1 で固定された 19 章すべての見出しが含まれる."""
    text = (REPO_ROOT / "development" / "docs" / "phase1-manual.md").read_text(
        encoding="utf-8"
    )
    required_chapters = [
        "概要",
        "前提環境",
        "Python の確認",
        "リポジトリ取得",
        "仮想環境作成",
        "依存関係導入",
        "qgb の実行確認",
        "対象プロジェクトでの初期化",
        "段階設計フェーズの実行",
        "サンプル REQ 生成",
        "quality-gate 実行",
        "gate.json の読み方",
        "summary.md の読み方",
        "NOT_READY になった場合の対応",
        "DENY になった場合の対応",
        "免除（waived）の指定方法",
        "TDD phase の使い方",
        "依存ライブラリ確認手順",
        "トラブルシューティング",
    ]
    for chapter in required_chapters:
        assert chapter in text, f"phase1-manual.md missing chapter: {chapter}"


def test_phase1_manual_includes_windows_powershell_examples() -> None:
    """spec §8.2 の PowerShell 例 (py -3 / qgb 主要コマンド) を含む.

    Phase 3 Step 3.0 (2026-06-21) で `python -m qgb detect` は廃止された
    ため、本テストの必須 snippet からも削除。spec §8.2 verbatim block の
    constituents という旧コメントも、現行 §8.2 が detect 行を含まない形に
    更新されたので不要。
    """
    text = (REPO_ROOT / "development" / "docs" / "phase1-manual.md").read_text(
        encoding="utf-8"
    )
    for snippet in (
        "py -3",
        "python -m qgb init",
        "python -m qgb design-stages",
        "python -m qgb scaffold",
        "python -m qgb run",
        "python -m qgb validate-policy",
        "python -m qgb --help",
        ".\\.venv\\Scripts\\Activate.ps1",
    ):
        assert snippet in text, f"phase1-manual.md missing snippet: {snippet}"


def test_phase1_manual_contains_consolidated_powershell_block() -> None:
    """Step 9 統合レビュー S1 補修: §8.2 通り consolidated PowerShell block.

    spec §8.2 が要求する一連のコマンドが、1 つの code block (sequential
    flow) として含まれていることを担保する。マニュアル内の任意の場所で、
    `py -3 --version` から `python -m qgb run REQ-APP-001` までが同一
    PowerShell code block に含まれている箇所が **少なくとも 1 つ** あれば
    良しとする (各章に散らした個別 block では不十分)。
    """
    text = (REPO_ROOT / "development" / "docs" / "phase1-manual.md").read_text(
        encoding="utf-8"
    )
    # 全ての py -3 --version の出現位置を試す
    pos = 0
    found = False
    while True:
        block_start = text.find("py -3 --version", pos)
        if block_start == -1:
            break
        block_end = text.find("python -m qgb run REQ-APP-001", block_start)
        if block_end == -1:
            break
        between = text[block_start:block_end]
        if "```" not in between:
            found = True
            break
        pos = block_start + 1
    assert found, (
        "py -3 --version から python -m qgb run REQ-APP-001 までが同一 "
        "PowerShell block に含まれている必要がある (Step 9 統合レビュー S1, "
        "spec §8.2)"
    )


def test_phase1_manual_troubleshooting_covers_bom() -> None:
    """Step 9 統合レビュー C1 補修: BOM 注記が troubleshooting に存在."""
    text = (REPO_ROOT / "development" / "docs" / "phase1-manual.md").read_text(
        encoding="utf-8"
    )
    assert "BOM" in text, "phase1-manual.md missing BOM troubleshooting note"


def test_phase1_manual_documents_venv_python_aliasing() -> None:
    """Step 9 統合レビュー W3 補修: venv activate 後の python 注釈."""
    text = (REPO_ROOT / "development" / "docs" / "phase1-manual.md").read_text(
        encoding="utf-8"
    )
    # "venv 内の" のような表現で python の指し先が説明されている
    assert "venv 内" in text or "venv 内の" in text


# ---- AC21: 依存ポリシー + セキュリティ確認手順 -----------------------


def test_security_dependency_policy_exists() -> None:
    policy = (
        REPO_ROOT / "development" / "docs" / "security-dependency-policy.md"
    )
    assert policy.is_file(), (
        "development/docs/security-dependency-policy.md must exist "
        "(受け入れ条件 21)"
    )


def test_security_dependency_policy_covers_required_checklist() -> None:
    """spec §6.6.2 の調査項目に対応するキーワードが含まれる."""
    text = (
        REPO_ROOT / "development" / "docs" / "security-dependency-policy.md"
    ).read_text(encoding="utf-8")
    for keyword in (
        "メンテナンス",
        "脆弱",
        "ライセンス",
        "依存ツリー",
        "postinstall",
        "ネットワーク",
        "バイナリ",
        "PyPI",
        "jsonschema",
        "Phase 1",
        "Phase 2",
    ):
        assert keyword in text, (
            f"security-dependency-policy.md missing keyword: {keyword}"
        )


def test_security_dependency_policy_covers_platform_binary_distinction() -> None:
    """Step 9 統合レビュー W4 補修: .pyd / .so / .dylib の platform 区別."""
    text = (
        REPO_ROOT / "development" / "docs" / "security-dependency-policy.md"
    ).read_text(encoding="utf-8")
    for keyword in (".pyd", ".so", ".dylib", "win_amd64", "manylinux", "macosx"):
        assert keyword in text, (
            f"security-dependency-policy.md missing platform binary keyword: {keyword}"
        )


# ---- Phase 3 Step 3.0 regression: detect / adapters の再混入を早期検出 ----
#
# Codex セカンドオピニオン (2026-06-21) 段 3 指摘: Step 3.0 で detect /
# adapters を撤去したが、派生 docs (CLAUDE.md / phase1-manual.md /
# stage-design.md / requirements_and_development.md / detailed-design.md /
# framework-shape.md / examples/) に再混入する可能性がある。docs grep
# regression test で早期検出する仕組みを置く。
#
# 「使う」言及 (廃止事実の説明や歴史記録) は許容、「現役機能として記述」
# だけを検出するため、許容パターンを exclude_lines で除外する。


def _grep_lines_containing(path: Path, term: str) -> list[tuple[int, str]]:
    """Return (line_no, line) tuples whose text contains ``term``.

    Path may point at a file or a directory; in the directory case, scans
    every regular .md / .json / .py file recursively.
    """
    if path.is_file():
        files = [path]
    else:
        files = sorted(
            p
            for p in path.rglob("*")
            if p.is_file()
            and p.suffix in {".md", ".json", ".py"}
            and ".venv" not in p.parts
            and ".pytest_cache" not in p.parts
            and ".ruff_cache" not in p.parts
            and ".git" not in p.parts
            and "__pycache__" not in p.parts
        )
    hits: list[tuple[int, str]] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if term in line:
                hits.append((line_no, f"{f.relative_to(REPO_ROOT)}:{line_no}: {line.strip()}"))
    return hits


# 廃止記述や履歴記録など「detect / adapter 再混入とみなさない」許容パターン。
# 文字列の部分一致で判定する (lower-case 比較は不要、原文どおり書く)。
_ALLOWED_DETECT_PATTERNS = (
    "廃止",                              # "qgb detect は廃止"
    "撤回",                              # "adapter 量産方針を撤回"
    "撤去",                              # "Phase 3 Step 3.0 で撤去"
    "削除",                              # "qgb detect 削除"
    "Phase 3 Step 3.0",                  # 説明文中の時系列言及
    "ストライクスルー",                  # 受け入れ条件§12 補足
    "~~",                                # markdown strikethrough 表記
    "Withdrawn",                         # CLAUDE.md の英語表現
    "withdrawn",                         # 同上
    "no `qgb/adapters/`",                # CLAUDE.md の表現
    "_detect_cycle",                     # preflight 内の別語: DAG 循環検出
    "detected_at",                       # 別語: 検出時刻
    "Detection",                         # journal の歴史記録
    "DetectionResult",                   # docstring / 歴史言及
    "detect_result",                     # docstring / 歴史言及
    "run_detect",                        # 同上
    "language detection",                # journal / docs での歴史的言及
    "detecting",                         # "detecting such tree-shape problems" のような別語
    "re-detected",                       # validate.py の "byte corruption is re-detected"
    "detect_p =",                        # 旧 detect parser 変数 (もはや存在しないが念のため)
    "_handle_detect",                    # 旧 handler (もはや存在しないが念のため)
)

_ALLOWED_ADAPTER_PATTERNS = (
    "廃止",
    "撤回",
    "撤去",
    "削除",
    "Phase 3 Step 3.0",
    "~~",
    "Withdrawn",
    "withdrawn",
    "no `qgb/adapters/`",
    "qgb/adapters/",                     # 「qgb/adapters/ を廃止」のような言及
    "adapter 抽象",                      # 「adapter 抽象が追いつかない」の説明
    "adapter 層",                        # 「adapter 層を撤去」の説明
    "旧 adapter",                        # 「旧 adapter による」の説明
    "全言語 adapter",                    # §7.5 Phase 1 で扱わないものの言及
    "adapter なし",                      # 「adapter なしで動く」など
    "minimum dependencies",              # 別文脈の用語
    "adapter による",                    # 説明用言及
    "adapter 量産",                      # 「adapter 量産方針」の言及
    "Adapter 層",                        # §6.1.2 タイトル
)


def _is_active_use(line: str, allowed_patterns: tuple[str, ...]) -> bool:
    """True iff the line uses the term as if it were an active feature.

    A line is considered an *active use* unless it matches any allowed
    pattern (廃止 / 撤回 / journal historical record / unrelated synonym
    etc.). The regression test fails when active uses appear so newly-added
    docs or code don't silently resurrect the deprecated abstraction.
    """
    for pat in allowed_patterns:
        if pat in line:
            return False
    return True


# Files we sweep for regression. We exclude:
# - tests/ (this file itself uses the strings)
# - development/docs/journal/ (historical record, all references are by
#   nature historical even when they don't carry an explicit 廃止 marker)
# - examples/*/evidence-reference/ (frozen reference output that mentions
#   adapter names by historical accident)
# - migration-phase1-to-phase2.md (Phase 1→2 当時の真実の記録)
# - requirements_and_development.v0.2.md (履歴保存ファイル)


_REGRESSION_SWEEP_PATHS = (
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "qgb",
    REPO_ROOT / "development" / "docs" / "philosophy.md",
    REPO_ROOT / "development" / "docs" / "requirements_and_development.md",
    REPO_ROOT / "development" / "docs" / "detailed-design.md",
    REPO_ROOT / "development" / "docs" / "framework-shape.md",
    REPO_ROOT / "development" / "docs" / "stage-design.md",
    REPO_ROOT / "development" / "docs" / "phase1-manual.md",
    REPO_ROOT / "development" / "docs" / "security-dependency-policy.md",
)


def test_no_active_qgb_detect_resurrection() -> None:
    """Step 3.0 regression: `qgb detect` の現役記述が docs / コードに混入していない."""
    offenders: list[str] = []
    for sweep_path in _REGRESSION_SWEEP_PATHS:
        if not sweep_path.exists():
            continue
        for _line_no, location in _grep_lines_containing(sweep_path, "qgb detect"):
            if _is_active_use(location, _ALLOWED_DETECT_PATTERNS):
                offenders.append(location)
    assert not offenders, (
        "Phase 3 Step 3.0 で qgb detect は廃止された。現役記述が混入している:\n"
        + "\n".join(offenders)
        + "\n\n再廃止 (撤回 / 廃止 / 撤去 / ~~ で囲む) するか、許容パターンを "
        "tests/test_step9_docs.py の _ALLOWED_DETECT_PATTERNS に追加して回避すること。"
    )


def test_no_active_adapters_directory_resurrection() -> None:
    """Step 3.0 regression: qgb/adapters/ への現役 import / 構造的言及が混入していない."""
    offenders: list[str] = []
    # コード側: qgb/ 配下に from qgb.adapters / import qgb.adapters があれば再混入
    for sweep_path in (REPO_ROOT / "qgb",):
        if not sweep_path.exists():
            continue
        for _line_no, location in _grep_lines_containing(sweep_path, "qgb.adapters"):
            # コメントの言及 (例: 廃止理由を docstring に書いている) は許容
            stripped = location.split(": ", 2)[-1].lstrip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            offenders.append(location)
    assert not offenders, (
        "Phase 3 Step 3.0 で qgb/adapters/ は撤去された。現役 import が混入している:\n"
        + "\n".join(offenders)
        + "\n\nimport を削除するか、対象 module を実際に必要な layer に移すこと。"
    )


def test_no_active_run_detect_resurrection() -> None:
    """Step 3.0 regression: qgb.core.detect.run_detect の現役呼び出しが混入していない."""
    offenders: list[str] = []
    for sweep_path in (REPO_ROOT / "qgb",):
        if not sweep_path.exists():
            continue
        for _line_no, location in _grep_lines_containing(sweep_path, "run_detect"):
            stripped = location.split(": ", 2)[-1].lstrip()
            # コメント / docstring 内の歴史的言及は許容
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            # docstring 中の例示 (例: ":func:`...run_detect`") も許容
            if ":func:" in location or "旧版" in location or "Phase" in location:
                continue
            offenders.append(location)
    assert not offenders, (
        "Phase 3 Step 3.0 で run_detect は撤去された。現役呼び出しが混入している:\n"
        + "\n".join(offenders)
    )


def test_no_active_detection_result_dataclass_resurrection() -> None:
    """Step 3.0 regression: DetectionResult の現役 import / 使用が混入していない."""
    offenders: list[str] = []
    for sweep_path in (REPO_ROOT / "qgb",):
        if not sweep_path.exists():
            continue
        for _line_no, location in _grep_lines_containing(sweep_path, "DetectionResult"):
            stripped = location.split(": ", 2)[-1].lstrip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if ":class:" in location or "旧版" in location or "Phase" in location:
                continue
            offenders.append(location)
    assert not offenders, (
        "Phase 3 Step 3.0 で DetectionResult は撤去された。現役利用が混入している:\n"
        + "\n".join(offenders)
    )
