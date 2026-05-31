# design-notes (examples/python-cli-pytest)

このノートは `examples/python-cli-pytest/` がなぜ現在の 3 段階構成に
なっているかを記録する。設計例パックの目的は「正解の例」を見せること
だけでなく、**なぜそうしたか、なぜ他の選択肢を採らなかったか** を残
すこと。

## 対象系の特徴

Python の小さな CLI ツール + pytest 単体テスト群。setuptools build
backend、PEP 621 metadata、editable install で利用する想定。検査対象
は次の 3 つの軸を持つ:

- **実装の正しさ** — CLI が argparse で受けた引数に対して正しい動作を返すこと。
- **CLI 表面の起動性** — `python -m demo_cli --help` がエラーなく
  exit 0 で完了すること (entry point / `__main__.py` が壊れていない)。
- **新規利用者の onboarding** — README に install 手順が文書化されている
  こと。

これらは「Python CLI プロジェクトが最低限満たすべき品質」であり、
production 規模の CLI でも本質的にこの 3 軸は残る。

## 段階数の決定根拠

stage-design.md §9 が **3〜7 段階** を推奨レンジとしている。本 example
は推奨レンジの **下限である 3** をあえて選んだ。

理由:

- 2 段階以下にすると責務が混ざる (例: pytest と `--help` を 1 stage に
  まとめると S1 が「内部実装 + 起動性」を二重判定する形になり、P9 単一
  責任原則違反になる)。
- 4 段階以上にすると、type-check / lint / build artefact 完全性などが
  混ざってきて、本 example の最小性を逸脱する (それらは Phase 2 以降の
  adapter inventory で扱う想定)。
- 3 stage は「最小だが責務が分離している例」として diff レビュー時に
  目視しやすい。

## 採用した段階と理由

| stage | verification_type | 単一責務 | なぜ |
|---|---|---|---|
| S1 | `command` | pytest 群が exit 0 で完了 | 実装本体の回帰検知。argparse の分岐や greet() のロジックも S1 が見る |
| S2 | `command` | `python -m demo_cli --help` が exit 0 | CLI 表面が壊れていないこと。pytest が通っても、エントリポイント (`__main__.py`) が消えていれば人が触ったときに壊れる |
| S3 | `substring_match` | README に "Installation" が含まれる | 新規利用者の onboarding。コード本体の品質ではなくドキュメント品質を独立に担保 |

S1 と S2 を分けるのは意図的。pytest はテストランナーとして対象コードを
exec するので、`__main__.py` が削除されていても S1 は通り得る。しかし
利用者が叩くのは `python -m demo_cli` という別の経路で、ここが壊れて
いれば届く前に転ぶ。S2 はその経路を「外側から」叩いて確認する。

## 採用しなかった段階と理由

検討したが Phase 1 ではあえて落とした stage:

- **type-check (mypy / pyright)** — 静的型検査。S1/S2 と並列に走らせ
  たいが、本 example は「最小例」の位置づけ。Phase 2 adapter inventory
  が型ツール選定を扱う想定で送る。
- **lint (ruff / flake8)** — 同上。
- **build artefact 完全性 (wheel build)** — `pip install -e .` で十分
  動作するため、wheel/sdist の完全性まで Phase 1 で要求する必然はない。
- **cross-platform CLI smoke** — Windows / Linux / macOS で `--help`
  が同じ挙動を返すか。NF-004 の文脈で重要だが、現状 Phase 1 の qgb
  runner は cross-platform 実行をサポートしないので、stage として
  立てても検査側が走れない。
- **performance / memory** — 小さな CLI に対して定量計測する意味が薄
  い。Phase 2 以降の adapter で扱う。
- **coverage threshold** — 「N% 以上ならパス」型の advisory metrics。
  Phase 1 の判定モデルは「定義済み必須検査が通る」であり、しきい値型は
  Phase 2 の knowledge / waiver 連携で扱う。

## 思想憲章のどの項目が特に効くか

- **P5 (DENY は失敗ではない)** — S1 (pytest) が DENY を返すのは「再
  生成・再判定の signal」。pytest を失敗扱いするのではなく、テストを
  修正して再 run する入口として扱う。
- **P6 (LLM 単独 ALLOW 禁止)** — 本 example の全 3 stage は機械的検査。
  manual_check は 1 つも含めない。S3 (README 文字列) は LLM の主観で
  なく単純 substring 検査として外部化されている。
- **P7 (再現可能な証跡)** — S1/S2 は `python -m ...` で argv を明示
  し、`os.environ.copy()` で env を継承する。reference gate.json に
  exit_code を残しているため、後日の auditor が同じ command を走ら
  せて exit_code が一致するか確認できる。
- **P9 (単一責任原則)** — S1 (実装) / S2 (起動性) / S3 (文書) の責務
  分割。1 stage に複数責務を載せない。

## 段階間の依存関係

```
S1 (pytest)            S3 (README substring)
  ↓ depends_on
S2 (CLI --help)
```

- **S2 → S1**: pytest が通らない実装で `--help` を回しても無意味。
  S1 失敗時は S2 は skip 扱い (`failed` として記録、実行はしない) で
  下流の認知的負荷を減らす。
- **S3 ⊥ {S1, S2}**: README の installation 記述は実装の状態と独立。
  実装が壊れていても "How to install" が書かれていれば S3 は passed。
  これは onboarding 品質という別軸の責務を独立に判定するため。

## 既知の限界

- **`command` runner のメモリ上限**: `subprocess.run(capture_output=True)`
  は stdout/stderr をフルバッファするため、pytest が巨大な出力を出すと
  メモリを食う。Phase 1 では `_tail_truncate()` が 64 KiB に絞る (ログ
  保存 cap であり、実メモリ cap ではない)。詳細は `qgb/core/runner.py`
  の docstring 参照。
- **Windows `.bat` / `.cmd` 経路**: `python -m demo_cli` 形式を使うこと
  で `.bat` 経由の argument escaping 問題を回避している。設計判断とし
  て、本 example の `command` は常にインタプリタ呼び出し経由とする。
- **`os.environ.copy()` で env 全継承**: Phase 1 では env を絞らない。
  Phase 2 で allowlist / secret masking が入る予定。
- **pytest 自体の存在前提**: `python -m pytest` が解決できる環境を要求
  する。`pip install -e ".[test]"` で `pytest` を入れること (README に
  明記)。
- **`python` PATH 前提 (Step 8 統合レビュー W3)**: S1/S2 contract は
  `["python", "-m", ...]` を literal に実行する。Windows で `py` のみ
  使う環境 (PATH に `python.exe` が無い) では S1 で command-not-found
  になる。これは「target project が用意した toolchain を qgb は再解釈
  しない」設計判断の結果。`py -3` で書き換えると POSIX 環境を壊し、
  `sys.executable` を使うと contract から「何を実行するか」の説明力
  が落ちる。Windows で `py` のみの場合は contract をローカルに調整
  して run する (README 末尾の Windows note を参照)。
- **pytest 出力の非決定的部分 (Step 8 統合レビュー Ph1)**: pytest が
  stdout に出す "4 passed in 0.02s" の実行時間は run ごとに揺れる。
  stage log の文字列は完全一致しないが、それで判定が左右されること
  はない: durable な signal は `exit_code: 0` と stage の
  `result: passed` であり、こちらは reproducible。auditor が
  evidence-reference と新規 run を比較するときは log 全文 diff では
  なく exit_code と result を見る。
