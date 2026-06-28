# 成果物 acceptance matrix (Phase 5)

Step 5.a-0 で確定する成果物受け入れ条件。5.b 実装 + 5.b-ci CI + 5.d-canary / 5.e dogfood で各 cell を満たすことを確認する。

## acceptance matrix

| 観点 | Claude / full | Claude / split | Codex / full | Codex / split |
|---|---|---|---|---|
| **生成ファイル** | `SKILL.md` 単独 (本文に philosophy/stage-design/examples 全て埋め込み) | `SKILL.md` + `workflow.md` + `references.md` + `prompts/design-stages.md` + `prompts/review-policy.md` | `SKILL.md` 単独 (構造は Claude full と同等の本文、frontmatter 差分のみ) | `SKILL.md` + helper files (Claude split と同型) |
| **frontmatter** | `name: qgb` + `description` + `allowed-tools` + 他 (`agent-claude.md` 参照) | 同 (full / split で frontmatter 同一) | `name: qgb` + `description` (Codex CLI で確認済キーのみ) | 同 |
| **構文検証** | YAML frontmatter parse 成功 + Markdown parse 成功 | 同 + helper files も Markdown parse 成功 | 同 (Codex 側で `name`/`description` が読める) | 同 + helper files Markdown parse |
| **生成物 header** | 全成果物先頭に generator comment (converter version + source commit hash + 「これは生成物。`skills/source/body.md` を編集すること」)。**生成日時は埋め込まない** (下記「deterministic build 契約」参照) | 同 | 同 | 同 |
| **install ガイド** | `dist/skills/full/claude/INSTALL.md` 同梱、`~/.claude/skills/qgb/` への配置手順 | `dist/skills/split/claude/INSTALL.md`、配置手順 + helper files の関係説明 | `dist/skills/full/codex/INSTALL.md`、`~/.agents/skills/qgb/` への配置手順 | 同 (split 用) |
| **golden fixture** | `tools/_golden/claude/full/` 配下に期待生成物全件、`tools/build_skill.py` 出力と byte 一致 | `tools/_golden/claude/split/` 配下、同 | `tools/_golden/codex/full/` 配下、同 | `tools/_golden/codex/split/` 配下、同 |
| **manual smoke** | 配置 → 利用者 prompt 「qgb 入れて」で skill 起動確認 → SKILL.md 内容が Claude に読まれている確認 (深 dogfood で完全な対話を実施) | 同 + helper files が必要な依頼 (例: 「契約段階の設計やって」) で `workflow.md` / `prompts/design-stages.md` が参照される確認 (深 dogfood) | 配置 → smoke (`/skills` で qgb が一覧に出る + 起動成功) のみ。深 dogfood は不要 (案 ii) | 同 (smoke のみ) |
| **hook (任意)** | `dist/skills/full/claude/hooks/settings.example.json` 同梱、INSTALL.md で opt-in 手順説明 | 同 | `dist/skills/full/codex/hooks/hooks.example.json` 同梱、INSTALL.md で opt-in 手順説明 | 同 |
| **build mode 整合性** | full モードは body.md include marker 内容を本文に embedded、外部 helper ファイル参照ゼロ (helper は `skills/source/` には authored source として存在しない、A1' = body.md 単一正本) | split モードは body.md 骨子 + helper files (body.md include marker から converter が機械生成) で参照、marker 通りに本文が切り出されている | full / split / agent 別の整合性確認は build_skill.py + golden fixture で機械検証、`source_files` (= `[body.md]`) と marker 名の集合分離も検証 | 同 |

## 検証時期

| acceptance 項目 | 5.b 実装 | 5.b-ci CI | 5.d-canary | 5.e 利用者目線 |
|---|---|---|---|---|
| 生成ファイル | ✓ (ローカル build で確認) | ✓ (CI で diff vs golden) | △ (Claude full のみ skill 起動確認) | ✓ (Claude full + split 深、Codex full + split smoke) |
| frontmatter | ✓ | ✓ | ✓ | ✓ |
| 構文検証 | ✓ | ✓ | — | — |
| 生成物 header | ✓ | ✓ | — | — |
| install ガイド | ✓ (内容のみ) | — | — | ✓ (実際にガイドに従ってインストール) |
| golden fixture | ✓ (生成) | ✓ (vs build output) | — | — |
| manual smoke | — | — | ✓ (Claude full) | ✓ (全 cell) |
| hook | ✓ (テンプレ作成) | ✓ (parse 検証) | — | ✓ (任意で opt-in 確認) |
| build mode 整合性 | ✓ | ✓ | — | — |

## deterministic build 契約 (Codex K=2 r1 spec fix #1 反映)

golden fixture との byte 一致を成り立たせるため、converter は **完全に決定的** であること:

### 含めない要素 (毎回変動するもの)

- **生成日時**: タイムスタンプを生成物に埋め込まない (デフォルト)
- 利用者環境固有 path (絶対 path / ホスト名 / OS 表記等): すべて relative path 表記
- 並列処理由来の出力順序揺れ (固定 ordering で書き出す)

### 含める要素 (再現可能な情報)

- `converter_version` (`tools/build_skill.py` の semver、source 同梱)
- `source_commit_hash` (`git rev-parse HEAD` の結果、下記「dirty tree / archive / 非 Git 環境」規則あり)
- `source_files` の hash (sha256、入力の完全性証跡)
- 「これは生成物。`skills/source/body.md` を編集すること」固定文言

### `source_commit_hash` の各種環境での挙動

| 環境 | 挙動 |
|---|---|
| clean Git tree | `git rev-parse HEAD` の出力をそのまま埋め込み |
| dirty Git tree (uncommitted 変更あり) | header に `<hash>-dirty` を埋め込み + stderr に warn 出力。CI build では dirty tree を **error** で reject (golden 比較の前提が崩れる) |
| Git archive (`git archive` で抽出した tarball 等、`.git` なし) | `git archive` の `export-subst` で埋め込まれた hash を使用 (`.gitattributes` で `export-subst` 宣言、`tools/build_skill.py` が読み取り)。`.gitattributes` 未設定環境は `unknown-archive` を埋め込み + stderr warn |
| 非 Git 環境 (zip 解凍等) | `unknown-no-git` を埋め込み + stderr warn |

### タイムスタンプを生成物に含めたい場合 (将来の選択肢)

利用者運用で「いつビルドされたか」を release 物に残したい場合、**`SOURCE_DATE_EPOCH` 環境変数** から固定値を読む規律を採用 (reproducible-builds.org 規約に整合):

- `SOURCE_DATE_EPOCH` 未設定 → 生成日時を埋め込まない (デフォルト、CI golden 比較成立)
- `SOURCE_DATE_EPOCH=<unix epoch>` 設定 → その値を埋め込み (release CI で `git log -1 --format=%ct` 等から導出)

これにより通常の CI build (golden 比較する run) では生成日時非埋め込み、release CI build (utc 固定日時を埋め込みたい run) では `SOURCE_DATE_EPOCH` 経由で再現可能な値を埋め込む、という二段運用が可能。Phase 5 完結時の release CI 設計 (5.c) で具体化。

### encoding / newline / sort 順序の固定

- 出力 encoding: **UTF-8 BOM なし**、改行 LF (Phase 3 規律と整合、`.gitattributes` で *.md / *.json の LF を強制)
- frontmatter YAML キーの順序: schema 定義順 (alphabetical でなく宣言順)、deterministic
- helper file 列挙順序: `body.md` 内 include marker の出現順序に従う (re-sort しない)

## 「supported」 の合格基準

各 agent が `supported` 状態であるためには:

- Claude Code: 上記 matrix の全 cell が緑、Claude / full + Claude / split で深 dogfood 通過
- Codex CLI: 上記 matrix の全 cell が緑、Codex / full + Codex / split で smoke 通過 (深 dogfood は不要、案 ii)

未達成の場合の状態 (`agent-*.md` 前 matter):

- 全 cell 緑 + 深 dogfood OK → `supported`
- 全 cell 緑 + smoke のみ OK → `supported` (Codex は smoke で充分、案 ii)
- 一部 cell 不可 → `experimental` (Phase 5 で当面使わない、TODO 化したものは別)
- 構造的に対応不能 → `deferred` または GitHub issue で TODO

## 「TODO」 状態 (Antigravity 等)

5.a-0 で対象から外した agent は **GitHub issue で記録**、本 matrix の対象外。issue が「supported に昇格」する判断トリガは:

1. 公式 docs が SKILL ファイル相当の仕様レベルで整備される
2. コミュニティから具体的な利用ケースの要望が出る
3. qgb メンテナが主環境にする (例: Phase 5 中に Codex から Antigravity に乗り換える等)

該当 issue: [#25 [Phase 6+] Antigravity CLI 向け skill build 対応](https://github.com/Yumeno/Quality-gate-builder/issues/25)

## 関連

- `README.md` (本 dir、保守原則 + compatibility matrix)
- `agent-claude.md` / `agent-codex.md` (各 agent 仕様メモ)
- prejournal v4 §3.6 (本 matrix の骨子)
- 5.b 完結時の journal `phase5-step5-b.md` で matrix 各 cell の達成状況を記録
