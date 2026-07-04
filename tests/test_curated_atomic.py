"""Step 6b 項目 2: curated/latest/ の atomic 入れ替え.

Codex Step 5 M4/M5 の指摘への対応。現状の curated 書き込みは
``stages/`` を消してから gate.json / summary.md / 各 stage log を
順次上書きしていく直接書き方式で、

* 書き込み中の reader が ``stages`` 空 + 古い ``gate.json`` を見る
* 書き込み途中で停止すると curated/latest/ が破壊状態のまま残る

という不整合観測の窓がある。テンポラリ位置にフル一式を書いてから
既存 ``latest/`` と入れ替えれば、

* ``latest`` は「無いか、整合した一式」のいずれかでしか観測されない
* 書き込み失敗時に既存 ``latest`` を破壊しない (前回の合格証跡を守る)

ことが保証できる。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qgb.cli import EXIT_OK, main

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERIC_MINIMAL = REPO_ROOT / "examples" / "generic-minimal"


def _copy_generic_minimal(dest: Path) -> Path:
    target = dest / "generic-minimal"
    shutil.copytree(
        GENERIC_MINIMAL,
        target,
        ignore=shutil.ignore_patterns("artifacts", "evidence"),
    )
    (target / ".quality-system" / "artifacts").mkdir(exist_ok=True)
    return target


# ---- 既存の前回合格証跡を破壊しない -------------------------------------


def test_failed_curated_write_preserves_previous_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """curated 側の書き込み途中で例外が起きても、前回の latest/ は壊れない.

    現在の直接書き式だと「stages を消してから新しい gate.json を書く間」に
    curated 側で例外が起きると、latest/ が破壊状態 (stages 空 + 古い
    gate.json) で残る。atomic 化後はテンポラリ側で失敗するので latest/ は
    前回のまま残る。

    テスト戦略: ``curated_dir`` 配下への ``write_text`` を最初の 1 回目で
    raise させ、その時点での旧 latest/ の状態をチェックする。
    """
    project = _copy_generic_minimal(tmp_path)

    # 1 回目: 通常実行で latest/ を作る。
    assert (
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    )

    curated = project / ".quality-system" / "evidence" / "REQ-APP-001" / "latest"
    first_gate = json.loads((curated / "gate.json").read_text(encoding="utf-8"))
    first_run_id = first_gate["run_id"]

    real_write_text = Path.write_text

    def fail_first_curated_write(
        self: Path, data: str, *args: object, **kwargs: object
    ) -> int:
        # curated/latest/ 配下 (またはそのテンポラリ swap 先) への書き込みを raise。
        resolved = self.resolve()
        evidence_root = (
            project / ".quality-system" / "evidence" / "REQ-APP-001"
        ).resolve()
        if evidence_root in resolved.parents or resolved == evidence_root:
            raise OSError("simulated mid-write failure on curated tree")
        return real_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_first_curated_write)

    with pytest.raises(OSError, match="simulated mid-write failure"):
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)])

    # 既存の latest/ は前回 (= 1 回目の run) のまま残る。
    assert curated.is_dir()
    assert (curated / "gate.json").is_file()
    surviving = json.loads((curated / "gate.json").read_text(encoding="utf-8"))
    assert (surviving["timestamp_utc"], surviving["run_id"]) == (
        first_gate["timestamp_utc"],
        first_run_id,
    ), "atomic 書き込みなら curated 失敗時の latest は前回のまま残るはず"
    # 旧 stage logs も残る (stages 空にされていない)。
    stages_dir = curated / "stages"
    assert stages_dir.is_dir()
    assert list(stages_dir.iterdir()), (
        "stages が空になっている = 旧式の _replace_dir_contents 経路で破壊された"
    )


# ---- 中間状態の "stages 空 + 古い gate.json" が観測されない ---------------


def test_no_partial_state_with_old_gate_and_empty_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """新 gate.json を書く前に stages が空になっている瞬間が存在しない.

    現在の実装では ``_replace_dir_contents(stages)`` を呼んでから新しい
    gate.json を書くまで、latest/ は「古い gate.json + stages 空」状態。
    atomic 化後は latest/ がスワップで一気に置き換わるので、新しい
    gate.json が見える時点で stages も新しいもので埋まっている。

    テストは write_text のフックで「gate.json を書く直前の curated/latest/
    の状態」をスナップショットして検査する。
    """
    project = _copy_generic_minimal(tmp_path)

    # 1 回目で latest/ を作る。
    assert (
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    )
    curated = project / ".quality-system" / "evidence" / "REQ-APP-001" / "latest"

    # 2 回目: 各書き込み時点で latest/ がどう見えるかチェック。
    real_write_text = Path.write_text
    snapshots: list[dict[str, object]] = []

    def snapshotting_write_text(
        self: Path, data: str, *args: object, **kwargs: object
    ) -> int:
        # 旧 curated/latest/ の状態を「これから書き込もうとしているファイル名」と
        # 共にスナップショットする。
        if curated.is_dir():
            existing_gate_path = curated / "gate.json"
            try:
                existing_gate = json.loads(
                    existing_gate_path.read_text(encoding="utf-8")
                )
                existing_run_id = existing_gate.get("run_id")
            except (FileNotFoundError, json.JSONDecodeError):
                existing_run_id = None
            stages_dir = curated / "stages"
            stage_log_count = (
                len(list(stages_dir.iterdir())) if stages_dir.is_dir() else 0
            )
            snapshots.append(
                {
                    "writing": self.name,
                    "writing_to_curated": curated in self.parents,
                    "existing_run_id_in_curated": existing_run_id,
                    "stage_log_count_in_curated": stage_log_count,
                }
            )
        return real_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", snapshotting_write_text)

    assert (
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    )

    # 旧 latest/ の状態が「新 gate.json が見えるのに stages が空」になっている
    # 瞬間 (= 旧 run_id とミスマッチの stages 数) が無いことを担保。
    # atomic 入れ替えでは、curated/latest/ への書き込みは存在せず、書き込みは
    # 全てテンポラリ位置で行われ、最後に rename で一気に置き換わる。
    curated_writes = [s for s in snapshots if s["writing_to_curated"]]
    assert not curated_writes, (
        f"curated/latest/ に直接書いている: {curated_writes}"
    )


# ---- atomic 化後でも従来の不変条件は維持 --------------------------------


def test_atomic_swap_does_not_change_basic_invariants(tmp_path: Path) -> None:
    """3 連続 run でも gate.json / summary.md / stage logs が常に揃う."""
    project = _copy_generic_minimal(tmp_path)
    curated = project / ".quality-system" / "evidence" / "REQ-APP-001" / "latest"

    for _ in range(3):
        assert (
            main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
            == EXIT_OK
        )
        assert (curated / "gate.json").is_file()
        assert (curated / "summary.md").is_file()
        gate = json.loads((curated / "gate.json").read_text(encoding="utf-8"))
        for stage in gate["stages"]:
            assert (curated / stage["log_ref"]).is_file(), stage["log_ref"]


def test_atomic_swap_cleans_up_temporary_dirs(tmp_path: Path) -> None:
    """latest.tmp-* / latest.old-* が evidence/ 配下に残らない."""
    project = _copy_generic_minimal(tmp_path)

    assert (
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    )

    evidence_req = project / ".quality-system" / "evidence" / "REQ-APP-001"
    leftovers = [
        p
        for p in evidence_req.iterdir()
        if p.is_dir() and p.name != "latest" and p.name.startswith("latest")
    ]
    assert not leftovers, f"テンポラリディレクトリが掃除されていない: {leftovers}"


def test_recover_from_orphan_old_dir_when_latest_missing(tmp_path: Path) -> None:
    """Codex 補修 (Medium 2): latest/ 欠落 + latest.old-* 残存からの起動時 recovery.

    前回 run が「latest → latest.old-X にリネームしたあと、tmp → latest の
    rename をする前」で kill されると、latest/ が無く latest.old-X だけ
    残った状態になる。次の qgb run 起動時に、その latest.old-X を latest/
    に復帰させてから新しい run を行うことで、

    - 復帰前に新 run が失敗しても、前回の合格証跡が完全に消失しない
    - 復帰後の動作は通常 run と同じ
    """
    project = _copy_generic_minimal(tmp_path)

    # 1 回目: 通常実行で latest/ を作る。
    assert (
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    )
    curated_root = (
        project / ".quality-system" / "evidence" / "REQ-APP-001"
    )
    curated = curated_root / "latest"
    first_gate = json.loads((curated / "gate.json").read_text(encoding="utf-8"))
    first_run_id = first_gate["run_id"]

    # 「中断状態」を手動で再現: latest/ を latest.old-rXXXX にリネーム。
    orphan_old = curated_root / f"latest.old-{first_run_id}"
    curated.rename(orphan_old)
    assert not curated.exists()
    assert orphan_old.is_dir()

    # 復元 → 次の run。recovery が走れば、latest/ が一旦戻ってから新 run の
    # 結果で上書きされる。最終的に latest/ には新しい run の gate.json がある。
    assert (
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    )
    assert curated.is_dir()
    new_gate = json.loads((curated / "gate.json").read_text(encoding="utf-8"))
    # run_id は同一秒内でしか一意でない (evidence._reserve_run_dir: 秒が変わると
    # r0001 から再スタート)。run の同一性は (timestamp_utc, run_id) のペア
    # (= run_dir 名) で判定する。run_id 単独比較は 2 回の run が秒境界を
    # 跨いだときに両方 r0001 になり偽陽性で fail する (CI 実測 2026-07-04)。
    assert (new_gate["timestamp_utc"], new_gate["run_id"]) != (
        first_gate["timestamp_utc"],
        first_run_id,
    )

    # 復元時の orphan は最終的に掃除される (latest.old-* が残らない)。
    leftovers = [
        p
        for p in curated_root.iterdir()
        if p.is_dir() and p.name != "latest" and p.name.startswith("latest")
    ]
    assert not leftovers, leftovers


def test_swap_rename_failure_restores_previous_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex 補修 (テスト 5): tmp → latest の rename が失敗したら old を戻す.

    Step 6b 項目 2 で最も危険な失敗点は、

    1. final → old のリネーム成功 (= latest/ が一瞬消える)
    2. tmp → final のリネーム失敗

    の組み合わせ。実装側で「失敗を検出したら old → final に戻す」復元ロジックが
    あるが、テストでロックしていなかった。os.replace を monkeypatch して
    『tmp → final のときだけ raise』を起こし、最終的に latest/ が前回の状態で
    残っていることを担保する。
    """
    project = _copy_generic_minimal(tmp_path)

    # 1 回目: 通常実行で latest/ を作る。
    assert (
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    )
    curated = project / ".quality-system" / "evidence" / "REQ-APP-001" / "latest"
    first_gate = json.loads((curated / "gate.json").read_text(encoding="utf-8"))
    first_run_id = first_gate["run_id"]

    # 2 回目: os.replace を monkeypatch して、tmp → final のときだけ raise。
    import os

    real_replace = os.replace

    def fail_tmp_to_final(src: object, dst: object, *args: object, **kwargs: object) -> None:
        src_str = str(src)
        dst_str = str(dst)
        # latest.tmp-* → latest の rename だけを raise させる。dst が `latest`
        # ちょうどで終わる (`latest.old-*` や `latest.tmp-*` ではない) ことで
        # 判別する。Windows/POSIX 両方のセパレータを受け付ける。
        is_dst_final_latest = (
            dst_str.endswith("/latest") or dst_str.endswith("\\latest")
        )
        if "latest.tmp-" in src_str and is_dst_final_latest:
            raise OSError("simulated tmp→final rename failure")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", fail_tmp_to_final)

    with pytest.raises(OSError, match="simulated tmp.final rename failure"):
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)])

    # 既存 latest/ は前回 (= 1 回目の run_id) のまま残る。
    assert curated.is_dir()
    surviving = json.loads((curated / "gate.json").read_text(encoding="utf-8"))
    assert (surviving["timestamp_utc"], surviving["run_id"]) == (
        first_gate["timestamp_utc"],
        first_run_id,
    ), f"tmp→final 失敗時に latest が復元されていない: got {surviving['run_id']}"


def test_atomic_swap_removes_old_stage_logs(tmp_path: Path) -> None:
    """前回 run の stage log は新 run の latest/stages/ に残らない.

    現在の挙動 (_replace_dir_contents) と同等の効果が atomic 化後も
    保たれることを担保。fake な古い stage log を仕込んで、新 run 後に
    消えていることを確認する。
    """
    project = _copy_generic_minimal(tmp_path)

    # 1 回目で latest/ を作って、その stages/ に「使われていないログ」を混入。
    assert (
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    )
    curated = project / ".quality-system" / "evidence" / "REQ-APP-001" / "latest"
    (curated / "stages" / "S999_obsolete.log").write_text(
        "this stage no longer exists\n", encoding="utf-8"
    )

    # 2 回目を走らせると、混入した古いログは消える (新 run の stages のみ)。
    assert (
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    )

    surviving = sorted(p.name for p in (curated / "stages").iterdir())
    assert "S999_obsolete.log" not in surviving, surviving
