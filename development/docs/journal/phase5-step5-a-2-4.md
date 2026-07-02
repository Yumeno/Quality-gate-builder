# Phase 5 Step 5.a-2-4 完結ジャーナル: command authoring protocol + capability-based dispatch

完結日: 2026-07-02 (実機 fixture 検証 + Fable 5 横断レビュー反映を完結前 fix として合流、最終確定)
着手前判断: `phase5-step5-a-2-4-prejournal.md` (commit `07de0c7`)
前提: Step 5.a 全体 K=2 達成 (commit `ebee96f`)
着手契機: K=2 r1 fix 進行中の user 提起 (日本語文書執筆プロジェクトの .ps1 契約 + PowerShell 5 + 日本語 encoding 問題への構造的解決)

## 1. Step 5.a-2-4 で確立した境界 (恒久記録)

### 1.1 構造 trigger による command 規律適用 (θ + ι 反映)

「日本語」「Windows」「.ps1」等のキーワード trigger ではなく、**「verification_type=command の contract を新規作成 / 既存編集する」という構造的事象** で θ command authoring protocol を必ず適用する設計に切替。これは Codex 設計再検討レビュー (`codex_ctx_p5_step5a-2-x_jp-docs-design_review_20260628-180821.txt`) の中核指摘。

#### θ: 7 step protocol (body.md §6.5)

```
1. context 取得 (target OS / shell / locale / runtime version)
2. verification type 選択 (command 以外で十分なら避ける)
3. runtime 解決 (PowerShell 5 vs 7、bash vs zsh 等を一意確定)
4. script / argv 生成 (runtime 規約に従って完全明示)
5. runtime-specific preflight (§12.5.5 capability checklist 適用)
6. qgb check リハーサル + U+FFFD 検出 (κ mojibake sentinel)
7. evidence 確認
```

#### ι: capability-based dispatch checklist (body.md §12.5.5)

作成物性質 (= script file の拡張子 / runtime 種別) で adapter checklist を分岐:

- PowerShell 5 / 7 (Windows native): BOM / OutputEncoding / argv / -NoProfile 等
- bash / sh (POSIX): shebang / executable bit / locale / 改行 LF
- Python (CPython 3.7+): UTF-8 mode / sys.stdout.reconfigure / PYTHONUTF8
- Node.js (LTS 18+): ESM / process.stdout / package.json engines
- Go binary / Rust binary / compiled: 絶対 path / version 記録 / binary 側 encoding 責任
- Markdown lint / link checker / 文書系 tool: 上記 runtime の checklist 適用

adapter は **skill 内 strategy として限定**、qgb 本体への対象検出復活はしない (framework-shape §5 境界遵守)。

### 1.2 skill 内 lint (proposal adopt 前の機械検査)

`skills/source/lint/check-command-contract.{ps1,py}` を skill 同梱で提供:

- **C1**: script 拡張子 ↔ confirmed runtime の整合
- **C2**: PowerShell 5 + 非 ASCII `.ps1` の UTF-8 BOM 有無
- **C3**: `.ps1` を `shell=False` の argv で直接起動の検出
- **C4**: PowerShell `.ps1` の `[Console]::OutputEncoding` 初期化漏れ
- **C5**: confirmed runtime executable の PATH 有無
- **C6**: qgb check stage log の `U+FFFD` (= κ mojibake sentinel)

skill agent が `qgb design-stages adopt` 前に自動実行、exit 0 で adopt 推奨。lint 結果は **advisory** (philosophy P6、ALLOW 判定根拠にしない)。

### 1.3 設計例 fixture (ζ): examples/japanese-docs-pwsh/

日本語文書執筆 + Windows PowerShell 5 + 日本語 `.ps1` 契約 の qgb 設計例を新設。skill (LLM) が few-shot として参照可能:

- 4 段階 (link / glossary / style / structure)
- 全 contract で `runtime: powershell-5` + 完全 argv 明示
- `.ps1` script は **pure ASCII + Unicode escape** で BOM 不要 (利用者が選べる 2 代替策 (BOM 付き UTF-8) の片方を fixture として demonstrate)
- 全 script 冒頭で `[Console]::OutputEncoding = UTF8` + `$ErrorActionPreference = Stop`
- `design-notes.md` で θ/ι 適用例 + アンチパターン回避を明示

