# 作業記録: Phase 1 Step 6b (項目 0 完了、本体 1〜3 は未着手)

期間: 2026-05-30 〜 (進行中)

## 目的

Step 6a 完結後、Step 6b (verify / run --yes / atomic 化 / QGB_KEEP_RUNS warning) に着手しようとしたところで `qgb verify` の存在理由を巡る spec-review に発展した。その結果、当初 Step 6b の最初の実装対象であった `qgb verify` を **Phase 1 から撤回** する判断に至った。

本ジャーナルは、Step 6b の作業項目構成が大きく変化したことを含め、項目 0 (verify 撤回) を完了したところまでを時系列で残す。Step 6b 本体 (1: run --yes / 2: atomic / 3: QGB_KEEP_RUNS) は別途進む予定で、本書に追記する。

## Step 6b スコープの再定義

### 当初の Step 6b スコープ (Step 6a 完結時)

```
1. qgb verify (validate-policy + 軽量 run、揮発側のみ)  ← preflight API の最初の消費者として 6b の最初
2. qgb run --yes (実行前確認プロンプト)
3. _replace_dir_contents() の atomic 化 (Codex M4/M5)
4. QGB_KEEP_RUNS 不正値の warning (Codex L4)
```

### 再定義後の Step 6b スコープ (本コミット時点)

```
0. qgb verify 撤回の spec 反映 + cli.py stub 削除  ← 完了 (commit b9029ab)
1. qgb run --yes (実行前確認プロンプト)              ← 未着手
2. _replace_dir_contents() の atomic 化              ← 未着手
3. QGB_KEEP_RUNS 不正値の warning                    ← 未着手
```

「verify 実装」から「verify 撤回」に変わったのは Step 6b 着手後の spec-review によるもので、Step 5 / 6a と性質が違う。

## 項目 0: qgb verify 撤回 (commit `b9029ab`)

### 発端

Step 6b の最初の実装対象である `qgb verify` の curated skip の実装方針 (案 A: フラグ / 案 B: 関数分離) を Codex に設計相談したところで、ユーザーから「そもそも verify が要る理由」への問いが入った。

Claude は最初、verify の動機を「合格の記録しか残したくないから、開発途中でうまくいってないかもしれない間は verify」と言い換えた。

### 決定的な問い: 「それは理念から妥当か」

ユーザーの「その動機は philosophy や八百万から見て妥当か」という問いを受けて philosophy.md P5 を読み直すと:

> DENY は失敗ではなく、揺らぎを安全に受け止めた結果である。DENY を「失敗」「エラー」と扱う運用文書を作らない。

Claude が持ち出した「合格しか残したくない」= DENY を隠したい = DENY を失敗扱いは、**P5 違反**だった。この発見が議論の階層を「実装方針 (案 A/B)」から「動機の妥当性」へ引き上げた。

### spec 内部矛盾の発見

verify の正しい根拠を求めて `yaoyorozu-system-references.md` を読み直すと:

- references 5.3: 軽量入口の qgb 採用は **spec-review 未決**
- 下流 3 文書 (要件§12 / stage-design §3 / framework-shape): verify を**確定**として記載

未決のはずが下流で確定として取り込まれていた。さらに qgb の verify の定義 (「揮発側のみ = 記録を絞る」) と八百万の verify-req のずれの疑いも浮上。

### 八百万一次資料の精査 (Agent 並列 4 観点)

二次資料の限界が見えたため、memory の `review-process` 方針に従い、`yaoyorozu-system/core` リポジトリを Agent 並列 4 観点で精査した:

1. 入口コマンドの使い分け (ci-l1 / mihashira / verify-req / test-layers の実装)
2. evidence/artifacts 分離の経緯と DENY の扱い
3. ワークフロー文書からの想定使用シーン
4. verify-req の実体 (検査範囲 vs 記録)

P8 の歯止め (八百万の `.ai/` 命令文を qgb への指示として取り込まない) を各 agent に明示した。

調査の事実認定は `yaoyorozu-entry-points-investigation.md` に集約。要点:

- 八百万の軽量入口の軽さは **「検査範囲を絞る」** が本質 (記録の有無ではない)
- 八百万に **「合格だけ残す」思想は無い** (P5 と一致、ALLOW も DENY も latest に置く)
- 軽量入口を分ける動機は **「固定 6 段を毎回回すと遅いから一部を速く」**

