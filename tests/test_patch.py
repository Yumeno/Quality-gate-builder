"""Tests for qgb.core.patch (Phase 2 Step 2.2 prejournal §6.4).

JSON Patch subset (add / replace / remove / test) の境界仕様を spec lock。
Codex 計画レビュー指摘 1 (array semantics) / 2 (pointer invalid escape) /
12 (PatchError reason code) / 14 (元 doc 非 mutate op 別テスト) を網羅。
"""

from __future__ import annotations

import copy

import pytest

from qgb.core.patch import PatchError, apply_patch

# ---- add: object key 追加 / 既存 key 置換 / array index 挿入 / append ----


class TestApplyAdd:
    def test_add_new_object_key(self) -> None:
        doc = {"a": 1}
        result = apply_patch(doc, [{"op": "add", "path": "/b", "value": 2}])
        assert result == {"a": 1, "b": 2}

    def test_add_existing_key_replaces_value(self) -> None:
        # RFC 6902 §4.1: existing key is replaced.
        doc = {"a": 1}
        result = apply_patch(doc, [{"op": "add", "path": "/a", "value": 99}])
        assert result == {"a": 99}

    def test_add_to_root_replaces_document(self) -> None:
        doc = {"a": 1}
        result = apply_patch(doc, [{"op": "add", "path": "", "value": {"b": 2}}])
        assert result == {"b": 2}

    def test_add_to_array_index_inserts(self) -> None:
        doc = [1, 2, 3]
        result = apply_patch(doc, [{"op": "add", "path": "/1", "value": 99}])
        assert result == [1, 99, 2, 3]

    def test_add_to_array_at_end_index(self) -> None:
        # Index == len means append per RFC 6902.
        doc = [1, 2, 3]
        result = apply_patch(doc, [{"op": "add", "path": "/3", "value": 4}])
        assert result == [1, 2, 3, 4]

    def test_add_to_array_with_dash_appends(self) -> None:
        # The "-" token is array append.
        doc = [1, 2]
        result = apply_patch(doc, [{"op": "add", "path": "/-", "value": 3}])
        assert result == [1, 2, 3]

    def test_add_to_array_dash_on_empty_array(self) -> None:
        doc: list[int] = []
        result = apply_patch(doc, [{"op": "add", "path": "/-", "value": 1}])
        assert result == [1]

    def test_add_to_nested_path(self) -> None:
        doc = {"stages": [{"id": "S1"}, {"id": "S2"}]}
        result = apply_patch(
            doc,
            [{"op": "add", "path": "/stages/0/name", "value": "first"}],
        )
        assert result == {"stages": [{"id": "S1", "name": "first"}, {"id": "S2"}]}

    def test_add_array_index_out_of_range_raises(self) -> None:
        doc = [1, 2, 3]
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, [{"op": "add", "path": "/10", "value": 99}])
        assert exc_info.value.reason == "invalid_array_index"


# ---- replace: 既存 key 上書き / array index 置換 -----------------------


class TestApplyReplace:
    def test_replace_existing_key(self) -> None:
        doc = {"a": 1}
        result = apply_patch(doc, [{"op": "replace", "path": "/a", "value": 2}])
        assert result == {"a": 2}

    def test_replace_root(self) -> None:
        result = apply_patch({"a": 1}, [{"op": "replace", "path": "", "value": [1]}])
        assert result == [1]

    def test_replace_array_index(self) -> None:
        doc = [10, 20, 30]
        result = apply_patch(doc, [{"op": "replace", "path": "/1", "value": 99}])
        assert result == [10, 99, 30]

    def test_replace_missing_key_raises(self) -> None:
        doc = {"a": 1}
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, [{"op": "replace", "path": "/b", "value": 2}])
        assert exc_info.value.reason == "path_not_found"

    def test_replace_array_dash_rejected(self) -> None:
        # "-" is not a valid index for replace (only valid for add).
        doc = [1, 2]
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, [{"op": "replace", "path": "/-", "value": 99}])
        assert exc_info.value.reason == "invalid_array_index"

    def test_replace_array_index_out_of_range(self) -> None:
        doc = [1, 2, 3]
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, [{"op": "replace", "path": "/10", "value": 99}])
        assert exc_info.value.reason == "path_not_found"


