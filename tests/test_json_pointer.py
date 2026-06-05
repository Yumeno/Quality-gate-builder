"""Tests for qgb.core.json_pointer (Phase 2 Step 2.2 prejournal §6.2).

JSON Pointer (RFC 6901) の encode / decode / parse_array_index の境界仕様を
ロックする。Step 2.2 の patch substrate / Step 2.5 Pattern B が前提とする
セマンティクスを spec lock する目的。
"""

from __future__ import annotations

import pytest

from qgb.core.json_pointer import (
    ARRAY_APPEND_TOKEN,
    PointerError,
    decode,
    encode,
    parse_array_index,
)

# ---- encode --------------------------------------------------------------


class TestEncode:
    def test_empty_tokens_is_root_pointer(self) -> None:
        assert encode([]) == ""

    def test_single_string_token(self) -> None:
        assert encode(["foo"]) == "/foo"

    def test_multiple_string_tokens(self) -> None:
        assert encode(["stages", "S1"]) == "/stages/S1"

    def test_int_token_is_stringified(self) -> None:
        assert encode(["stages", 0]) == "/stages/0"

    def test_token_with_slash_escapes_to_tilde_one(self) -> None:
        assert encode(["a/b"]) == "/a~1b"

    def test_token_with_tilde_escapes_to_tilde_zero(self) -> None:
        assert encode(["a~b"]) == "/a~0b"

    def test_token_with_both_escapes_in_correct_order(self) -> None:
        # ``~`` must be escaped BEFORE ``/``.
        assert encode(["a~/b"]) == "/a~0~1b"

    def test_token_with_tilde_one_string_does_not_double_escape(self) -> None:
        # Input ``~1`` should encode to ``~01``, not ``~/`` then re-escape.
        assert encode(["~1"]) == "/~01"


# ---- decode --------------------------------------------------------------


class TestDecode:
    def test_empty_pointer_is_root(self) -> None:
        assert decode("") == []

    def test_single_token(self) -> None:
        assert decode("/foo") == ["foo"]

    def test_multiple_tokens(self) -> None:
        assert decode("/stages/S1") == ["stages", "S1"]

    def test_array_index_token_is_string(self) -> None:
        # decode() returns str only; index conversion is caller's job.
        assert decode("/stages/0") == ["stages", "0"]

    def test_tilde_one_decodes_to_slash(self) -> None:
        assert decode("/a~1b") == ["a/b"]

    def test_tilde_zero_decodes_to_tilde(self) -> None:
        assert decode("/a~0b") == ["a~b"]

    def test_combined_escape_decodes_in_correct_order(self) -> None:
        # ``~0~1`` → ``~/``, NOT ``~1`` decoded first as ``/`` then ``~0``.
        assert decode("/a~0~1b") == ["a~/b"]

    def test_tilde_zero_one_string_decodes_to_tilde_one(self) -> None:
        # Inverse of the encode test: ``/~01`` decodes back to ``"~1"``.
        assert decode("/~01") == ["~1"]

    # Empty inner tokens are valid per RFC 6901 §3 (multiple consecutive
    # ``/`` yield empty string tokens).
    def test_empty_inner_tokens_allowed(self) -> None:
        assert decode("/foo//bar") == ["foo", "", "bar"]

    def test_trailing_slash_yields_empty_token(self) -> None:
        assert decode("/foo/") == ["foo", ""]

    # Invalid pointer shapes.

    def test_not_a_pointer_raises(self) -> None:
        with pytest.raises(PointerError) as exc_info:
            decode("foo")
        assert exc_info.value.reason == "not_a_pointer"

    def test_unterminated_escape_raises(self) -> None:
        with pytest.raises(PointerError) as exc_info:
            decode("/foo~")
        assert exc_info.value.reason == "unterminated_escape"

    def test_invalid_escape_raises(self) -> None:
        with pytest.raises(PointerError) as exc_info:
            decode("/foo~2")
        assert exc_info.value.reason == "invalid_escape"

    def test_invalid_escape_with_letter_raises(self) -> None:
        with pytest.raises(PointerError) as exc_info:
            decode("/foo~x")
        assert exc_info.value.reason == "invalid_escape"