### P3 緊張と REQ 分割への再配置

ユーザーの指摘:

> LLM 編集は全文が LLM を通り、要修正部分以外が改変されない保証がない。特定判定条件だけ追試すると、他の「すでに合格していたポイントが不合格になる」可能性はゼロではない。

これは発表資料の中心テーマ「揺らぎ」そのもの。部分追試は「触っていない部分は不変」を暗黙仮定するが、philosophy P3 (保証対象の転換 = コード不変を前提にしない) はそれを禁じる。

さらにユーザーは「フィードバック制御」の比喩で検討した上で、決定的な条件設定を出した:

> 大規模プロジェクトで部分部分が個別開発されるなら、それぞれに部分テストが設計され証跡が残るようにできるなら、verify を外してよい。結合テストはそれ用に作る。

これは「部分検証を実行時 verify でなく **REQ 分割 (設計時)** で解く」という再配置。各 REQ が自分の全 stage を走らせるので P3 緊張が構造的に消える。P9 (独立して再実行可能) と P1 (結合は結合 REQ として要求を立てる) が支える。

### 八百万原作者見解との一致 (3 経路の収束)

議論と並行して、八百万原作者 (wakaba 氏) から見解が示された:

> 階層化品質保証自体が、（部分追試の議論でいう）限定化した検証が e2e レイヤですら走る前提

階層化の各層 (責務限定) は e2e まで含めて全部走らせる前提であり、「限定化 = 責務分割 (設計)」であって「実行の省略」ではない。これは qgb 思想から導いた結論と一致した。

P8 の扱い: 著者見解は「指示」でなく「事実」として記録。意義は「思想憲章 (P3/P9/P1) からの結論」「利用者像からの結論」「原作者見解」の **3 経路が独立に同じ結論に収束**したこと。

### spec 改訂の実施

決定が固まった後、spec 改訂を一通り適用した。Codex に進め方を相談し、推奨を受けて:

1. `requirements_and_development.md`: §1.3 撤回履歴 / §F-008 を「採用判定の入口は qgb run 単一」に書き換え / §F-010 / 受け入れ条件 25→24 / CLI 一覧 / 運用フロー / マニュアル / §13
2. `stage-design.md`: ワークフロー図から verify 削除 / §3.1「軽量入口を持たない理由」新設 / §12 NOT_READY
3. `detailed-design.md`: コマンド表 / 2 系統出力表 / §12 Step 6b 再定義
4. `framework-shape.md`: §4 evidence 更新権限
5. `qgb/cli.py`: stub_commands から verify 削除
6. `qgb/core/evidence.py`: docstring
7. 新規 `yaoyorozu-entry-points-investigation.md`: 一次資料調査の事実
8. 新規 `journal/phase1-step6b-spec-review.md`: 議論と結論の経緯

phase 値 "verify" (TDD 局面、`qgb run --phase` の既定値) は CLI コマンドとは別物のため残し、要件§6 に用語注意を追記した。schema/fixture12件/decision.py の "verify" 値はリネームしない (Codex 助言: 波及コスト > 便益)。

### Codex 横断レビュー

memory の `review-process` 4 段プロセスに従い、改訂を一通り適用してから Codex に横断レビューを依頼。結果:

- **major 1**: `detailed-design.md` のコマンド表で `validate-policy` を「6a 実装済み」に変えたが、stub 説明文と近接していて誤読余地あり → stub 説明文に「現時点で init/validate/validate-policy/run は実 handler に差し替え済み」を追記
- **minor**: stage-design §3.1 の P3 反論に補強 1 文 (`qgb run は実行時点の対象 REQ に対し全 stage を同時点で再評価するため、未実行 stage の過去結果が現在の判定に混ざらない`) を追加

両方を補修したうえで 1 コミットにまとめた。Codex の助言「Revise Phase 1 spec to withdraw qgb verify」を踏まえてコミットメッセージは spec 改訂を前面に出した。

### memory に永続化

`verify-not-adopted.md` を project memory に追加し、再実装の歯止めとした。MEMORY.md インデックスにも登録。

## 振り返り (項目 0 段階)

### 1. 実装の細部より動機の妥当性が先

