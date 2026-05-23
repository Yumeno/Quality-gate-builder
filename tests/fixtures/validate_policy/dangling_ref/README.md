# Fixture: dangling_ref

REQ meta が policy.json に存在しない `stage_id` (`S999`) を参照する tree。

## qgb validate-policy への期待

* exit code: 2 (NOT_READY)
* blockers に `unknown_stage_id` を含む
* policy.json は 3 段階あるので `stage_count_out_of_range` は出ない

## 役割

「stage_id の dangling reference」を validate-policy が確実に検出する
ことを spec として固定する装置。同様に依存関係チェック (depends_on)
の dangling も同じ kind ファミリで扱われる。
