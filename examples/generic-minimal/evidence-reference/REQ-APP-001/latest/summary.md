# REQ-APP-001 採用判定サマリ

## 判定結果

**ALLOW**

> Defined checks passed. This is not proof of total correctness.

## 実行情報

| 項目 | 値 |
|---|---|
| REQ ID | REQ-APP-001 |
| Phase | verify |
| 実行日時 (UTC) | 2026-05-21T120000Z |
| 実行日時 (RFC3339) | 2026-05-21T12:00:00Z |
| run_id | `r0001` |
| Runner | qgb 0.1.0 |
| run_dir | `.quality-system/artifacts/REQ-APP-001/runs/2026-05-21T120000Z-r0001` |
| curated_latest_dir | `.quality-system/evidence/REQ-APP-001/latest` |

## 段階別結果

| 段階 | 名前 | 結果 | verification_type |
|---|---|---|---|
| S1 | sample ファイル存在 | passed | file_exists |
| S2 | キーワード包含 | passed | substring_match |

すべての必須段階が通過したため、status=ALLOW。

## 採用根拠 (basis)

- REQ-APP-001 (REQ 本文 + メタ)
- POLICY-default (段階定義)
- CONTRACT-REQ-APP-001-S1 (S1 の検査契約)
- CONTRACT-REQ-APP-001-S2 (S2 の検査契約)

## 注意 (思想 P5, P11)

- 本 ALLOW は「定義済み検査に通過した」ことのみを意味する。完全な正しさ・業務妥当性・将来の保証は意味しない
- 本 ALLOW は当該プロジェクト内の policy と contract に対する局所判定であり、他プロジェクトとの品質水準比較には使えない

## 注意 (このファイルについて)

このファイルは Step 4 で手書きされた **リファレンス** であり、Step 5 で `qgb run` が実装されると、実行時に同じスキーマで自動生成される。
