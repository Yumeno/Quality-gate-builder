# design-notes (examples/python-fastapi-pytest)

このノートは `examples/python-fastapi-pytest/` がなぜ現在の 3 段階構成に
なっているかを記録する。

## 対象系の特徴

Python の FastAPI Web API + pytest + httpx テスト群。FastAPI の
`TestClient` (httpx ベース) を使うことで、テスト時にサーバーを起動しない
構成が一般的。検査対象は次の 3 軸:

- **API エンドポイントの正しさ** — TestClient 経由で各ルートが期待する
  JSON を返すこと。
- **エントリポイントの存在** — `src/demo_api/main.py` が存在し、
  uvicorn に渡せる `app` オブジェクトを持つこと。
- **利用者向け Usage 文書** — README.md に起動手順が記載されていること。

## 段階数の決定根拠

stage-design.md §9 が **3〜7 段階** を推奨レンジとしている。本 example
は推奨レンジの **下限である 3** を選んだ。

理由:

- 2 段階以下にすると pytest と file_exists を 1 stage にまとめる形になり
  P9 単一責任原則に違反する。
- 4 段階以上にすると type-check / lint / OpenAPI スキーマ検証が混ざり、
  Phase 1 の最小例の位置づけを逸脱する。

## 採用した段階と理由

| stage | verification_type | 単一責務 | なぜ |
|---|---|---|---|
| S1 | `command` | pytest + httpx TestClient が exit 0 | API 実装本体の回帰検知。TestClient はサーバー不要なので CI でも確実に実行できる |
| S2 | `file_exists` | `src/demo_api/main.py` が存在 | エントリポイント存在保証。テストが通っても main.py が削除されていれば uvicorn が起動しない |
| S3 | `substring_match` | README に "Usage" を含む | 利用者の onboarding。コード品質ではなくドキュメント品質を独立に担保 |

S1 と S2 を分けるのは python-cli-pytest と同じ理由: テストは内部的に
モジュールを import するので、`main.py` が存在しなくてもテスト自体は
パスし得る。しかし利用者が `uvicorn demo_api.main:app` で起動するには
ファイルが必要で、その経路を S2 で守る。

## 採用しなかった段階と理由

- **OpenAPI スキーマ検証 (json_schema)** — FastAPI は `/openapi.json` を
  自動生成するが、テスト実行中に HTTP サーバーを起動してフェッチする必要が
  あり、Phase 1 の `command` / `file_exists` / `substring_match` の範囲
  では clean に扱えない。Phase 2 adapter で検討する。
- **type-check (mypy / pyright)** — python-cli-pytest と同じ理由で送り。
- **lint (ruff)** — 同上。
- **docker build** — デプロイ形態に依存しすぎる。

## 思想憲章のどの項目が特に効くか

- **P9 (単一責任)** — S1 (テスト通過) と S2 (ファイル存在) の分離根拠。
- **P6 (LLM 単独 ALLOW 禁止)** — 全 stage が機械検証であり、manual_check
  を含まない。
- **P7 (再現可能証跡)** — command の exit code、file_exists の結果、
  substring_match の結果がそれぞれ log に記録される。
- **NF-004 (Windows first-class)** — pytest + httpx は Windows でも
  ネイティブに動作する (サーバー起動不要)。

## 段階間の依存関係

```
S1 (pytest)     S2 (file_exists)     S3 (substring_match)
   独立            独立                   独立
```

3 stage すべてが独立 (`depends_on: []`)。pytest が file_exists に依存しない
のは意図的: pytest は Python の import 機構で動作するので、`main.py` の
存在とは別経路で成功し得る。

## 既知の限界

- TestClient は同プロセス内でリクエストするので、ネットワーク周りの問題
  (CORS、proxy、TLS) は検知できない。
- FastAPI の `/docs` / `/openapi.json` は TestClient ではテストしていない
  (前述の採用しなかった段階の理由参照)。
- 依存 (fastapi, httpx) のインストールを前提としているため、
  `qgb run --path .` を叩く前に `pip install -e ".[test]"` が必要。