Claude は verify の curated skip 実装 (案 A/B) や gate.json の command フィールドという**細部**に降りていた。本当に先に問うべきは「verify の動機は思想憲章に照らして妥当か」だった。ユーザーの「理念から妥当か」の一問で、議論が正しい階層 (動機の妥当性) に引き上げられた。

設計判断は「どう作るか」の前に「なぜ・本当に要るか」を思想憲章で検証する。これは P1 (要求の外部化) の開発プロセスへの適用でもある。

### 2. 二次資料の限界、一次資料の価値

`yaoyorozu-references.md` は整理された二次資料で便利だが、「なぜそう設計したか」「軽さの本質は何か」は二次資料では曖昧だった。一次資料 (実装 + ワークフロー文書) に当たって初めて「軽さ = 検査範囲を絞る」が確定した。P7 (再現可能な根拠) は調査自体にも適用される。

### 3. memory の review-process が初めて実用に使われた

Step 6a 末尾で memory に書いた「観点別分散レビュー」が、今回の八百万一次資料調査 (Agent 並列 4 観点) と Codex 横断レビューで初めて実コードならぬ実プロセスとして使われた。

特に Agent 並列調査は (a) 八百万コードを 4 観点で同時に読む高速性 (b) 各 agent が独立観点で深掘りする精度 の両方を発揮した。手動で 4 観点を順に調べていたら半日コースだったところを 1 セッションで終えた。

### 4. ユーザーの問いが議論を正しく駆動した

この一連は Claude が主導したのではなく、ユーザーの問い —「verify が要る理由」「それは理念から妥当か」「軽い/重いはどこから来たか」「大規模プロジェクトの条件設定」「ヤオロズの構造はそもそも汎用提案フレームワークだから重い?」— が議論を正しい方向に駆動した。LLM は細部に走りやすく、「そもそも論」への引き戻しは人間判断が強い。これは Step 5 のスコープ challenge、Step 6a のコミット粒度判断と同型の学び。

### 5. spec 内部の未決→確定の取り込み漏れ

references 5.3 の「未決」が下流文書で「確定」として書かれてしまっていた。spec が多層 (思想憲章 → 要件 → stage-design → framework-shape) になっていると、上流の「未決」が下流で「確定」に化ける事故が起きる。**未決事項は下流に伝播するとき「未決」のまま運ばれるべき**、という規律が露呈した。

### 6. ハーネス側の異常 (court 混入)

spec 改訂作業の最中に、出力テキストに無関係な単語 `court` が繰り返し混入する現象が発生した。Claude Code feedback に報告 (X 上に同症状が複数いることをユーザーから情報提供)。途中でモデルを Opus 4.8 → Opus 4.7 に切り替え、その後は安定した。作業内容自体には影響なし。

## コミット履歴 (Step 6b 項目 0 まで)

```
b9029ab Phase 1 spec を改訂し qgb verify (軽量入口) を撤回する
2f0dbc5 Phase 1 Step 6a (本体 3 コミット + 補修 2 段) の作業記録を追加
```

## テストと品質指標の推移

| 段階 | テスト件数 | ruff |
|---|---|---|
| Step 6a 完結時 | 238 | clean |
| 項目 0 (verify 撤回) 完了 | **238** | clean |

verify 撤回は CLI stub の削除のみで、本体テストへの影響はゼロ。phase 値 "verify" を残したので fixture 12 件にも影響なし。

## 関連 Issue / 文書

- `development/docs/yaoyorozu-entry-points-investigation.md` (一次資料調査の事実認定)
- `development/docs/journal/phase1-step6b-spec-review.md` (verify 撤回の議論経緯、本書とは別の独立文書)
- `development/docs/philosophy.md` v1.0 (P3 / P5 / P6 / P9 が本期の判断軸)
- `development/docs/stage-design.md` §3.1 (verify 不採用、REQ 分割の利用者向け指針)
- `~/.claude/projects/.../memory/verify-not-adopted.md` (再実装の歯止め)

## 項目 1〜3 (Step 6b 本体) の作業記録

verify 撤回 (項目 0) に続いて、技術的補修 3 項目を順次実装した。

### 項目 1: `qgb run --yes` フラグ + 確認プロンプト (commit `980c733`)

要件 §F-008 (要件§448 「qgb run は実行前に確認プロンプトを出す、--yes でスキップ可」) の実装。

