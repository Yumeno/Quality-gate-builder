"""JSON Pointer (RFC 6901) encode / decode for qgb.

Phase 2 Step 2.2 で新設 (Codex 計画レビュー指摘 13、P9 集約)。
Step 2.1 まで :mod:`qgb.core.schema` に `_json_pointer_escape` / `_to_pointer`
として埋め込まれていた encode 経路をここに集約し、Step 2.2 で必要になる
decode 経路 (`#/...` 形式の pointer を token 列に分解) を追加する。

設計境界 (RFC 6901 + Step 2.2 Codex 計画レビュー指摘 1/2 反映):

* **encode**: token 列 → pointer 文字列。各 token に対し ``~`` → ``~0``、
  ``/`` → ``~1`` を順序通り適用 (順序を逆にすると ``/`` を含む token が
  誤って escape される)。空 token 列は ``""``。
* **decode**: pointer 文字列 → token 列。先頭 ``/`` で split し、各 token に
  対し ``~1`` → ``/``、``~0`` → ``~`` を **順序通り** 適用 (こちらも順序を
  逆にすると ``~01`` のような正当 escape が壊れる)。空文字列 ``""`` は
  root pointer で empty token 列を返す。
* **invalid escape は :class:`PointerError` で reject**:
    - pointer が ``""`` または ``/...`` 以外
    - token 内の ``~`` の後続が ``0`` / ``1`` 以外
    - token 内の末尾 ``~`` (escape 未完了)

decode 戻り値は ``list[str]`` のみ。array index への変換は呼び出し側
(patch.py) の責務 — JSON Pointer 仕様上 token は単なる文字列で、
「これは配列 index」「これは object key」かは context 依存だから。
ただし patch.py の便宜のため :func:`parse_array_index` ヘルパも提供する。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "PointerError",
    "encode",
    "decode",
    "parse_array_index",
    "ARRAY_APPEND_TOKEN",
]


# RFC 6901 で配列末尾追加を表す特別な token (patch.py の add op で使う)。
ARRAY_APPEND_TOKEN = "-"


@dataclass(frozen=True)
class PointerError(ValueError):
    """Raised when a JSON Pointer string is malformed.

    ``reason`` は機械可読な分類で、Step 2.5 (Pattern B) の proposal/adopt 経路
    でも安定判定に使えるよう設計。

    reason 一覧:

    * ``"not_a_pointer"`` — 先頭が ``/`` でない (空文字列でもない)
    * ``"unterminated_escape"`` — token の末尾が ``~`` で終わっている
    * ``"invalid_escape"`` — ``~`` の後続が ``0`` / ``1`` 以外
    * ``"non_string_token"`` — encode 入力に非文字列化不能な値が含まれる
    """

    pointer: str
    reason: str
    message: str

    def __str__(self) -> str:
        return f"{self.message} (pointer={self.pointer!r}, reason={self.reason})"


def _escape_token(token: object) -> str:
    """Escape a single JSON Pointer reference token per RFC 6901 §4."""
    s = str(token)
    # Order matters: ``~`` must be escaped to ``~0`` BEFORE ``/`` becomes
    # ``~1``, otherwise ``~`` introduced by ``/`` substitution would be
    # double-escaped on the next pass.
    return s.replace("~", "~0").replace("/", "~1")


def encode(tokens: Iterable[object]) -> str:
    """Encode a sequence of tokens into a JSON Pointer (RFC 6901).

    * Empty input → ``""`` (root pointer).
    * Each token is stringified via ``str()`` and escaped per
      :func:`_escape_token`.
    * Returned pointer always starts with ``/`` unless empty.

    例::

        encode([])           == ""
        encode(["foo"])      == "/foo"
        encode(["a/b"])      == "/a~1b"
        encode(["a~b"])      == "/a~0b"
        encode(["a~/b"])     == "/a~0~1b"
        encode(["stages", 0]) == "/stages/0"
    """
    token_list = list(tokens)
    if not token_list:
        return ""
    return "/" + "/".join(_escape_token(t) for t in token_list)


def decode(pointer: str) -> list[str]:
    """Decode a JSON Pointer string into a list of reference tokens.

    Step 2.2 Codex 計画レビュー指摘 1/2 反映:

    * pointer が ``""`` (root) → 空 list
    * pointer が ``/...`` 以外 → :class:`PointerError`
      (``reason="not_a_pointer"``)
    * token 内の ``~`` の後続が ``0`` / ``1`` 以外 →
      :class:`PointerError` (``reason="invalid_escape"``)
    * token の末尾が ``~`` → :class:`PointerError`
      (``reason="unterminated_escape"``)

    array index への変換は呼び出し側責務 (:func:`parse_array_index` 参照)。
    各 token はあくまで文字列として返す。

    例::

        decode("")           == []
        decode("/foo")       == ["foo"]
        decode("/a~1b")      == ["a/b"]
        decode("/a~0b")      == ["a~b"]
        decode("/a~0~1b")    == ["a~/b"]
        decode("/stages/0")  == ["stages", "0"]   # str のまま
        decode("/foo~")      → PointerError "unterminated_escape"
        decode("/foo~2")     → PointerError "invalid_escape"
        decode("foo")        → PointerError "not_a_pointer"
    """
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PointerError(
            pointer=pointer,
            reason="not_a_pointer",
            message="JSON Pointer must be empty or start with '/'",
        )
    # Split on '/' but skip the leading empty element from the initial '/'.
    raw_tokens = pointer.split("/")[1:]
    decoded: list[str] = []
    for raw in raw_tokens:
        decoded.append(_unescape_token(raw, pointer))
    return decoded


def _unescape_token(raw: str, pointer: str) -> str:
    """Unescape a single token from a JSON Pointer.

    RFC 6901 §4 ではエスケープは ``~0`` → ``~`` と ``~1`` → ``/`` の 2 つの
    シーケンスのみ許される。``~`` 単独 (``~`` の後続が無い、または ``~`` の
    後続が ``0`` / ``1`` 以外) は invalid。

    Phase 2 Step 2.2 補修 A6 (Codex / subagent correctness 低反映):
    実装は **逐次走査** (sequential scan)。``~`` を見つけるたびに次文字を
    確認し、``0`` なら ``~`` / ``1`` なら ``/`` に置換、それ以外なら
    :class:`PointerError`。逐次走査なので「先に ``~1`` を処理してから ``~0``」
    のような順序問題は発生しない (``~01`` は ``~0`` → ``~`` の後、残りの
    ``1`` がリテラル文字として扱われ ``~1`` という結果になる)。
    encode 側 (:func:`_escape_token`) の ``replace()`` チェーンとは仕組みが
    異なる点に注意 (あちらは順序が重要)。
    """
    out_chars: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c != "~":
            out_chars.append(c)
            i += 1
            continue
        # We are at a '~'. The next character determines the escape.
        if i + 1 >= n:
            raise PointerError(
                pointer=pointer,
                reason="unterminated_escape",
                message=f"token ends with '~' without escape sequence: {raw!r}",
            )
        nxt = raw[i + 1]
        if nxt == "0":
            out_chars.append("~")
            i += 2
        elif nxt == "1":
            out_chars.append("/")
            i += 2
        else:
            raise PointerError(
                pointer=pointer,
                reason="invalid_escape",
                message=(
                    f"invalid escape '~{nxt}' in token: {raw!r} "
                    "(only ~0 → '~' and ~1 → '/' are valid)"
                ),
            )
    return "".join(out_chars)


def parse_array_index(token: str, *, allow_append: bool = False) -> int | str:
    """Interpret a JSON Pointer token as an array index per RFC 6901 §4.

    Step 2.2 patch op (`add` / `replace` / `remove` / `test`) で配列に対する
    operation を判定するときに呼ぶ。RFC 6901 §4 では配列 index に以下の
    制約がある:

    * 0 または正の整数を ASCII 数字で表す
    * **leading zero は禁止** (``0`` 単独はよいが ``01`` は invalid)
    * ``-`` は「配列末尾の直後」を指す特別な値 (RFC 6901 §4 / 6902 §4 で
      array append として使う)

    本関数の挙動:

    * token が ``-`` かつ ``allow_append=True`` → 文字列 ``"-"`` を返す
      (呼び出し側が array append として処理する)
    * token が ``-`` かつ ``allow_append=False`` → :class:`PointerError`
      (``reason="invalid_array_index"``)
    * token が ``"0"`` または ``"123"`` のような正規の整数 → int を返す
    * token が ``"01"`` / ``"-1"`` / ``"abc"`` / ``""`` →
      :class:`PointerError` (``reason="invalid_array_index"``)
    """
    if token == ARRAY_APPEND_TOKEN:
        if allow_append:
            return ARRAY_APPEND_TOKEN
        raise PointerError(
            pointer="",
            reason="invalid_array_index",
            message=(
                "array append token '-' is only valid in add/replace contexts"
            ),
        )
    if not token:
        raise PointerError(
            pointer="",
            reason="invalid_array_index",
            message="empty token cannot be parsed as an array index",
        )
    # Phase 2 Step 2.2 補修 A1 (Codex / subagent edge-cases 高): RFC 6901
    # §4 は "0-9 ASCII digits only" を要求する。Python の ``str.isdigit()``
    # は Arabic-Indic (``٠``) や全角 (``１``) を True と判定するので、
    # 明示的に ASCII 0-9 集合に限定する。``isdigit()`` チェックも残すのは
    # ``"+1"`` のような符号付き / ``"1.0"`` のような小数を early reject
    # するため。
    if not token.isdigit() or not all(c in "0123456789" for c in token):
        raise PointerError(
            pointer="",
            reason="invalid_array_index",
            message=(
                f"token {token!r} is not a non-negative ASCII integer "
                "(RFC 6901 §4 forbids non-ASCII digits and leading signs)"
            ),
        )
    if len(token) > 1 and token[0] == "0":
        # Leading zero is forbidden by RFC 6901 §4.
        raise PointerError(
            pointer="",
            reason="invalid_array_index",
            message=f"array index {token!r} has a forbidden leading zero",
        )
    return int(token)