### 1.4 mojibake sentinel (κ)

qgb check / run 後の stage log での **U+FFFD (replacement character) grep** を:

- body.md §13.3.5 で advisory review 観点に追加
- skill lint script (C6) で機械検査
- 完結 journal §6.6 dogfooding 保守シナリオ (項目 6 / 7) で逆方向検証 (Console.OutputEncoding 削除で `U+FFFD` 出現確認)

cp932→UTF-8 誤 decode の多くを安価に検出可能。

### 1.5 「日本語固有問題」でなく「command 共通 invariant」

Codex 視点転換の中核: ユーザー提起の論点は **日本語文書執筆 + Windows + PowerShell 5** 固有問題ではなく、**verification_type=command の生成時に runtime 規律を組み込む**というすべての command contract 共通の invariant。日本語 PowerShell はその 1 具体化。

この視点転換により、本 Step で確立した protocol / checklist は将来の他 runtime (Ruby / Perl / 独自 binary 等) にも同型に適用可能な拡張可能設計となった。

### 1.6 完結判定の根拠: 机上 K=2 から実機 fixture 検証への転換

本 Step の完結判定は「Codex 机上 K=2 の達成」ではなく「実機 fixture による運用基準達成」を根拠とする。この判断経緯と論理を恒久記録として残す。

#### 机上 K=2 の収束不能

Codex 横断レビューは r1〜r6 の 6 ラウンドを要し、finding 系列は 5→5→4→1→2→2 と収束しなかった。r4 以降は finding 数こそ 1〜2 件に減少したが、r5・r6 でそれぞれ新たな実装上の欠陥 (位置依存ロジックの false positive、PS7 略形の見落とし) が発見されており、「次のラウンドで 0 件になる」という見通しが立てられない状態だった。これは lint script が位置依存・runtime 分岐・略形対応を多く含む複雑な実装であることに起因する。

#### 実機 fixture 検証への転換

user 判断により、机上レビューを継続する代わりに `tests/fixtures/lint_command_contract/` を新設して実際に PS5.1 上で実行する方針に転換した。この 1 ラウンドで、机上 6 ラウンドが見逃していた lint bug を複数捕捉した:

- `script_explicitly_provided` flag 欠如による derive 経由 path 比較 false positive
- `required_flag_synonyms` 未定義による省略形が required_flags を通らない問題
- `ep_aliases` 未定義による EP 重複・隣接検査の省略形対応漏れ
- PS5.1 test runner 固有の罠 (null array・ErrorRecord 化・stdout+stderr 混合)

実機 PS 5.1.26100 で 7 fixture すべてが PASS したことで「運用上問題ない」基準を機械的証跡として担保した。

#### Fable 5 横断レビュー指摘の合流

Fable 5 横断レビュー (`phase5-fable5-cross-review.md`) の指摘 D-1/D-2/D-3 は、完結前 fix として本 Step に合流させた。D-2 (PS 実装の fixture 未検証) は「実機で担保」を宣言した完結判定の根拠の穴そのものであり、完結処理の前提に昇格した。D-1 (body.md §10.1 の `pip install quality-gate-builder` — 供給網リスク) および D-3 (typo) は同一 commit で修正した (commit `44159cd`)。D-2 対応として lint Python・PS 両実装を 21 判定全 PASS まで拡張した (commit `a65c6c5`)。

#### philosophy との整合

この完結判定の切替は philosophy P6 (LLM 主観評価を ALLOW の単独根拠にしない) および P7 (監査可能性・再現性) に忠実な判断である。Codex 机上レビューは advisory であり、それが何ラウンド続いても「再現可能な機械的証跡」の代替にはならない。実機 fixture が示す 21 判定全 PASS こそが P7 の要求する監査可能証跡である。この判断パターンは auto-memory `review-process` に「実機 fixture 先行の原則」として一般化済みである。

