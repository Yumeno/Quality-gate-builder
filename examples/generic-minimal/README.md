# examples/generic-minimal/

qgb の **入門用最小サンプル**。言語非依存 (Generic) で、`file_exists` と `substring_match` の 2 段階だけで構成される。

## このサンプルが示すこと

- `qgb init` から `qgb validate` までのラウンドトリップが動くこと
- 段階を 2 個だけ宣言した場合の最小構造
- gate.json の採用判定証跡の見た目

## このサンプルが示さないこと

- 推奨段階数 (3〜7) の例 → `examples/python-cli-pytest/` (Step 8)
- 非プログラミング対象の例 → `examples/markdown-docs/` (Step 8)
- 外部コマンド呼び出し (verification_type: command) の例 → 上記 Python 例

## ファイル構成

```
examples/generic-minimal/
  README.md                                   # 本書
  design-notes.md                             # 設計判断メモ (採用しなかった段階を含む)
  .gitignore                                  # 揮発側 artifacts/ を除外
  target/
    sample.txt                                # 検査対象テキスト
  .quality-system/
    config.json                               # qgb config (project name = generic-minimal)
    policy.json                               # S1, S2 を定義 (file_exists + substring_match)
    req/
      REQ-APP-001.md                          # REQ 本文 (人間向け)
      REQ-APP-001.meta.json                   # REQ メタ (S1, S2 を選択)
    contracts/REQ-APP-001/
      S1.json                                 # file_exists contract
      S2.json                                 # substring_match contract
    evidence/REQ-APP-001/latest/
      gate.json                               # 手書きの期待 ALLOW 出力 (Step 5 のリファレンス)
      summary.md                              # 人間向け要約
```

`.quality-system/artifacts/` ディレクトリ自体は git に含まれない。実際に `qgb run` を実行すると `.quality-system/artifacts/REQ-APP-001/runs/<timestamp>/` 配下に揮発側証跡が生成される (Step 5 で実装予定)。

## 使い方

このサンプルは「動かす」のではなく「読む」前提。Step 5 の `qgb run` が実装された後に、ここで動作確認できる：

```bash
cd examples/generic-minimal
python -m qgb validate           # OK: all JSON sources of truth are valid.
python -m qgb run REQ-APP-001    # ALLOW (Step 5 以降)
```

それまでは `qgb validate` でスキーマ準拠だけ確認可能：

```bash
$ python -m qgb validate --path examples/generic-minimal
Checked 5 file(s):
  - .../config.json (schema: config)
  - .../policy.json (schema: policy)
  - .../REQ-APP-001.meta.json (schema: req-meta)
  - .../REQ-APP-001/S1.json (schema: contract)
  - .../REQ-APP-001/S2.json (schema: contract)
OK: all JSON sources of truth are valid.
```

## 関連文書

- `design-notes.md`: なぜこの構成にしたかの判断記録
- `../../development/docs/philosophy.md`: 思想憲章 (P9, P10)
- `../../development/docs/stage-design.md`: 段階設計仕様 (推奨レンジ 3〜7)
- `../../development/docs/detailed-design.md`: 詳細設計