# ---- remove: key 削除 / array index 削除 / root remove ------------------


class TestApplyRemove:
    def test_remove_object_key(self) -> None:
        doc = {"a": 1, "b": 2}
        result = apply_patch(doc, [{"op": "remove", "path": "/a"}])
        assert result == {"b": 2}

    def test_remove_array_index(self) -> None:
        doc = [1, 2, 3]
        result = apply_patch(doc, [{"op": "remove", "path": "/1"}])
        assert result == [1, 3]

    def test_remove_root_returns_none(self) -> None:
        # Low-level patch allows root removal; apply-after schema/validate
        # is expected to reject it (Codex 計画レビュー指摘 1).
        result = apply_patch({"a": 1}, [{"op": "remove", "path": ""}])
        assert result is None

    def test_remove_missing_key_raises(self) -> None:
        doc = {"a": 1}
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, [{"op": "remove", "path": "/b"}])
        assert exc_info.value.reason == "path_not_found"

    def test_remove_array_dash_rejected(self) -> None:
        doc = [1, 2]
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, [{"op": "remove", "path": "/-"}])
        assert exc_info.value.reason == "invalid_array_index"


# ---- test: 等価判定 / 失敗 / JSON semantic equality ----------------------


class TestApplyTest:
    def test_test_passes_for_equal_value(self) -> None:
        doc = {"a": 1}
        result = apply_patch(doc, [{"op": "test", "path": "/a", "value": 1}])
        assert result == {"a": 1}

    def test_test_fails_for_mismatch(self) -> None:
        doc = {"a": 1}
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, [{"op": "test", "path": "/a", "value": 99}])
        assert exc_info.value.reason == "test_failed"

    def test_test_int_equals_float(self) -> None:
        # JSON semantic equality: ``1 == 1.0`` is True in Python and
        # we intentionally adopt that for test op (Codex 指摘 4 acknowledged).
        doc = {"a": 1}
        result = apply_patch(doc, [{"op": "test", "path": "/a", "value": 1.0}])
        assert result == {"a": 1}

    def test_test_nested_value(self) -> None:
        doc = {"stages": [{"id": "S1"}]}
        result = apply_patch(
            doc,
            [{"op": "test", "path": "/stages/0/id", "value": "S1"}],
        )
        assert result == doc

    def test_test_path_not_found(self) -> None:
        doc = {"a": 1}
        with pytest.raises(PatchError) as exc_info:
            apply_patch(doc, [{"op": "test", "path": "/b", "value": 1}])
        assert exc_info.value.reason == "path_not_found"


# ---- malformed patch documents (reason code 検証) ----------------------


