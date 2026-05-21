# 作業記録: Phase 1 Step 3〜Step 4

期間: 2026-05-21 (Step 0〜2 記録の続き)

## 目的

Step 3 (`qgb init`) と Step 4 (`examples/generic-minimal/`) の作業経緯を時系列で残す。Step 0〜2 記録 (`phase1-step0-to-step2.md`) の続編。

Step 3〜4 は **Step 2 で確立した「思想憲章を共有しての Codex 再レビュー」パターン** がより自然に適用された期間。Codex の最初のレビューを丸呑みせず、思想憲章 P9 (単一責任) との整合性で取捨選択する規律が定着した。

## 全体の流れ

```
Step 3   qgb init                (実装 -> Codex レビュー -> 補修)
   ↓
Step 4   examples/generic-minimal/  (手書き -> Codex レビュー -> 補修)
```

両 Step とも一発で済まず、Codex 指摘を反映する補修コミットを伴った。

## Step 3: qgb init

### 実装内容 (commit `5303c99`)

`.quality-system/` 生成コマンド。要件定義書 §F-002 / §F-003 / §B-004 を満たす最小実装。

- `qgb/core/init.py`: `run_init(project_root, project_name?, force?)` で構造生成
- `qgb/templates/`: `config.initial.json` / `policy.initial.json` / `project-context.initial.md`
- `qgb/cli.py` の `init` subcommand 実装 (`--path`, `--name`, `--force`, `--json`)
- 6 ディレクトリ + 4 ファイル + `.gitignore` 追記
- `init -> validate` ラウンドトリップ保証 (test_init_output_passes_validate)
- 19 件のテスト追加 (合計 118 件)

#### 設計判断 (Step 2 経験を反映)

- `policy.json` は `stages: []` の空雛形で出す。段階設計は Step 6 `qgb design-stages` の責務 (P10、§F-006)。**init は最小の器を用意するだけ** という P9 単一責任を厳格に守った
- `detect` (Step 6) を含まない。Phase 1 の init は対象系を見ない
- `evidence/` と `artifacts/` も予約として作成 (Step 5 で使われる)

#### 副次修正

`test_cli_smoke.py` の「未実装サブコマンド」代表テストを `init` から `detect` に切り替え。Step 3 で init が実装されたため、テスト実行中に **qgb 自身の cwd で副作用** (`.gitignore` 改変、`.quality-system/` 作成) が発生していた。これは「テストが対象プロジェクトの状態を変える可能性」というメタ問題で、後続の Step でも気をつける必要がある。

### Codex 第 1 回レビュー

辛口で 10 件の指摘:

| # | 区分 | 指摘 |
|---|---|---|
| 1 | 重大 | ファイルとディレクトリの衝突を扱えていない (`mkdir` が例外 or `skipped` で成功偽装) |
| 2 | 重大 | `config.initial.json` の `raw.replace("{project_name}", ...)` が JSON として危険 (`"`, `\\`, 改行で破壊) |
| 3 | 中 | `.gitignore` がファイルでない場合に落ちる |
| 4 | 中 | `.gitignore` 追記の重複判定が雑 (trailing slash 差) |
| 5 | 中 | 空の `.gitignore` に先頭空行が入る |
| 6 | 中 | `FileOutcome.action` / `gitignore_action` が生文字列 (Literal 推奨) |
| 7 | 中 | `InitReport` に error 概念がない (例外 or 成功の二択) |
| 8 | 中 | CLI JSON 出力に `ok` がない |
| 9 | 中 | `--force` の範囲が help に不明示 |
| 10 | テスト | 壊れた既存ツリー系のテストが不足 |

加えて命名上の懸念 (`config.json` の `qgb.core_language` が「対象プロジェクトの言語」と誤読されうる)、Step 4 への先回り懸念 (`artifacts/` が `.gitignore` 対象なので空ディレクトリが git に乗らない問題) も指摘された。

#### 「責務越境はほぼしていない」評価

Codex は冒頭で:

> 結論から言うと、責務越境はほぼしていません。`init` は detect/design/scaffold に踏み込んでおらず、`policy.stages: []` も正しい。

と認定。Step 2 で経験した責務越境の罠を Step 3 では踏まなかった。これは設計判断 (P9 単一責任を init にも適用) が正しく働いた証拠。

### Step 3 補修 (commit `888484d`)

