# 設計判断メモ: generic-minimal

## 対象系の特徴

このサンプルは **特定の対象系を持たない**。プログラミング言語にも対象成果物の種類にも依存しない、qgb の最小動作確認用の例として位置づける。

入門者が qgb の全体像を掴むためのスケルトンであり、実プロジェクトでこの設計をそのまま流用するのは推奨しない（後述の限界を参照）。

## 段階数の決定根拠: 意図的に 2 段階

段階設計仕様 (`stage-design.md` §9) は **推奨段階数を 3〜7** としている。本サンプルは **2 段階** で、推奨レンジから外れる。

2 段階に絞った理由:

- 入門者が読むときに、最小の構造で「段階」「contract」「REQ メタの段階選択」「gate.json」の関係を一望できる
- 3 段階以上だと verification_type のバリエーション (command, json_schema 等) を見せたくなるが、それは別サンプル (python-cli-pytest, Step 8) の責務
- 2 段階でも `depends_on` の依存関係 (`S2` が `S1` に依存) は表現できる

実プロジェクトで qgb を使う場合、`qgb validate-policy` (Step 6) は段階数が推奨レンジ外であることを warning として通知する。本サンプルでもその warning は発生する想定（design intent としては許容）。

## 採用した段階と理由

### S1: sample ファイル存在 (file_exists)

- **目的**: 検査対象が物理的に存在するという最低限の前提を確認
- **思想根拠**: P7 (再現可能な証跡) — ファイルが無い状態を ALLOW にしないための最初の門
- **責務 (responsibility)**: 「target/sample.txt が存在する」
- **依存**: なし
- **verification_type**: file_exists

### S2: キーワード包含 (substring_match)

- **目的**: ファイルが期待する内容を含むことを確認
- **思想根拠**: P5 (ALLOW の限定的意味) — 「ファイルがある」だけでは ALLOW にしない、内容も契約に従う必要がある
- **責務 (responsibility)**: 「target/sample.txt に "hello" が含まれる」
- **依存**: S1 (ファイルが無ければキーワード検索する意味がない)
- **verification_type**: substring_match

## 採用しなかった段階と理由 (← 最も重要)

### 「ファイルサイズが妥当な範囲か」段階

- **却下理由**: P5 (ALLOW の限定的意味) の観点で、本 REQ の ALLOW は「sample.txt 存在と挨拶キーワード包含」のみを意味する。サイズの妥当性をこの ALLOW に内包させると、ALLOW の意味が曖昧になる。P9 (単一責任) の観点でも、S1 (存在) に混ぜず別段階にすべきだが、入門用なので最小構成を優先した
- **採用時の検討**: バイナリ汚染や DoS リスクを ALLOW の意味として保証したい場合は、`file_size_bounds` のような独立段階で実装する

### 「ファイルが UTF-8 として valid か」段階

- **却下理由**: P9 (単一責任原則) の観点で、符号化検査と内容検査は別責務である。本サンプルでは encoding error の **診断責務をスコープに含めない** ことを明示的に選んだ。壊れた UTF-8 の場合は S2 が DENY となるが、それは「内容検査が失敗した」ことだけを意味し、原因が encoding 不正かキーワード不在かを切り分けない
- **採用時の検討**: encoding error を利用者に明示したい対象系 (国際化文書、外部入力を読み込むサービス) では、`file_encoding_valid` のような独立段階に分離する

### 「ファイルの最終更新日時が最近か」段階

- **却下理由**: 採用判定に「実行時刻」依存の要素を入れると、思想 P7 (再現可能な証跡) が成立しなくなる。同じツリーを同じ contract で再実行したとき、時間経過だけで ALLOW → DENY に変わるのは思想に反する
- **採用時の検討**: stale 検出が要求事項の場合は、contract に **固定基準時刻** または **生成元 manifest の checksum** を含める別段階として設計する (例: `manifest_freshness`)。これなら同一入力に対して結果が安定し、P7 を保てる

### 「JSON Schema 検証」段階 (verification_type: json_schema)

- **却下理由**: target/sample.txt はプレーンテキスト。JSON 検査の例は別サンプル (python-cli-pytest, Step 8) で扱う
- **採用時の検討**: 対象系が JSON ファイル生成器なら必須段階

### 「手動レビュー」段階 (verification_type: manual_check)

- **却下理由**: Phase 1 では manual_check を含む REQ は NOT_READY 扱い (Step 7 で実装、思想 P6 LLM 単独 ALLOW 禁止)。本サンプルは ALLOW を出すデモなので含めない
- **採用時の検討**: 思想 P6 と整合する別フェーズ (Phase 2 以降の human_attestation) で扱う

## 思想憲章のどの項目が特に効くか

- **P5 ALLOW/DENY の意味の限定**: S1, S2 両方の通過が ALLOW の条件。`gate.json.decision.meaning` で「Defined checks passed. This is not proof of total correctness.」を明示
- **P7 再現可能な証跡**: 各段階で `contract_ref` と `log_ref` を gate.json に記録 (Step 5 で実装)
- **P9 単一責任原則**: S1 と S2 は異なる責務 (存在 vs 内容) を担い、混ぜていない
- **P10 段階の可変性**: 推奨レンジ外でも、対象系と目的に合っていれば 2 段階で良い

## 段階間の依存関係

```
[start]
   ↓
  S1 (file_exists: target/sample.txt)
   ↓
  S2 (substring_match: target/sample.txt contains "hello")
   ↓
 [ALLOW]
```

線形依存 (DAG の最も単純なケース)。S2 は S1 が通った後でないと意味がない。

## 既知の限界

1. **入門用にしては抽象的**: 「sample.txt があって 'hello' が含まれる」は教育的だが、現実のプロジェクトには直接対応しない
2. **段階数が推奨レンジ外**: 実用例として真似ると validate-policy で警告が出る
3. **manual_check と command を含まない**: verification_type のフルセットを学ぶには別サンプルが必要
4. **複数 REQ の例ではない**: REQ-APP-001 だけ。複数 REQ の例は python-cli-pytest (Step 8) で扱う
5. **TDD フェーズの例ではない**: 全段階 ALLOW を前提。phase=red の例は Step 7 以降で扱う

## リファレンス出力の場所 (Step 5 補修)

手書きの期待出力は `evidence-reference/REQ-APP-001/latest/` に置いてある。`.quality-system/evidence/` は `qgb run` の destination であり、コミット対象の手書きリファレンスとは分離されている。

これは P7 (再現可能な証跡) と P9 (単一責任) の両方に沿った配置: 同じパスに「source of truth」と「runner の出力先」を同居させると、`qgb run` の destination がリファレンスを上書きしてしまう。Step 5 当初は同居させていたが、Codex レビューを受けて分離した。

## 関連

- 段階設計仕様 (`stage-design.md`) §9: 段階数の推奨レンジ
- 思想憲章 P9, P10
- 詳細設計 (`detailed-design.md`) §4-5: gate.json と contract.json のスキーマ