# ---- encode/decode round-trip -------------------------------------------


class TestRoundTrip:
    @pytest.mark.parametrize(
        "tokens",
        [
            [],
            ["foo"],
            ["stages", "S1"],
            ["a/b"],
            ["a~b"],
            ["a~/b"],
            ["~1"],
            ["", "foo"],
            ["foo", ""],
        ],
    )
    def test_encode_then_decode_preserves(self, tokens: list[str]) -> None:
        assert decode(encode(tokens)) == tokens

    @pytest.mark.parametrize(
        "pointer",
        ["", "/foo", "/stages/S1", "/a~1b", "/a~0b", "/a~0~1b", "/~01"],
    )
    def test_decode_then_encode_preserves(self, pointer: str) -> None:
        assert encode(decode(pointer)) == pointer


# ---- parse_array_index ---------------------------------------------------


class TestParseArrayIndex:
    def test_zero_is_valid(self) -> None:
        assert parse_array_index("0") == 0

    def test_positive_integer(self) -> None:
        assert parse_array_index("123") == 123

    def test_leading_zero_rejected(self) -> None:
        with pytest.raises(PointerError) as exc_info:
            parse_array_index("01")
        assert exc_info.value.reason == "invalid_array_index"

    def test_double_leading_zero_rejected(self) -> None:
        with pytest.raises(PointerError) as exc_info:
            parse_array_index("00")
        assert exc_info.value.reason == "invalid_array_index"

    def test_negative_rejected(self) -> None:
        with pytest.raises(PointerError) as exc_info:
            parse_array_index("-1")
        assert exc_info.value.reason == "invalid_array_index"

    def test_non_numeric_rejected(self) -> None:
        with pytest.raises(PointerError) as exc_info:
            parse_array_index("abc")
        assert exc_info.value.reason == "invalid_array_index"

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(PointerError) as exc_info:
            parse_array_index("")
        assert exc_info.value.reason == "invalid_array_index"

    def test_append_token_without_flag_rejected(self) -> None:
        with pytest.raises(PointerError) as exc_info:
            parse_array_index(ARRAY_APPEND_TOKEN)
        assert exc_info.value.reason == "invalid_array_index"

    def test_append_token_with_flag_returns_dash(self) -> None:
        assert parse_array_index(ARRAY_APPEND_TOKEN, allow_append=True) == "-"

    def test_positive_with_append_allowed_still_parses_int(self) -> None:
        # Numeric indices are unaffected by allow_append=True.
        assert parse_array_index("5", allow_append=True) == 5

    # Step 2.2 補修 A1 (Codex / subagent edge-cases 高 反映): RFC 6901 §4
    # は ASCII digits only を要求するので、Unicode の数字カテゴリ (Arabic-
    # Indic 数字、全角数字、上付き数字など) は invalid。

    def test_full_width_digit_rejected(self) -> None:
        """全角数字 ``１`` は ``str.isdigit()`` で True だが ASCII でないので reject."""
        with pytest.raises(PointerError) as exc_info:
            parse_array_index("１")  # "１"
        assert exc_info.value.reason == "invalid_array_index"

    def test_arabic_indic_digit_rejected(self) -> None:
        """Arabic-Indic 数字 ``٠`` も同じ理由で reject."""
        with pytest.raises(PointerError) as exc_info:
            parse_array_index("٠")  # "٠"
        assert exc_info.value.reason == "invalid_array_index"

    def test_superscript_digit_rejected(self) -> None:
        """上付き数字 ``²`` も str.isdigit() で True だが ASCII でない."""
        with pytest.raises(PointerError) as exc_info:
            parse_array_index("²")  # "²"
        assert exc_info.value.reason == "invalid_array_index"

    def test_mixed_ascii_and_unicode_rejected(self) -> None:
        """ASCII と Unicode 数字の混在も reject."""
        with pytest.raises(PointerError) as exc_info:
            parse_array_index("1１")  # "1１"
        assert exc_info.value.reason == "invalid_array_index"
