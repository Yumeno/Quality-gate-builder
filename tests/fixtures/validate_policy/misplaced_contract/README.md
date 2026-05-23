# Fixture: misplaced_contract

contract.json が canonical layout (`.quality-system/contracts/<REQ>/<stage>.json`)
ではなく `sub/` サブディレクトリの下に置かれている tree。
REQ meta の `contract_ref` もそれを指している。

## qgb validate-policy への期待

* exit code: 2 (NOT_READY)
* blockers に `misplaced_contract` を含む
* contract.json 自体は schema を満たしているので `schema_violation` は出ない

## 役割

「contract 配置の予測不能化」を validate-policy が確実に検出することを
spec として固定する装置。深い階層、別 REQ ディレクトリ下、別拡張子 (`.yaml`)
などのバリエーションも全て同じ `misplaced_contract` kind で扱う。
