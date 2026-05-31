# REQ-DOC-001 採用判定サマリ

## 判定結果

**ALLOW**

> Defined checks passed. This is not proof of total correctness.

## 実行情報

| 項目 | 値 |
|---|---|
| REQ ID | REQ-DOC-001 |
| Phase | verify |
| 実行日時 (UTC) | 2026-05-21T120000Z |
| 実行日時 (RFC3339) | 2026-05-21T12:00:00Z |
| run_id | `r0001` |
| Runner | qgb 0.1.0 |
| run_dir | `.quality-system/artifacts/REQ-DOC-001/runs/2026-05-21T120000Z-r0001` |
| curated_latest_dir | `.quality-system/evidence/REQ-DOC-001/latest` |

## 段階別結果

| 段階 | 名前 | 結果 | verification_type |
|---|---|---|---|
| S1 | index ページが存在する | passed | file_exists |
| S2 | index ページに H1 ヘッダがある | passed | substring_match |
| S3 | metadata が schema に従う | passed | json_schema |

すべての必須段階が通過したため、status=ALLOW。

## 採用根拠 (basis)

- REQ-DOC-001
- POLICY-default
- CONTRACT-REQ-DOC-001-S1
- CONTRACT-REQ-DOC-001-S2
- CONTRACT-REQ-DOC-001-S3

## 注意 (思想 P5, P11)

- 本判定は「定義済み検査に通過した」ことのみを意味する。完全な正しさ・業務妥当性・将来の保証は意味しない
- 本判定は当該プロジェクト内の policy と contract に対する局所判定であり、他プロジェクトとの品質水準比較には使えない