Codex の重大 2 件 + 中 8 件 + テスト不足 1 件をすべて反映。

#### 重大修正の核心

1. **「成功偽装」の根絶**: `InitError` dataclass を新設し、パス種別衝突 (ファイル ↔ ディレクトリ) を `errors[]` に集約。検出した場合は **exit 2 (NOT_READY)** を返し、**`--force` でもバイパスしない**
2. **JSON 安全性**: `_materialise_config()` を `json.loads(template) -> data[...] = name -> json.dumps()` の構造化代入に変更。`--name 'a"b\\c'` でも JSON 構造が崩れない

#### 命名上の判断 (Codex 指摘を見送り)

`qgb.core_language` の改名 (Codex 指摘) は **見送り**。理由：

- 要件定義書 §F-002 と `qgb/schemas/config.schema.json` で既に使用済み
- v0.3 全体の命名整合性を優先
- 改名するなら schema migration で扱うべき範囲

「Codex 指摘 = 必ず採用」ではなく、プロジェクト固有の事情で見送る判断が定着。

#### テスト追加 (20 件)

- パス種別衝突 (3 件): `.quality-system/` がファイル / `config.json` がディレクトリ / `.gitignore` がディレクトリ
- 特殊文字プロジェクト名 (parametric 7 件): 二重引用符 / バックスラッシュ / スペース / 改行 / タブ / 日本語 / クオート全体
- `.gitignore` 端処理 (3 件): 空ファイル先頭空行 / trailing-slash 同等 / 二重実行で byte-for-byte 不変
- 部分削除リカバリ (2 件): config だけ削除 / knowledge ディレクトリまるごと削除
- CLI: NOT_READY 表示 / JSON の ok/summary / 衝突時 JSON 出力
- `InitError` の frozen dataclass 保証

テスト件数: 118 → 138。

### 学び (Step 3)

- **Codex は「責務越境していない」をきちんと評価する**。前回の助言を「ユーザーの素朴な期待」優先で誤ったあと、思想憲章を共有しての再レビューで自己訂正したから、今回は最初から責務分離を優先するスタンスを取った
- **Codex 指摘の中に「採用しないもの」を判断する規律**: `core_language` 改名のように、Codex の指摘が技術的に正しくても、プロジェクト固有の整合性を優先する場合は明示的に見送る
- **「成功偽装」は最も危険なバグ**: ユーザーから見て「初期化成功」に見えるのに、実体は壊れた器、というケースを `InitError` で捕捉した。これは Step 5 以降の他コマンドでも同じパターンを使う

## Step 4: examples/generic-minimal/

### 実装内容 (commit `cc2b7a1`)

Phase 1 で初の **設計例パック**。実装コードではなく、設計判断の記録と動く `.quality-system/` ツリーの手書き。Step 5 (`qgb run`) のターゲット仕様としても機能する。

#### 構成

- `README.md`: サンプルの全体像
- `design-notes.md`: 設計判断メモ (採用しなかった段階を含む)
- `.gitignore`: `.quality-system/artifacts/` 除外
- `target/sample.txt`: 検査対象テキスト
- `.quality-system/`: config / policy / req / contracts / evidence (手書き)

段階構成:

| id | name | responsibility | type | depends_on |
|---|---|---|---|---|
| S1 | sample ファイル存在 | target/sample.txt が存在する | file_exists | [] |
| S2 | キーワード包含 | target/sample.txt に "hello" が含まれる | substring_match | [S1] |

#### 重要な設計判断

- **2 段階は推奨レンジ (3-7) 外**だが、入門用に意図的に縮めた。design-notes.md で明記
- **`artifacts/` ディレクトリは作らない**: 空 dir は git に乗らない、揮発側は実行時生成 (Codex Step 3 レビューで先回り指摘されていた問題への対応)
- **`gate.json` は手書きの ALLOW リファレンス**: Step 5 の qgb run が同等の構造を生成する設計
- **採用しなかった段階を 5 種類列挙**: ファイルサイズ / UTF-8 valid / 最終更新日時 / JSON Schema / 手動レビュー。各々の却下理由を思想憲章 (P5, P6, P7, P9) と紐づけ

#### 整合性テスト (5 件、後に拡張)

`tests/test_examples.py` を新設し、設計例の腐敗を CI で検出:

