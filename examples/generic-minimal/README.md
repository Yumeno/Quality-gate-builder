# examples/generic-minimal/

qgb の **入門用最小サンプル**。言語非依存 (Generic) で、`file_exists` と `substring_match` の 2 段階だけで構成される。

設計判断の根拠は `design-notes.md` を参照。本 README はサンプルの構成と使い方の入口に限定する。

## このサンプルが示すこと

- 最小の `.quality-system/` ツリーが `qgb validate` を通ること
- 段階を 2 個だけ宣言した場合の最小構造
- gate.json の採用判定証跡の見た目 (Step 5 の `qgb run` リファレンス)

## このサンプルが示さないこと

- 推奨段階数 (3〜7) の例 → `examples/python-cli-pytest/` (Step 8 で追加予定)
- 非プログラミング対象の例 → `examples/markdown-docs/` (Step 8 で追加予定)
- 外部コマンド呼び出し (verification_type: command) の例 → 上記 Python 例 (Step 8 で追加予定)

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
    evidence/                                 # qgb run の採用判定証跡 destination (repo には empty)
  evidence-reference/REQ-APP-001/latest/      # 手書きの期待出力 (Step 5 のリファレンス、コミット対象)
    gate.json                                 # 期待 ALLOW gate.json
    summary.md                                # 人間向け要約
    stages/
      S1.log
      S2.log
```

Step 5 補修: 手書きの期待出力は `evidence-reference/` に分離してある。`.quality-system/evidence/` 自体は `qgb run` の destination 専用とし、リポジトリには空ディレクトリ (または非存在) のまま保つ。これにより `python -m qgb run REQ-APP-001 --path examples/generic-minimal` をリポジトリ内で直接実行しても、コミット済みのリファレンス出力は上書きされない。

`.quality-system/artifacts/` ディレクトリは git に含まれない (`.gitignore` で除外)。`qgb run` 実行時に `.quality-system/artifacts/REQ-APP-001/runs/<timestamp>/` 配下に揮発側証跡が生成される。

## 使い方

このサンプルは「動かす」のではなく「読む」前提。Step 5 の `qgb run` が実装済みなので、ここで動作確認できる：

```bash
cd examples/generic-minimal
python -m qgb validate           # OK: all JSON sources of truth are valid.
python -m qgb run REQ-APP-001    # ALLOW
```

`qgb run` 実行後、`.quality-system/evidence/REQ-APP-001/latest/gate.json` と `.quality-system/artifacts/REQ-APP-001/runs/<timestamp>/` に生成された証跡を、手書きリファレンス (`evidence-reference/REQ-APP-001/latest/gate.json`) と見比べると Step 5 の挙動が理解しやすい。

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
