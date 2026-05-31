# REQ-APP-001 — demo_cli が起動し、テストが通り、install 手順が書かれている

このプロジェクト (examples/python-cli-pytest) が満たすべき品質要求。

## ALLOW の条件

| stage | 検査内容 |
|---|---|
| S1 | `python -m pytest -q` が exit 0 で完了する |
| S2 | `python -m demo_cli --help` が exit 0 で完了する |
| S3 | `README.md` に `Installation` という文字列が含まれる |

S1 と S2 はそれぞれ「内部実装の正しさ」と「CLI 表面の起動性」を独立に検査する。
S3 は「新規利用者が install できる手順が文書化されていること」を静的に検査する。

詳細な責務分割の根拠は `../design-notes.md` を参照。