class TestPatchDocumentValidation:
    def test_patch_must_be_list(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({}, {"op": "add", "path": "/a", "value": 1})  # type: ignore[arg-type]
        assert exc_info.value.reason == "invalid_patch_document"

    def test_op_must_be_object(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({}, ["not a dict"])  # type: ignore[list-item]
        assert exc_info.value.reason == "invalid_patch_document"

    def test_op_field_must_be_string(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({}, [{"op": 123, "path": "/a", "value": 1}])  # type: ignore[dict-item]
        assert exc_info.value.reason == "invalid_patch_document"

    def test_unsupported_op_unknown(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({}, [{"op": "frobnicate", "path": "/a", "value": 1}])
        assert exc_info.value.reason == "unsupported_op"

    def test_move_is_phase_3(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch(
                {"a": 1},
                [{"op": "move", "path": "/b", "from": "/a"}],
            )
        assert exc_info.value.reason == "unsupported_op"
        assert "Phase 3" in exc_info.value.message

    def test_copy_is_phase_3(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch(
                {"a": 1},
                [{"op": "copy", "path": "/b", "from": "/a"}],
            )
        assert exc_info.value.reason == "unsupported_op"
        assert "Phase 3" in exc_info.value.message

    def test_missing_path(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({}, [{"op": "add", "value": 1}])
        assert exc_info.value.reason == "missing_path"

    def test_missing_value_for_add(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({}, [{"op": "add", "path": "/a"}])
        assert exc_info.value.reason == "missing_value"

    def test_missing_value_for_replace(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({"a": 1}, [{"op": "replace", "path": "/a"}])
        assert exc_info.value.reason == "missing_value"

    def test_missing_value_for_test(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({"a": 1}, [{"op": "test", "path": "/a"}])
        assert exc_info.value.reason == "missing_value"

    def test_invalid_pointer_unterminated_escape(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({}, [{"op": "add", "path": "/foo~", "value": 1}])
        assert exc_info.value.reason == "invalid_pointer"

    def test_invalid_pointer_invalid_escape(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({}, [{"op": "add", "path": "/foo~2", "value": 1}])
        assert exc_info.value.reason == "invalid_pointer"

    def test_invalid_pointer_not_starting_with_slash(self) -> None:
        with pytest.raises(PatchError) as exc_info:
            apply_patch({}, [{"op": "add", "path": "foo", "value": 1}])
        assert exc_info.value.reason == "invalid_pointer"


# ---- 元 doc 非 mutate 保証 (Codex 指摘 14、op 別) ----------------------


class TestOriginalDocNotMutated:
    def test_add_does_not_mutate_original(self) -> None:
        doc = {"a": 1}
        snapshot = copy.deepcopy(doc)
        apply_patch(doc, [{"op": "add", "path": "/b", "value": 2}])
        assert doc == snapshot

    def test_replace_does_not_mutate_original(self) -> None:
        doc = {"a": 1, "nested": [1, 2, 3]}
        snapshot = copy.deepcopy(doc)
        apply_patch(doc, [{"op": "replace", "path": "/nested/1", "value": 99}])
        assert doc == snapshot

    def test_remove_does_not_mutate_original(self) -> None:
        doc = {"a": 1, "b": [1, 2, 3]}
        snapshot = copy.deepcopy(doc)
        apply_patch(doc, [{"op": "remove", "path": "/b/0"}])
        assert doc == snapshot

    def test_test_does_not_mutate_original(self) -> None:
        doc = {"a": 1, "nested": {"x": [1, 2]}}
        snapshot = copy.deepcopy(doc)
        apply_patch(doc, [{"op": "test", "path": "/nested/x/0", "value": 1}])
        assert doc == snapshot

    def test_failed_op_does_not_mutate_original(self) -> None:
        # When a patch fails mid-sequence, the caller's original doc must
        # remain untouched (deepcopy isolates the working copy).
        doc = {"a": 1, "b": 2}
        snapshot = copy.deepcopy(doc)
        with pytest.raises(PatchError):
            apply_patch(
                doc,
                [
                    {"op": "remove", "path": "/a"},
                    {"op": "remove", "path": "/missing"},
                ],
            )
        assert doc == snapshot


# ---- multi-op sequence (順序保証) --------------------------------------


class TestMultiOpSequence:
    def test_sequential_ops_applied_in_order(self) -> None:
        doc = {"a": 1}
        result = apply_patch(
            doc,
            [
                {"op": "add", "path": "/b", "value": 2},
                {"op": "replace", "path": "/a", "value": 10},
                {"op": "remove", "path": "/b"},
            ],
        )
        assert result == {"a": 10}

    def test_test_pass_then_add(self) -> None:
        doc = {"a": 1}
        result = apply_patch(
            doc,
            [
                {"op": "test", "path": "/a", "value": 1},
                {"op": "add", "path": "/b", "value": 2},
            ],
        )
        assert result == {"a": 1, "b": 2}

    def test_test_fail_aborts_sequence(self) -> None:
        doc = {"a": 1, "b": 2}
        snapshot = copy.deepcopy(doc)
        with pytest.raises(PatchError) as exc_info:
            apply_patch(
                doc,
                [
                    {"op": "test", "path": "/a", "value": 99},
                    {"op": "add", "path": "/c", "value": 3},
                ],
            )
        assert exc_info.value.reason == "test_failed"
        assert doc == snapshot
