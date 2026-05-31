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
    """spec §8.2 の PowerShell 例 (py -3 / qgb 主要コマンド) を含む."""
    text = (REPO_ROOT / "development" / "docs" / "phase1-manual.md").read_text(
        encoding="utf-8"
    )
    for snippet in (
        "py -3",
        "python -m qgb init",
        "python -m qgb design-stages",
        "python -m qgb scaffold",
        "python -m qgb run",
        # Step 9 統合レビュー S1: spec §8.2 verbatim block の constituents
        "python -m qgb detect",
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
