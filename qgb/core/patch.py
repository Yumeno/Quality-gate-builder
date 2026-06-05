"""JSON Patch subset (RFC 6902) for qgb.

Phase 2 Step 2.2 (prejournal §6.4) で新設。Codex 計画レビュー 18 指摘 +
5 着手前修正要件吸収後の確定仕様で実装。

### 採用範囲 (Step 2.2 では subset)

* ``add`` / ``replace`` / ``remove`` / ``test`` の 4 op のみ
* ``move`` / ``copy`` は **Phase 3 送り** (Pattern B は 4 op で足りる)
* ``from`` field は **schema レベルで reject** (patch.schema.json で
  additionalProperties: false + op enum 限定)

### array semantics (RFC 6902 寄り)

* ``add`` object: 既存 key は **replace 相当として許す** (RFC 6902 §4.1)
* ``add`` array: ``0..len`` 挿入と ``/-`` append を許す
* ``remove`` root path ``""`` は許す (apply 後 schema/validate で落ちる
  前提、低レベル patch として許容)
* ``test`` の equality は Python の ``==`` で行う (JSON semantic equality、
  ``1 == 1.0`` は True、テストで明示)

### 副作用ゼロ保証

* ``apply_patch(doc, patch)`` は元 ``doc`` を mutate せず、新しい doc を返す
* 内部で ``copy.deepcopy(doc)`` 1 回、その後はすべて in-place mutation
  (deepcopy 後の独立コピーなので元には波及しない)
* 失敗時は :class:`PatchError` を raise、戻り値なし → 呼び出し側で原本不変

### PatchError 構造化 (Codex 指摘 12)

reason code enum で Step 2.5 (Pattern B) の proposal/adopt 経路が
安定判定できるよう設計。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from qgb.core.json_pointer import (
    ARRAY_APPEND_TOKEN,
    PointerError,
    decode,
    parse_array_index,
)

__all__ = [
    "PatchError",
    "apply_patch",
    "SUPPORTED_OPS",
    "PHASE_2_OPS",
]


# Phase 2 Step 2.2 で受け入れる op 集合。
PHASE_2_OPS: frozenset[str] = frozenset({"add", "replace", "remove", "test"})

# Phase 3 で追加予定の op (現状は schema reject)。docstring と spec の整合
# 確認用に列挙。
PHASE_3_OPS: frozenset[str] = frozenset({"move", "copy"})

# 既知 op の集合 (RFC 6902 全 6 op)。schema 検証は op enum を PHASE_2_OPS
# に限定するので、本集合は docstring / 警告メッセージ用。
SUPPORTED_OPS: frozenset[str] = PHASE_2_OPS | PHASE_3_OPS


@dataclass(frozen=True)
class PatchError(ValueError):
    """Raised when a patch document is malformed or cannot be applied.

    ``reason`` は機械可読な分類。Step 2.5 (Pattern B) の proposal/adopt
    経路で安定判定に使う。

    reason 一覧 (prejournal §6.4):

    * ``"invalid_patch_document"`` — patch が list でない、各 op が
      object でない
    * ``"unsupported_op"`` — op enum 外 (move/copy 含む)
    * ``"missing_path"`` — op に path field が無い
    * ``"missing_value"`` — add/replace/test に value field が無い
    * ``"invalid_pointer"`` — path が JSON Pointer として malformed
      (PointerError からの transcode)
    * ``"path_not_found"`` — apply 時に target path が存在しない
    * ``"invalid_array_index"`` — array index が範囲外 / leading zero など
    * ``"test_failed"`` — test op が一致しなかった
    """

    op_index: int
    reason: str
    message: str
    pointer: str = ""

    def __str__(self) -> str:
        loc = f"op #{self.op_index}"
        if self.pointer:
            loc += f" at pointer {self.pointer!r}"
        return f"{loc}: {self.message} (reason={self.reason})"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_patch(doc: Any, patch: list[dict[str, Any]]) -> Any:
    """Apply a JSON Patch subset to ``doc`` and return a new document.

    :param doc: the source document (dict / list / scalar). Will NOT be
        mutated; a deepcopy is made internally.
    :param patch: list of operation objects, each with ``op`` / ``path``
        (and ``value`` for add/replace/test).
    :returns: the patched document (independent of ``doc``).
    :raises PatchError: on any malformed op, invalid pointer, missing path,
        out-of-range index, or failed ``test``.

    順序 spec lock (Codex 計画レビュー指摘 5/6 を Step 2.2 で踏襲):

    1. patch document の型を検査 (list of dict)
    2. deepcopy で独立コピーを作成
    3. 各 op を順番に適用
    4. どこかで失敗したら PatchError を raise、呼び出し側で元 doc は不変
    """
    if not isinstance(patch, list):
        raise PatchError(
            op_index=-1,
            reason="invalid_patch_document",
            message=f"patch must be a list of operations, got {type(patch).__name__}",
        )

    working = copy.deepcopy(doc)
    for i, op in enumerate(patch):
        working = _apply_one(working, op, i)
    return working


# ---------------------------------------------------------------------------
# Per-op dispatch
# ---------------------------------------------------------------------------


def _apply_one(doc: Any, op: dict[str, Any], op_index: int) -> Any:
    """Apply a single op to ``doc`` (in-place on the deepcopy)."""
    if not isinstance(op, dict):
        raise PatchError(
            op_index=op_index,
            reason="invalid_patch_document",
            message=f"each operation must be an object, got {type(op).__name__}",
        )

    op_name = op.get("op")
    if not isinstance(op_name, str):
        raise PatchError(
            op_index=op_index,
            reason="invalid_patch_document",
            message=f"op field must be a string, got {type(op_name).__name__}",
        )
    if op_name not in PHASE_2_OPS:
        if op_name in PHASE_3_OPS:
            raise PatchError(
                op_index=op_index,
                reason="unsupported_op",
                message=(
                    f"op {op_name!r} is RFC 6902 valid but reserved for Phase 3 "
                    f"(Phase 2 supports {sorted(PHASE_2_OPS)})"
                ),
            )
        raise PatchError(
            op_index=op_index,
            reason="unsupported_op",
            message=(
                f"op {op_name!r} is not a known JSON Patch op "
                f"(Phase 2 supports {sorted(PHASE_2_OPS)})"
            ),
        )

    path = op.get("path")
    if not isinstance(path, str):
        raise PatchError(
            op_index=op_index,
            reason="missing_path",
            message=f"op {op_name!r} requires a string 'path' field",
        )

    try:
        tokens = decode(path)
    except PointerError as exc:
        raise PatchError(
            op_index=op_index,
            reason="invalid_pointer",
            message=str(exc),
            pointer=path,
        ) from exc

    if op_name == "remove":
        return _apply_remove(doc, tokens, path, op_index)
    if op_name == "test":
        if "value" not in op:
            raise PatchError(
                op_index=op_index,
                reason="missing_value",
                message="op 'test' requires a 'value' field",
                pointer=path,
            )
        return _apply_test(doc, tokens, op["value"], path, op_index)
    # add / replace
    if "value" not in op:
        raise PatchError(
            op_index=op_index,
            reason="missing_value",
            message=f"op {op_name!r} requires a 'value' field",
            pointer=path,
        )
    if op_name == "add":
        return _apply_add(doc, tokens, op["value"], path, op_index)
    if op_name == "replace":
        return _apply_replace(doc, tokens, op["value"], path, op_index)
    # Should be unreachable due to op enum check above.
    raise PatchError(
        op_index=op_index,
        reason="unsupported_op",
        message=f"unhandled op {op_name!r}",
        pointer=path,
    )


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def _apply_add(
    doc: Any, tokens: list[str], value: Any, path: str, op_index: int
) -> Any:
    """RFC 6902 §4.1 add."""
    if not tokens:
        # add to root replaces the entire document.
        return value
    parent, last_token = _navigate_to_parent(doc, tokens, path, op_index)
    if isinstance(parent, list):
        idx = _resolve_array_index(
            last_token, len(parent), path, op_index, allow_append=True
        )
        if idx == ARRAY_APPEND_TOKEN:
            parent.append(value)
        else:
            assert isinstance(idx, int)  # for type-checkers
            if idx > len(parent):
                raise PatchError(
                    op_index=op_index,
                    reason="invalid_array_index",
                    message=(
                        f"add index {idx} exceeds array length {len(parent)}"
                    ),
                    pointer=path,
                )
            parent.insert(idx, value)
        return doc
    if isinstance(parent, dict):
        # RFC 6902 §4.1: existing key is replaced.
        parent[last_token] = value
        return doc
    raise PatchError(
        op_index=op_index,
        reason="path_not_found",
        message=f"cannot add into {type(parent).__name__} at {path!r}",
        pointer=path,
    )


# ---------------------------------------------------------------------------
# replace
# ---------------------------------------------------------------------------


def _apply_replace(
    doc: Any, tokens: list[str], value: Any, path: str, op_index: int
) -> Any:
    """RFC 6902 §4.3 replace."""
    if not tokens:
        return value
    parent, last_token = _navigate_to_parent(doc, tokens, path, op_index)
    if isinstance(parent, list):
        idx = _resolve_array_index(
            last_token, len(parent), path, op_index, allow_append=False
        )
        assert isinstance(idx, int)
        if idx >= len(parent):
            raise PatchError(
                op_index=op_index,
                reason="path_not_found",
                message=f"replace index {idx} out of range (len={len(parent)})",
                pointer=path,
            )
        parent[idx] = value
        return doc
    if isinstance(parent, dict):
        if last_token not in parent:
            raise PatchError(
                op_index=op_index,
                reason="path_not_found",
                message=f"replace target key {last_token!r} does not exist",
                pointer=path,
            )
        parent[last_token] = value
        return doc
    raise PatchError(
        op_index=op_index,
        reason="path_not_found",
        message=f"cannot replace into {type(parent).__name__} at {path!r}",
        pointer=path,
    )


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


def _apply_remove(
    doc: Any, tokens: list[str], path: str, op_index: int
) -> Any:
    """RFC 6902 §4.2 remove. Root removal returns None (caller decides)."""
    if not tokens:
        # Removing the root makes the result an empty/None document.
        return None
    parent, last_token = _navigate_to_parent(doc, tokens, path, op_index)
    if isinstance(parent, list):
        idx = _resolve_array_index(
            last_token, len(parent), path, op_index, allow_append=False
        )
        assert isinstance(idx, int)
        if idx >= len(parent):
            raise PatchError(
                op_index=op_index,
                reason="path_not_found",
                message=f"remove index {idx} out of range (len={len(parent)})",
                pointer=path,
            )
        del parent[idx]
        return doc
    if isinstance(parent, dict):
        if last_token not in parent:
            raise PatchError(
                op_index=op_index,
                reason="path_not_found",
                message=f"remove target key {last_token!r} does not exist",
                pointer=path,
            )
        del parent[last_token]
        return doc
    raise PatchError(
        op_index=op_index,
        reason="path_not_found",
        message=f"cannot remove from {type(parent).__name__} at {path!r}",
        pointer=path,
    )


# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------


def _apply_test(
    doc: Any, tokens: list[str], expected: Any, path: str, op_index: int
) -> Any:
    """RFC 6902 §4.6 test. Raises ``test_failed`` if mismatched."""
    current = _navigate_to_value(doc, tokens, path, op_index)
    # JSON semantic equality via Python ``==``. Note: ``1 == 1.0`` is True
    # (intentional — JSON spec doesn't distinguish int vs float types).
    if current != expected:
        raise PatchError(
            op_index=op_index,
            reason="test_failed",
            message=(
                f"test at {path!r} failed: expected {expected!r}, got {current!r}"
            ),
            pointer=path,
        )
    return doc


# ---------------------------------------------------------------------------
# navigation helpers
# ---------------------------------------------------------------------------


def _navigate_to_parent(
    doc: Any, tokens: list[str], path: str, op_index: int
) -> tuple[Any, str]:
    """Walk to the parent container of the final token. Returns (parent, last_token)."""
    parent = doc
    for tok in tokens[:-1]:
        parent = _step_into(parent, tok, path, op_index)
    return parent, tokens[-1]


def _navigate_to_value(
    doc: Any, tokens: list[str], path: str, op_index: int
) -> Any:
    """Walk through every token and return the value at the leaf."""
    cur = doc
    for tok in tokens:
        cur = _step_into(cur, tok, path, op_index)
    return cur


def _step_into(node: Any, token: str, path: str, op_index: int) -> Any:
    """Resolve a single token against ``node`` (dict or list)."""
    if isinstance(node, list):
        idx = _resolve_array_index(
            token, len(node), path, op_index, allow_append=False
        )
        assert isinstance(idx, int)
        if idx >= len(node):
            raise PatchError(
                op_index=op_index,
                reason="path_not_found",
                message=f"array index {idx} out of range (len={len(node)})",
                pointer=path,
            )
        return node[idx]
    if isinstance(node, dict):
        if token not in node:
            raise PatchError(
                op_index=op_index,
                reason="path_not_found",
                message=f"key {token!r} not found in object",
                pointer=path,
            )
        return node[token]
    raise PatchError(
        op_index=op_index,
        reason="path_not_found",
        message=(
            f"cannot step into {type(node).__name__} with token {token!r}"
        ),
        pointer=path,
    )


def _resolve_array_index(
    token: str,
    length: int,
    path: str,
    op_index: int,
    *,
    allow_append: bool,
) -> int | str:
    """Translate a token into an array index, surfacing PointerError as PatchError."""
    try:
        return parse_array_index(token, allow_append=allow_append)
    except PointerError as exc:
        raise PatchError(
            op_index=op_index,
            reason="invalid_array_index",
            message=str(exc),
            pointer=path,
        ) from exc