## 2. Step 5.a-2 完結 journal §2 旧→新対応表への追記 (Step 5.a-2-4 反映)

Step 5.a-2-4 で発生した修正は **既存 spec drift の訂正ではなく新規追加** が中心で、5.a-2 完結 journal §2 旧→新対応表に追記する形より、本書 §1 で **新規確立した境界** として記録。

ただし 5.a-2 完結 journal §6.6 dogfooding 保守シナリオに追加項目 (PowerShell 5 + 日本語 .ps1 シナリオ、項目 5-9) を追記したのは spec 拡張なので、5.a-2 完結 journal 側でも明示済。

## 3. Step 5.a-2-4 commit chronology

| commit | 段階 | 内容 |
|---|---|---|
| `07de0c7` | 段階 1 | prejournal 風設計判断記録 |
| `7aa9ad4` | 段階 2 | body.md §6.5 command authoring protocol (θ) |
| `260e517` | 段階 3 | body.md §12.5.5 capability-based dispatch checklist (ι) |
| `153a2b1` | 段階 4 | skills/source/lint/check-command-contract.{ps1,py} + README.md (新設) |
| `2dd22cb` | 段階 5 | examples/japanese-docs-pwsh/ 新設 (18 files、ζ fixture) |
| `9c57de8` | 段階 6 | body.md §13.3.5 mojibake sentinel (γ-lite + κ) + 完結 journal §6.6 拡張 |
| `db34758` | 7 | 5.a-2-4 完結 journal (本書、初版) |
| K=2 r1 fix commit | 段階 8 K=2 r1 fix | (a) lint script Python + PowerShell の C1/C2/C4 必須化 (script path 解決失敗時、PowerShell runtime のみ hard finding、他 runtime は skip) (b) C3 完全明示 argv 検証強化 (invoker basename 完全一致、runtime ↔ invoker 整合、-File 後 script path 検査) (c) C4 必須/任意分離 ([Console]::OutputEncoding 必須、$OutputEncoding advisory) (d) C5 advisory 化 (利用者 host との差を accept) (e) acceptance-matrix.md に lint 同梱規律を正本化 (digest カテゴリ 5 = lint、合計 8 カテゴリへ番号繰り下げ、生成物表に lint/ 行追加) |
| K=2 r2 fix commit | 段階 8 K=2 r2 fix | (a) PowerShell sibling C5 advisory parity 修正 (戻り値を hashtable で構造化、空配列 collapse 回避) (b) C3 -ExecutionPolicy Bypass 隣接検査追加 (Python + PS) (c) -File path 整合検査を layered 化 (absolute → full path 比較、relative → basename equality、Phase 5 では絶対 path 渡し時のみ strict 比較、relative は 5.b dogfooding に委ねる) (d) Python に basename_universal / has_path_separator / normalize_path_for_compare helper 追加 (ntpath + PureWindowsPath で cross-platform Windows path 解釈) (e) acceptance-matrix.md カテゴリ番号繰下げ漏れ修正 (line 92, 118 の「カテゴリ 7」を「カテゴリ 8」に) (f) lint/README.md + body.md §13.3.5 に C5 advisory 化を明文化 |
| K=2 r3 fix commit | 段階 8 K=2 r3 fix | (a) -File 以降に host option を許可する欠陥修正: host_option_lowercase set を定義、-File より後ろに -NoLogo / -NoProfile / -NonInteractive / -ExecutionPolicy 等が現れたら finding (Python + PS) (b) 重複 -ExecutionPolicy / -File 検出: -ExecutionPolicy / -File は exactly one occurrence (Python + PS) (c) option casing parity: Python を case-insensitive 化 (commandLower 配列を生成、required_flags も lowercase、host option set も lowercase)、PowerShell sibling と完全 parity 達成。`-file` (小文字) でも derive_script_from_command が認識 (d) README C3 説明を実装に合わせて layered 比較を明示 (absolute → full path、relative → basename) + 新検査項目 (host option 前後 / 重複 / 隣接) を列挙 |
| K=2 r4 fix commit | 段階 8 K=2 r4 fix | -Command / -EncodedCommand と -File の排他チェック追加: PowerShell 仕様で `-Command` / `-EncodedCommand` は実行モードを指定する別 host parameter、`-File` と一緒に渡すと -Command 本体が実行され -File 以降は文字列引数扱い (script は実行されず exit 0、silent failure)。両者が argv に共存したら C3 finding。実機確認で `-Command "Write-Output COMMAND_RAN" -File script.ps1` で `COMMAND_RAN -File script.ps1` が出力 + script 不実行 + exit 0 を確認。Python + PowerShell + README + 完結 journal を同期 |
| K=2 r5 fix commit | 段階 8 K=2 r5 fix | (a) **排他判定を -File より前の位置に限定**: r4 実装は `-Command` が argv のどこにあっても排他 finding を出すため、`-File script.ps1 -Command value` (script 引数として渡る `-Command`) で false positive。fix: 最初の -File より前の位置に出現した execution-mode option のみ排他 finding (Python + PS) (b) **PowerShell 省略形 (-c / -ec) も検出**: 実機 PS5.1 で `-c "..." -File script.ps1` も silent failure 経路。fix: allowlist 方式に変更、-File より前は許可 host option (展開済の略形一覧 -nol/-nop/-noni/-noe/-ex/-ep/-w 等) と未承認 token を区別、execution-mode option (`-command` / `-c` / `-encodedcommand` / `-ec`) は専用の排他 finding、それ以外の未承認 token は generic allowlist failure。Python + PS + README + 完結 journal を同期 |
| K=2 r6 fix commit | 段階 8 K=2 r6 fix | (a) **PS7 exec-mode 略形を追加**: r5 まで PS5/7 共通の exec-mode set だったため PS7 公式の `-e` (EncodedCommand 略形) と `-CommandWithArgs`/`-cwa` を見逃していた。fix: `exec_mode_options_by_runtime` を runtime 別 dict 化、PS5 = {-command/-c/-encodedcommand/-ec}、PS7 = PS5 セット + {-e/-commandwithargs/-cwa}。help-mode (-help/-?//?) も exec-mode 相当として両 runtime で排他扱い (b) **allowlist を PS5/7 runtime 別公式 host option 網羅**: r5 までの allowlist は PS5/PS7 共通だったため、PS5 の `-EncodedArguments`、PS7 の `-Interactive`/`-i`、`-Login`/`-l`、`-ConfigurationFile`、`-CustomPipeName`、`-NoProfileLoadTime`、`-SettingsFile`/`-settings`、`-SSHServerMode`/`-sshs`、`-WorkingDirectory`/`-wd`/`-wo`、`-Version`/`-v` を未知扱いして false positive。fix: `allowed_host_options_by_runtime` を runtime 別 dict 化、PS5/PS7 公式 docs (about_powershell_exe / about_pwsh) を網羅。help-mode は exec-mode 側に移動 (-File と両立しない実運用に整合)。PS7 の -OutputFormat 略形 -o/-of 化、-Version の略形 -v 追加。Python + PS sibling parity 確認 (PS5 -EncodedArguments / PS7 -e / PS7 -Login -WorkingDirectory / 既存 example S1 と -c 略形回帰、全 ok) |
| `b29ceef` | 段階 9 実機 fixture | PS5.1 実機 fixture テスト追加 + 実機発見 lint bug 修正 (7 fixture、lint Python 側の derive path 比較 false positive / required_flag_synonyms / ep_aliases を修正、7/7 PASS) |
| `44159cd` | 段階 10 Track 1-2 | Track 1-2: body.md pip install 供給網リスク修正 + typo (Fable 5 レビュー D-1/D-3) |
| `a65c6c5` | 段階 11 Track 1-1 | Track 1-1: fixture runner を lint 両実装 parity 検証に拡張、21 判定全 PASS (Fable 5 レビュー D-2) |

## 4. 機械検証実績

- pytest test_step9_docs.py: 各段階で 15 passed 維持 (前 commit から件数変動なし)
- skill lint script: good contract → exit 0 / bad contract → exit 1 + 適切な finding (C3 等)
- example PowerShell scripts: 全 3 script (link / glossary / style) 実行で exit 0
- example contract 全 3 件 (S1 / S2 / S3 PowerShell 5) を lint で検証 → 全て OK

## 5. Codex 設計再検討レビュー受領 (Step 5.a-2-4 着手契機)

| context | 主要指摘 |
|---|---|
| `codex_ctx_p5_step5a-2-x_jp-docs-design_review_20260628-180821.txt` | 推奨 (η改) = θ + ι + β-lite + ζ + γ-lite + κ、視点転換 4 点 (日本語固有問題でない / 構造 trigger / 組み合わせ一般化 / 混ぜるな) |

Codex の指摘どおり、K=2 r1 fix と分離して独立 Step として実装 (「混ぜるな」遵守)。

## 6. 完結後 K=2 (本 Step 単独レビュー) 方針

Step 5.a 全体 K=2 r6 達成済の運用基準 (「実際のプロジェクトとして動かしたときに運用上問題ない / 複数実装あり得るがどちらでもよい」 + 3 分類判定 (必須 / 5.b 送り / Phase 6+ 送り)) を継承。

本 Step 単独で Codex 横断レビューを実施、新規必須 fix ゼロまで継続。Step 5.a 全体 K=2 (r6 達成済) は影響しない (本 Step の追加修正は別系統として扱う、ただし 5.b 着手前提として両方達成必須)。

## 7. 次の Step 申し送り

### 7.1 5.b 着手前提 (Step 5.a 全体 + Step 5.a-2-4 統合)

Step 5.a 全体完結 journal §6.3 の 16 項目に加えて、Step 5.a-2-4 で確立した以下を 5.b 実装時の必須前提に追加:

- **skill 内 lint script の同梱**: `skills/source/lint/check-command-contract.{ps1,py}` + `lint/README.md` を `dist/skills/{full,split}/{claude,codex}/lint/` に copy
- **`build_input_digest` カテゴリ 4** (同梱 hook) と同様の扱いで lint script を digest 対象に含める
- **examples/japanese-docs-pwsh/** は 5.d / 5.e dogfooding fixture として使用

### 7.2 5.d / 5.e dogfooding 拡張 (完結 journal §6.6 既追加済)

- A1' 構造の保守シナリオ (項目 1-4、既存)
- Windows + PowerShell 5 + 日本語 .ps1 シナリオ (項目 5-9、本 Step で追加)

### 7.3 Phase 6+ 検討項目 (本 Step で out of scope と判定)

- `contract.encoding` field (ε 候補): qgb 本体改修、Phase 5 では skill 側で吸収済のため Phase 6+ 実需待ち
- `contract.runtime` field の qgb 本体 schema 化: 現状は skill 側のみで判断、qgb 本体は受け流し。Phase 6+ で利用者運用が安定したら schema 化検討
- 他 runtime adapter checklist の拡張 (Ruby / Perl / Lua 等): 実需が出てから追加

## 8. 関連ファイル

- prejournal: `development/docs/journal/phase5-step5-a-2-4-prejournal.md` (commit `07de0c7`)
- 中間表現変更: `skills/source/body.md` §6.5 + §12.5.5 + §13.3.5 (commit `7aa9ad4` / `260e517` / `9c57de8`)
- skill 内 lint: `skills/source/lint/check-command-contract.{ps1,py}` + `README.md` (commit `153a2b1`)
- 設計例: `examples/japanese-docs-pwsh/` (commit `2dd22cb`)
- Codex 設計再検討レビュー context: `codex_ctx_p5_step5a-2-x_jp-docs-design_review_20260628-180821.txt`
- 上流 Step 5.a 全体完結 journal: `development/docs/journal/phase5-step5-a-2.md` (commit `acbd64f` + K=2 fix 6 commit)
- Phase 5 v4 prejournal: `development/docs/journal/phase5-prejournal.md` (commit `9fb089b`、historical record)