- `qgb validate` を通る
- `gate.json` が curated schema (strict) を満たす
- contract の claim が target ファイルで成立 (substring_match の "hello" が実在)
- `design-notes.md` が「推奨レンジ」を言及
- `design-notes.md` が「採用しなかった段階」セクションを含む

### Codex 第 1 回レビュー

Step 4 は実装コードでなく文書中心だが、Codex は **「Step 5 のターゲット仕様として見るとまだ甘い」** と評価。重大 3 件 + 中 4 件 + 軽微 1 件:

| # | 区分 | 指摘 |
|---|---|---|
| 1 | 重大 | `gate.json` の `log_ref` が実体を持たない (`latest/stages/*.log` 不在) |
| 2 | 重大 | `REQ-APP-001.md` と `design-notes.md` で `validate-policy` の期待結果が矛盾 |
| 3 | 重大 | `tests/test_examples.py` の整合性検証密度が不足 (cross-check 不在) |
| 4 | 中 | `design-notes.md` の UTF-8 却下理由が P9 違反の悪い癖を教える (「substring_match で暗黙カバー」) |
| 5 | 中 | 最終更新日時の却下理由が `validate-policy` 責務に逃がしていて不適切 |
| 6 | 中 | README が scaffold/run 責務に寄っている (「init から validate まで」) |
| 7 | 中 | Step 5 の出力仕様として `timestamp_utc` / `timestamp_rfc3339` の対応が未固定 |
| 8 | 軽微 | README が未来の examples (python-cli-pytest / markdown-docs) を既存のように見せている |

#### 「責務越境はしていない」評価 (再び)

Codex は今回も冒頭で responsibility 越境の懸念がないことを認定。Step 2 の経験を踏まえて、設計教材の例でも detect/design-stages/scaffold/run の領域に踏み込まない構造にしていたのが評価された。

### Step 4 補修 (commit `58bb38e`)

すべての指摘を反映:

#### 重大修正

1. **`log_ref` の実体追加**: `latest/stages/S1.log` と `S2.log` を手書きで追加。Step 5 で `qgb run` が同じパスに実ログを書く設計
2. **REQ と design-notes の矛盾解消**: `REQ-APP-001.md` の受入条件を「参照整合性は error なし、段階数 warning は design intent として許容」に書き換え
3. **cross-file integrity テスト**: `tests/test_examples.py` を 5 件 → 18 件に拡張。Step 5 が破ってはならない 10 件の不変条件を CI で検証:
   - REQ メタの stage_id ⊂ policy の id 集合
   - contract_ref が実在
   - contract の req_id / stage_id / verification_type が policy / meta と一致
   - contract が required_contract_fields を満たす
   - `gate.stages[]` が REQ メタの選択順
   - `gate.status == gate.decision.result` 同期
   - ALLOW のとき failed_stage == "" かつ全 stage passed
   - basis[] が REQ + POLICY-* + 各 CONTRACT-* を含む
   - paths.run_dir 末尾 timestamp が timestamp_utc と一致
   - timestamp 二系統 (compact / RFC3339) が同一時刻

#### Step 5 への申し送り (detailed-design.md §7.4, §7.5 新設)

Codex 指摘 #7 (timestamp 仕様未固定) を受けて、Step 5 で守るべき仕様を文書化:

- §7.4 gate.json 内 timestamp 規約: 単一の `datetime.now(timezone.utc)` から両形式を生成、`paths.run_dir` のサフィックスは `timestamp_utc` と一致
- §7.5 basis[] 規約: `REQ-*` + `POLICY-<policy_id>` + `CONTRACT-<REQ>-<stage_id>` の Phase 1 最小形式

これらは Step 5 実装時にテスト (Layer 3) で自動検証される。

#### design-notes.md の責務境界修正

- UTF-8 却下理由: 「暗黙カバー」(P9 違反の癖) から「diagnostic 責務として持たない」に書き換え
- 最終更新日時の却下理由: `validate-policy` 責務逃がしから「P7 と相性悪く、別段階で manifest checksum 等」に書き換え
- ファイルサイズの却下理由に P5 (ALLOW の意味の限定) を追加

設計例パックは **スキル化 (Phase 5) のときに Claude/Codex/Gemini が読む few-shot 学習材料** なので、不正確な責務境界の記述は将来の判断を歪める。Codex 指摘の通り、ここは特に丁寧に直した。

