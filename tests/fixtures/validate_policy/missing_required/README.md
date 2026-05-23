# Fixture: missing_required

`.quality-system/policy.json` を意図的に欠落させた tree。

## qgb validate-policy への期待

* exit code: 2 (NOT_READY)
* blockers に `missing_required_file` (policy.json) を含む
* warnings は無関係 (blocker があれば exit 2)

## 役割

「正本ファイルの欠落」を validate-policy が確実に検出することを
spec として固定する装置。Step 2 巻き戻し時に validate から外した
責務 (cross-file integrity) が validate-policy で復活していることの
回帰防止。
