"""Step 6b 項目 3: QGB_KEEP_RUNS 不正値の warning.

Codex Step 5 L4 の指摘への対応。現状は QGB_KEEP_RUNS に "abc" / "-5" / "0"
などの不正値を入れても黙って既定値 10 (または 1) に倒すので、設定ミスが
検知できない。仕様化:

* 非整数 (parse 失敗) → 既定値 10、stderr に warning
* 0 以下の整数 → 既定値 10、stderr に warning
* 1 以上の整数 → 採用 (warning なし)
* 未設定 / 空文字 → 既定値 10、warning なし

warning メッセージには「採用された値」と「無視された raw 値」の両方を含めて、
利用者が気付けるようにする。
"""

from __future__ import annotations

import pytest

from qgb.core.evidence import _DEFAULT_KEEP_RUNS, _resolve_keep_runs


def test_unset_uses_default_without_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("QGB_KEEP_RUNS", raising=False)
    assert _resolve_keep_runs(None) == _DEFAULT_KEEP_RUNS
    assert capsys.readouterr().err == ""


def test_empty_uses_default_without_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("QGB_KEEP_RUNS", "")
    assert _resolve_keep_runs(None) == _DEFAULT_KEEP_RUNS
    assert capsys.readouterr().err == ""


def test_valid_positive_int_is_used(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("QGB_KEEP_RUNS", "5")
    assert _resolve_keep_runs(None) == 5
    assert capsys.readouterr().err == ""


def test_non_integer_warns_and_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("QGB_KEEP_RUNS", "abc")
    assert _resolve_keep_runs(None) == _DEFAULT_KEEP_RUNS
    err = capsys.readouterr().err
    assert "QGB_KEEP_RUNS" in err
    assert "abc" in err
    assert str(_DEFAULT_KEEP_RUNS) in err


def test_negative_warns_and_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("QGB_KEEP_RUNS", "-5")
    assert _resolve_keep_runs(None) == _DEFAULT_KEEP_RUNS
    err = capsys.readouterr().err
    assert "QGB_KEEP_RUNS" in err
    assert "-5" in err


def test_zero_warns_and_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """0 は「全削除」を意図したい人もいるが、Phase 1 は最低 1 個残す方針。

    元々の max(1, value) で黙って 1 にしていたが、これは意図と挙動の乖離が
    最大の入力なので明示的に warning を出して既定値 10 にフォールバック。
    """
    monkeypatch.setenv("QGB_KEEP_RUNS", "0")
    assert _resolve_keep_runs(None) == _DEFAULT_KEEP_RUNS
    err = capsys.readouterr().err
    assert "QGB_KEEP_RUNS" in err
    assert "0" in err


def test_explicit_argument_bypasses_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``keep_runs`` 引数 (主にテスト経路) は env を無視し warning も出さない."""
    monkeypatch.setenv("QGB_KEEP_RUNS", "abc")
    assert _resolve_keep_runs(3) == 3
    assert capsys.readouterr().err == ""


def test_whitespace_only_warns(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """空文字は warning なし既定だが、空白だけの場合は不正値扱い."""
    monkeypatch.setenv("QGB_KEEP_RUNS", "   ")
    assert _resolve_keep_runs(None) == _DEFAULT_KEEP_RUNS
    err = capsys.readouterr().err
    assert "QGB_KEEP_RUNS" in err


def test_padded_integer_is_accepted_without_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Codex 補修 (低): " 5 " など前後空白付きの整数は strip 後に受け付ける."""
    monkeypatch.setenv("QGB_KEEP_RUNS", " 5 ")
    assert _resolve_keep_runs(None) == 5
    assert capsys.readouterr().err == ""
