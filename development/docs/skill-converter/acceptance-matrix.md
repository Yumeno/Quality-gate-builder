# 成果物 acceptance matrix (Phase 5)

Step 5.a-0 で確定する成果物受け入れ条件。5.b 実装 + 5.b-ci CI + 5.d-canary / 5.e dogfood で各 cell を満たすことを確認する。

## acceptance matrix

| 観点 | Claude / full | Claude / split | Codex / full | Codex / split |
|---|---|---|---|---|
| **生成ファイル** | `SKILL.md` 単独 (本文に philosophy/stage-design/examples 全て埋め込み) | `SKILL.md` + `workflow.md` + `references.md` + `prompts/design-stages.md` + `prompts/review-policy.md` | `SKILL.md` 単独 (構造は Claude full と同等の本文、frontmatter 差分のみ) | `SKILL.md` + helper files (Claude split と同型) |
| **frontmatter** | `name: qgb` + `description` + `allowed-tools` + 他 (`agent-claude.md` 参照) | 同 (full / split で frontmatter 同一) | `name: qgb` + `description` (Codex CLI で確認済キーのみ) | 同 |
| **構文検証** | YAML frontmatter parse 成功 + Markdown parse 成功 | 同 + helper files も Markdown parse 成功 | 同 (Codex 側で `name`/`description` が読める) | 同 + helper files Markdown parse |
| **生成物 header** | 全成果物先頭に generator comment (converter version + build input digest + 「これは生成物。`skills/source/body.md` を編集すること」)。**生成日時 / source commit hash は埋め込まない** (下記「deterministic build 契約」参照、commit hash は golden 自己参照問題を構造的に回避) | 同 | 同 | 同 |
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
- `build_input_digest` (build 結果を決定する全入力を canonical 順で連結した sha256 hex digest、下記「build_input_digest の構成」参照)
- 「これは生成物。`skills/source/body.md` を編集すること」固定文言

**`source_commit_hash` は生成物に埋め込まない** (Codex K=2 r2 spec fix #1 反映):

- 旧設計では `git rev-parse HEAD` を埋め込もうとしていた
- しかし golden fixture 更新 commit で HEAD が変わるため、golden 内の hash が自己参照になり、byte 一致を維持できない
- 代わりに **build 入力全体の content hash (`build_input_digest`)** を埋め込む。これは入力の完全性証跡として `source_commit_hash` と同等の trust を提供し、HEAD に依存しない (commit 前後で build 入力が同じなら同じ digest)

### `build_input_digest` の構成 (deterministic input hash、Codex K=2 r3 spec fix #2 反映)

**build 結果を変化させる全入力**を digest 対象に含める。converter は以下の手順で digest を生成:

#### digest 対象 (canonical input manifest)

build 結果は以下に依存するため、すべてを digest 対象に含める:

1. `metadata.yaml` 全体 (skill_id / version / description / converter_min_version / source_files / build_modes / target_agents)
2. `metadata.schema.json` 全体 (schema 変更で validate 挙動が変わるため)
3. `metadata.yaml#source_files` に列挙された authored source 文書 (現状 `[body.md]` のみ、将来追加された場合も含む)
4. 同梱対象の hook 関連ファイル (`skills/source/hooks/**/*.json` + `skills/source/hooks/**/*.ps1` + `skills/source/hooks/**/*.md` + `skills/source/hooks/**/*.sh` 等、`AGENT_TO_HOOK_DIRNAME` mapping で target_agents に対応する dir のみ)
5. `target_agents` の各 agent について `development/docs/skill-converter/agent-{name}.md` 全体 (converter が status / frontmatter キー / hook_support 等を読むため、変更で build 挙動が変わる)
6. **converter version** (`converter_version`) も digest 入力に含める (converter 改修で生成物が変わるため、build 入力の一部とみなす)

**ファイル列挙の canonical 順**: 上記 1〜5 の各カテゴリ内で、相対 path の **辞書順 ASCII sort** (locale 非依存)。カテゴリ間順序は上記の番号順 (= manifest 構造順) を固定。

#### digest 計算手順

1. 上記 canonical manifest を構築
2. 各 input file を **byte 単位**で読み込み (decode せず)、改行は **LF に正規化済**であることを確認 (`.gitattributes` で LF 強制済)
3. 連結フォーマット: 各 input について `<categorical id (1〜6)>\n<file path as UTF-8 bytes>\n<file content bytes>\n` を生成、全体を 1 byte stream に連結。`converter_version` だけは `6\n<version string>\n` の形 (file content ではなく文字列直接)
4. sha256 を計算、16 進 lowercase で表現
5. 短縮表記 (最初の 16 桁) を生成物 header に埋め込み: `build_input_digest: 0123456789abcdef`

#### 設計上の主張

- **同一 build 入力 → 同一 digest**: metadata / source / hook / agent docs / converter version のいずれが変わっても digest が変化、それ以外 (環境変数 / HEAD / build 時刻等) では変化しない
- **build 入力 1 byte 変更 → digest 完全変化** (binary diffuse な hash の特性)
- **golden fixture は build 入力同期で更新**: 上記いずれかが変更 → golden 再生成 + 同一 commit に含める (1 commit 内で build 入力と digest が一致する状態を維持)
- **build 入力外の変化は digest を変えない**: 例えば `development/docs/journal/` の追記、利用者プロジェクト側の変更、CI 設定の変更等は digest に影響しない (= golden 比較も影響しない)

#### 旧 source_content_digest との違い

K=2 r2 で導入した `source_content_digest` (body.md のみ対象) は **build 入力の完全性証跡として不十分**だった (Codex K=2 r3 spec fix #2 指摘)。例: hook / metadata のみを変更しても build 結果は変わるが digest は変わらず、golden 不一致が起きるが digest からは原因が辿れない。`build_input_digest` で真の入力範囲を反映する設計に修正。

### 利用者向け「どの commit で build されたか」の参照

利用者運用で「この生成物はどの commit でビルドされたか」を知りたい場合、以下のいずれかを採用:

- **release tag に hash を明示**: GitHub Releases の release notes / tag message に build 元 commit hash を記載 (人間可読の release metadata、生成物には埋め込まない)
- **`SOURCE_DATE_EPOCH` 経由のタイムスタンプ**: 下節参照、CI build で `git log -1 --format=%ct` 等から固定値を導出して generator header に埋め込み可能 (deterministic、golden 比較は維持される)

生成物に commit hash を直接埋め込まないことで、golden fixture と HEAD の自己参照問題を構造的に回避する。

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