#### テスト

- 143 件 → 156 件、全成功

### 学び (Step 4)

- **設計教材の品質は「教える内容の正確性」**: 採用しなかった段階の却下理由を間違えると、スキルが似たような状況で誤った理由を学ぶ。Codex 指摘の「P9 違反の癖を教えない」は本質的
- **手書きサンプルでも CI で参照整合性を縛る**: 文書だけ整っていても、`gate.json` が `policy.json` と矛盾していたら教材として有害。Layer 3 cross-check はそれを防ぐ
- **Step 5 への申し送り文書化**: Step 4 時点で固まった契約 (timestamp / basis / cross-file integrity) を `detailed-design.md` に明文化することで、Step 5 実装時の判断を後押しする
- **「Step N のターゲット仕様」という見方を Codex に与えると、レビュー精度が上がる**: Codex は最初「設計教材として読める」と評価しつつも、「Step 5 リファレンスとしては緩い」と踏み込んだ。後者の視点を最初から共有していたことが効いた

## 振り返り: Step 3〜4 を通じて固まったパターン

### 1. 思想憲章は実装側にも降ろす

`P9 単一責任` は本来 stage に適用されるが、CLI コマンドにも同じ原則を当てる。これは Step 2 で確立し、Step 3 (init は最小の器のみ) と Step 4 (example は教材であって他責務に踏み込まない) で再確認された。

### 2. Codex 指摘は分類して判断

- 重大: 即時補修
- 中: 補修対象 (例外的に持ち越し、その場合は明示的判断を残す)
- 軽微: 必要に応じて
- 「正しいが見送る」: プロジェクト固有の事情で採用しない場合は理由を明示

`core_language` 改名見送り (Step 3) はこの分類の良い例。

### 3. テスト assertion の密度を上げる

Step 4 で Codex が「整合性検証密度が不足」と指摘したことで、`schema validation + 1 つの存在確認` だけだったテストを **5 件 → 18 件** に拡張。「壊れたら落ちる」ではなく「狙った契約で落ちる」を CI で検証する規律が定着。

### 4. Step N の文書化が Step N+1 の実装を楽にする

Step 4 の `detailed-design.md §7.4 timestamp 規約` / §7.5 basis 規約は Step 5 着手前の申し送り。Step 4 完了時点で固まった契約を明文化することで、Step 5 で「どうするか」を再考する手間が消える。

### 5. 設計例パックは「動く文書」

`examples/generic-minimal/` は README/design-notes/source/gate.json/log が**互いに整合**していなければ意味がない。整合性は Layer 3 cross-check テストで保証する。これは Phase 5 のスキル化 (`examples/` を few-shot 材料として読む) のために重要。

## コミット履歴 (Step 3〜4)

```
58bb38e Phase 1 Step 4 補修: Codex レビュー指摘の修正
cc2b7a1 Phase 1 Step 4: examples/generic-minimal/ 手書き完成版を追加
888484d Phase 1 Step 3 補修: Codex レビュー指摘の修正
5303c99 Phase 1 Step 3: qgb init を実装
055a776 Phase 1 Step 0〜2 確定範囲の詳細設計と作業記録を追加  # 前回 journal
```

## テストと品質指標の推移

| 段階 | テスト件数 | ruff |
|---|---|---|
| Step 2 巻き戻し完了時 | 99 | clean |
| Step 3 実装後 | 118 | clean |
| Step 3 補修後 | 138 | clean |
| Step 4 実装後 | 143 | clean |
| Step 4 補修後 | 156 | clean |

## 関連 Issue

- [#14](https://github.com/Yumeno/Quality-gate-builder/issues/14) Phase 1 MVP 実装トラッキング
- [#18](https://github.com/Yumeno/Quality-gate-builder/issues/18) Step 3: `qgb init` 最小実装 (closed)
- [#19](https://github.com/Yumeno/Quality-gate-builder/issues/19) Step 4: examples/generic-minimal/ 手書き完成版 (closed)

## 次のステップ

#20 Step 5: `qgb run` 最小実装 (縦串完成)。

`examples/generic-minimal/` がターゲット仕様。`detailed-design.md §7.4` (timestamp) と `§7.5` (basis[]) の規約に従って実装する。Layer 3 cross-check テストが破られないことが Step 5 の受け入れ条件の一つ。