設計判断:

- 既定 (TTY) 時は `Proceed? [y/N]:` を出し、`y` / `yes` のみ続行、それ以外 NOT_READY (curated evidence は触らない)
- `--yes` で完全スキップ
- 非 TTY (CI / パイプ) で `--yes` 未指定 → 明示的に abort + 「--yes を付けろ」ヒント。CI で気付かず走るのを防ぐ
- preflight 成功後に確認 (失敗時は確認する意味がないので即 NOT_READY)
- プロンプト出力先は stderr (`--json` の stdout を汚さない)

既存テストへの影響: `test_run_generic_minimal.py` の `qgb run` 呼び出し 27 箇所を `--yes` 付きに更新。自動実行コンテキストだから `--yes` が必要、で正しい。

Codex 横断レビュー指摘 (1 件、medium):

- `--json` モードで abort 経路も JSON 出力にすべき (preflight NOT_READY と同じ契約)

→ `_abort_to_json()` を追加して `reason` フィールド (`declined` / `non_tty_without_yes`) で区別。

新規テスト 12 件。テスト 238 → 250 件。

### 項目 2: curated/latest/ の atomic 入れ替え (commit `e19a8b5`)

Codex Step 5 M4/M5 の指摘への対応。直接書き込み式 (`_replace_dir_contents` → write_text 連発) を、テンポラリ + rename 方式に切り替える。

設計 (`_atomic_swap_curated`):

```
0. recovery: latest/ 欠落 + latest.old-* 残存 = 前回中断 → old を戻す
1. latest.tmp-<run_id>/ にフル一式 (gate.json/summary.md/stages/*.log)
2. 既存 latest/ → latest.old-<run_id>/ にリネーム
3. latest.tmp-<run_id>/ → latest/ にリネーム
4. latest.old-<run_id>/ をベストエフォート削除
```

失敗時:

- step 1 失敗: latest/ 無傷、tmp は調査用に残す
- step 3 失敗: old を final に戻して前回 latest を復元してから raise

保証する性質:

- reader が中間状態 (stages 空 + 古い gate.json) を観測する窓が無い
- 書き込み中の中断で前回の合格証跡が失われない

Phase 1 out-of-scope (Codex 横断レビューで明示的に保留した項目):

- fsync / 電源断耐性 (Phase 2 課題)
- 並行書き込み (single-writer 前提を docstring に明記)

Codex 横断レビュー指摘 (5 件):

| 重要度 | 内容 | 対応 |
|---|---|---|
| High | fsync 無し、power-loss 耐性なし | Phase 2 out-of-scope、docstring に明記 |
| Medium | 起動時 recovery (`latest/` 欠落 + `latest.old-*` 残存) が無い | `_recover_orphan_latest()` 追加 |
| Medium | 並行書き込み未対応 | single-writer 前提を docstring に明記 |
| Medium | Windows reader 握り → rename 失敗 | docstring に明記、対処は前回 latest 保持 |
| テスト | tmp→final 失敗復元の直接テストが無い | テスト追加 |

新規テスト 7 件。テスト 250 → 257 件。

### 項目 3: QGB_KEEP_RUNS 不正値の warning (commit `234177e`)

Codex Step 5 L4 の指摘への対応。非整数 / 負値 / 0 が silent fallback で気付けなかったので、stderr に warning を出して既定値 10 にフォールバックする仕様化。

仕様:

| 入力 | 結果 | warning |
|---|---|---|
| 未設定 / 空文字 | 既定 10 | なし |
| 1 以上の整数 (前後空白許容) | 採用 | なし |
| 非整数 / 0 以下 / 空白だけ | 既定 10 | あり |

警告文に raw 値 (`repr`)、理由、fallback 先を含めて利用者が即判別できるようにする。

Codex 横断レビュー: 中程度以上の指摘なし。低優先度で `" 5 "` (前後空白付き整数) のテスト追加のみ反映。

新規テスト 8 件。テスト 257 → 266 件。

## コミット履歴 (Step 6b 完結)

```
234177e Step 6b 項目 3: QGB_KEEP_RUNS 不正値の warning
e19a8b5 Step 6b 項目 2: curated/latest/ の atomic 入れ替え
980c733 Step 6b 項目 1: qgb run --yes フラグ + 確認プロンプト
fedb106 Step 6b 項目 0 (qgb verify 撤回) の作業記録を追加
b9029ab Phase 1 spec を改訂し qgb verify (軽量入口) を撤回する
```

## テストと品質指標の推移

| 段階 | テスト件数 | ruff |
|---|---|---|
| Step 6a 完結時 | 238 | clean |
| 項目 0 (verify 撤回) 完了 | 238 | clean |
| 項目 1 (--yes) 完了 | 250 | clean |
| 項目 2 (atomic) 完了 | 257 | clean |
| 項目 3 (KEEP_RUNS warning) 完了 | **266** | clean |

## 振り返り (項目 1〜3)

### 7. Codex 連携の許可設定整理

項目 2 作業中に、Codex wrapper を呼ぶ経路の許可プロンプトが頻発した。原因は:

- Write tool で `/tmp/...` に書けない (許可は Windows ネイティブ TEMP のみ)
- `(echo; echo; git diff) > /tmp/file` の subshell + redirect が許可テンプレートにマッチしない
- Skill(ask-codex-with-context) は許可されているが、skill 内部の `Bash(powershell ...)` は別途許可必要
- `rm -f /c/Users/vz7a-/AppData/Local/Temp/...` の rm 傘が無かった

settings に以下を追加して、Codex 連携サイクル (Write context → wrapper 呼び出し → rm context) を全てプロンプト無しに:

- `Bash(powershell -ExecutionPolicy Bypass -NoProfile -File *codex-wrapper.ps1*)` (wrapper パス固定の傘)
- `Bash(rm -f /c/Users/vz7a-/AppData/Local/Temp/*)` (Windows TEMP の rm 傘)

memory の `codex-context-files.md` に動線を永続化。今後同じ作業で躓かない。

### 8. Codex wrapper の UTF-8 出力問題

項目 2 のレビュー取得時に Codex の日本語応答が文字化け。原因は wrapper の `[Console]::OutputEncoding` が既定の Shift-JIS (OEM 932) になっていて、Bash msys 経由でパイプすると UTF-8 解釈で壊れる。

wrapper の param 直後に `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` を追加して解決。修正は wrapper の元リポジトリ ([Yumeno/add_codexcli](https://github.com/Yumeno/add_codexcli)) に [issue #12](https://github.com/Yumeno/add_codexcli/issues/12) として起票。

### 9. Codex 横断レビューが out-of-scope 判断の根拠になった

項目 2 で Codex が指摘した「fsync が無いので power-loss 耐性が無い」は技術的には正しい。しかし Phase 1 MVP のスコープは「reader 不整合観測の防止」が主目的で、power-loss 耐性は別レイヤ。レビュー結果を **対応する / Phase 2 に倒す / docstring で明示的に out-of-scope と書く** に三分類して整理することで、「指摘されたから全部直す」を避けられた。これは Step 5/6a でやった「LLM の細部走り」を人間判断で引き戻すパターンの自動化。

### 10. memory が permission 設定の方針として効いた

「ワイルドカードを広げすぎない」「副作用の形が決まっている粒度」という Step 6a の方針が memory に書かれていたおかげで、項目 2 で許可プロンプト連発を解決するときに **`Bash(powershell *)` のような広い傘を貼らない判断** ができた。代わりに `Bash(powershell -ExecutionPolicy Bypass -NoProfile -File *codex-wrapper.ps1*)` のように **wrapper パスに固定** した傘を選んだ。memory が方針の連続性を担保した実例。

## Step 6b 全体の総括

verify 撤回 (項目 0) で Phase 1 のスコープを **「採用判定の実行入口は qgb run 単一」「部分検証は REQ 分割で解く」** に確定させ、項目 1〜3 で run の運用品質を補修した:

- 項目 1: 実行前確認 (誤発射防止)
- 項目 2: curated/latest/ の不整合観測 / 破壊状態回避
- 項目 3: 環境変数の設定ミス検知

これにより `qgb run` は Phase 1 MVP として「人と CI 両方から安全に使える」「中断耐性がある (前回証跡を破壊しない)」「設定ミスが silent fail しない」状態になった。次は Step 6c (`detect` + `adapters/python` + `adapters/generic`) でターゲット言語検出に進む。
