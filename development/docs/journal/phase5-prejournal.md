# Phase 5 着手前判断: Skill Creator 化

着手前判断確定: 2026-06-26 (v1)
Codex セカンドオピニオン反映 + ライン引き再点検: 2026-06-26 (v2)

## v2 改訂サマリ (v1 → v2)

v1 commit (`dc6c9a7`) を Codex 計画レビュー r1 にかけ、code fix 4 件 + spec fix 8 件 + out of scope 3 件 + 各判断点推奨回答を受領。以下を確定:

- **5.a を 3 段階に分割**: 5.a-0 (agent contract probe + acceptance 固定) / 5.a-1 (metadata.yaml schema + minimal source tree) / 5.a-2 (body.md + workflow.md + references.md + prompts)
- **5.b と 5.c を切り離す**: 5.b で `build_skill.py` + ローカル build 確認、5.c はリリース直前 (dogfood 後) に再配置
- **dogfooding を 2 段階化**: 5.b 後に canary dogfood (Step 5.d-canary) + 5.d 後に利用者目線 dogfood (5.e)
- **`tools/build_skill.py` の依存方針確定**: `pyyaml` を dev/build 限定で追加 (runtime には入れない、lock+hash で管理)、template engine は不要 (f-string で十分)
- **`metadata.yaml` schema を JSON Schema で固定**: F-019/C-008 整合、converter の曖昧さを閉じる
- **3 agent acceptance を限定**: 生成物構造 / install guide / static syntax / golden output / manual smoke checklist まで、実 agent の完全同等挙動保証は機械検証対象外
- **5.g (CI テンプレ生成) を optional 降格で確定**: 要件書 §13 Phase 5 の「スキルに含める」記述との矛盾を v2 で整理 (Codex 推奨: optional)
- **規模見積もり 5.0〜9.0 → 7.0〜12.0 へ上方修正**: agent contract probe / golden fixture / context budget / release packaging / dogfood 補修分

## 1. 経緯

Phase 1 (Python CLI MVP, 2026-05) / Phase 2 (編集を安全にする, 2026-06-13 完結) / Phase 3 (機械責務側の最終整備, 2026-06-26 完結) を経て、qgb 本体は機械責務側の整備を完了した。残る Phase 4 (CI 連携) は 2026-06-21 に **廃止**、Phase 5 (Skill Creator 化) が次の主軸:

1. ✅ Phase 1: Python CLI MVP
2. ✅ Phase 2: 編集を安全にする
3. ✅ Phase 3: 機械責務側の最終整備 (Step 3.0 detect 廃止 / 3.1 command runner / 3.2 lock + hash)
4. 🚫 Phase 4: 廃止
5. **Phase 5 (本書)**: Skill Creator 化 — エージェント中立スキル提供

Phase 5 で qgb は **「Python CLI として動く」だけ** から **「Claude Code / Codex CLI / Gemini CLI のいずれにも投入可能なスキルとして配布される」** 状態に進化する。

## 2. Phase 5 の理念的位置づけ

### 2.1 何を解決するか

Phase 1〜3 で qgb 本体は完成したが、**「LLM 環境からどう qgb を呼び出すか」** という運用層が未整備。利用者は qgb CLI を直接叩くか、自前で各エージェント用のスキル定義を書く必要がある。Phase 5 はこれを:

- スキル本体 (qgb の使い方 + philosophy + 段階設計手順 + プロンプト) を **エージェント中立な中間表現** として 1 つだけ書く
- コンバータ `tools/build_skill.py` が 3 エージェント (Claude Code / Codex CLI / Gemini CLI) 向け成果物を機械的に生成する
- 利用者は自分のエージェント用 1 セットだけを取得して入れる

### 2.2 ライン引きの維持 (Phase 1〜3 で確立した境界の継承)

Phase 5 で **Phase 1〜3 で確立した境界を一切緩めない**:

- **Step 3.0 ライン引き (対象認識)**: スキルは対象を Read で読んで理解する (LLM 責務)、qgb 本体は contract で宣言されたコマンドを実行するだけ (機械責務)
- **Step 3.1 ライン引き (異常時責務分離 + ドメイン依存性)**: スキルは利用者プロジェクトに responsibility 分離を提案するが、リアルタイム制御等の他ドメインには qgb 流を普遍適用しない注意喚起を含める
- **Step 3.2 ライン引き (lock 文化 vs 利用者運用)**: スキルは利用者プロジェクトに `--require-hashes` を**提案**できるが**強制しない**

### 2.3 Phase 6 以降との関係

Phase 5 完結後、qgb は「フレームワーク + LLM 向けスキル」のセット配布物となる。Phase 6 以降は実需に応じて Step 3.3 残務 / 新 verification_type / adapter 復活検討。これらはすべて Phase 5 が advance しないと判断不能。

## 3. Phase 5 スコープ

### 3.1 中核: F-019 エージェント中立スキル提供 (構造再確認)

```text
skills/source/                   # 中間表現 (正本、repo で保守、Phase 5 で本実装)
  metadata.yaml                  # skill id, version, agent_bindings
  metadata.schema.json           # v2 追加: metadata.yaml の JSON Schema (Codex code fix #3)
  body.md                        # スキル本体 (中立 Markdown)
  workflow.md                    # 作業手順 (.quality-system/ を作るまで)
  references.md                  # philosophy / stage-design 等への参照集
  prompts/
    design-stages.md             # 段階設計プロンプト (パターン B/C 統合、章分離)
    review-policy.md             # レビュー観点プロンプト

tools/build_skill.py             # コンバータ (Phase 5 で新設、Phase 3 Step 3.2 で tools/ 階層を確立済)

dist/skills/                     # ビルド成果物 (.gitignore 対象、CI で生成)
  claude/   SKILL.md + 補助ファイル
  codex/    AGENTS.md (補助連結)
  gemini/   GEMINI.md (@import) + .gemini/commands/qgb.toml
```

### 3.2 対象エージェント (3 種、F-019 で確定)

| エージェント | 主成果物 | 補助の扱い | 配置先 |
|---|---|---|---|
| Claude Code | `SKILL.md` (YAML frontmatter) | dir 内に実体配置 | `~/.claude/skills/<id>/` |
| Codex CLI | `AGENTS.md` (フラット連結) | 末尾に章として連結 | プロジェクトルート |
| Gemini CLI | `GEMINI.md` (@import) + `.toml` | `@import` 参照、スラッシュコマンドは TOML | `~/.gemini/` |

### 3.3 スコープ内 (Phase 5 で必ずやる)

- 中間表現 (`skills/source/`) の本実装 (各ファイルを埋める、Phase 1 で予約した README.md は内容更新)
- `metadata.yaml` schema (JSON Schema で固定、Codex code fix #3)
- `tools/build_skill.py` 実装 (決定的ビルド契約: clean build / LF 正規化 / generator header / converter version / source commit hash 埋め込み / dirty tree 検出 / golden fixture 比較、Codex code fix #1)
- 3 エージェント向け成果物 (`dist/skills/{claude,codex,gemini}/`) の生成と検証 (構造 / install guide / static syntax / golden output / manual smoke checklist、Codex spec fix #7)
- CI build check (5.b 直後、`dist/` を生成 + golden fixture と diff)
- 3 エージェント向け運用ガイド (インストール / 更新 / トラブルシューティング)
- canary dogfooding (5.b 後) + 利用者目線 dogfooding (5.d 後)
- CI からの GitHub Releases 添付 (dogfooding 完了後、`gh release upload` で third-party action 不要)

### 3.4 スコープ内 (任意、Codex spec fix #8 で optional 降格確定)

- **利用者プロジェクト向け CI テンプレ生成機能** (旧 Phase 4 吸収項目、5.g): `ci-examples.md` Pattern A〜E が出発点、Phase 5 スキルが対象プロジェクトに応じて選択する形。**Phase 5 では optional、必要が見えてから着手**
- **言語非依存ドメインの examples 追加** (prompt-collection / sql-schemas / legal-templates 等、5.h): 既存 6 例で出発、利用者からの要望が出てから追加

### 3.5 スコープ外 (Phase 5 でやらない、Codex 確認済)

- **Phase 2 繰越実需回収 (Step 3.3)**: blocker になったものだけ例外的に拾う、即時並走は Phase 5 の主目的を濁す (Codex out of scope #1)
- **AI Agent 評価フレームワーク**: P6 と緊張 (Codex out of scope #2)。**ただし dogfooding checklist と人間 review rubric は別 (P6 違反でない)、Phase 5 内で作る**
- **新 verification_type 追加**: 実需が出てから判断
- **adapter 復活**: Phase 3 Step 3.0 で撤回した方針を維持
- **SBOM 自動生成 / vuln scan**: Phase 3 Step 3.2 で整理済
- **3 agent 完全同等挙動保証**: 実 agent の挙動差は流行側、converter の変換規則と生成物 snapshot を固定するに留める (Codex spec fix #7)

## 4. サブステップ構成 (v2 で再分割、Codex spec fix #1 + #5 + #6 反映)

v1 の 6 サブステップを Codex 推奨に従って分割・順序調整:

| Step | 内容 | 規模 | 自走可否 |
|---|---|---|---|
| **5.a-0** | Agent contract probe + 各エージェント最新仕様確認 + 成果物 acceptance 固定 | 0.5〜1.0 | 自走 (調査 + acceptance 文書) |
| **5.a-1** | `metadata.yaml` schema (JSON Schema) + minimal `skills/source/` tree (空ファイル + schema 検証だけ通る状態) | 0.5〜1.0 | 自走 (schema 設計) |
| **5.a-2** | `body.md` + `workflow.md` + `references.md` + `prompts/` 本文の本実装 | 1.5〜2.5 | 部分自走 (分量判断点あり) |
| **5.b** | `tools/build_skill.py` 実装 (決定的ビルド契約) + 3 エージェント成果物生成 + golden fixture 化 + ローカル build 検証 | 2.0〜3.0 | 自走 (5.a 確定後) |
| **5.b-ci** | CI に build check job 追加 (Phase 3 Step 3.1/3.2 と同じ SHA pin 規律) | 0.3〜0.5 | 自走 |
| **5.d-canary** | canary dogfooding (Claude Code でこのスキルを使って小さな改善を 1 回試す) | 0.5〜1.0 | 部分自走 (使用感判断点あり) |
| **5.d** | 3 エージェント向け運用ガイド (インストール / 更新 / トラブルシューティング) + dogfooding checklist + 人間 review rubric | 0.5〜1.0 | 自走 (template ベース) |
| **5.e** | 利用者目線 dogfooding (5.d の運用ガイドに従ってインストールから 1 サイクル) + 補修 | 0.5〜1.0 | 部分自走 |
| **5.c** | CI からの GitHub Releases 添付自動化 (dogfooding 後、`gh release upload` で third-party action 不要) | 0.3〜0.5 | 自走 (Phase 3 Step 3.1/3.2 パターン) |
| **5.f** | 完結ドキュメント + journal + memory (Phase 3 Step 3.1/3.2 同型の Task 22/46 相当) | 0.5〜1.0 | 自走 (パターン確立) |
| 任意 5.g | 利用者プロジェクト向け CI テンプレ生成 (旧 Phase 4 吸収、optional) | 0.5〜1.0 | スコープ判断点 |
| 任意 5.h | 言語非依存 examples 追加 | 0.3〜0.8 | 実需待ち |

**合計規模見積もり**: **7.0〜12.0** (Codex 推奨、v1 の 5.0〜9.0 から上方修正)
**上振れリスク線**: 15〜18 (agent contract probe で予想外、3 agent 挙動差吸収で複雑化、dogfood 補修連鎖)

### 4.1 順序調整 (Codex spec fix #6 反映)

v1 の `5.c (CI ビルド + GitHub Releases 添付)` を 2 つに分割:
- **5.b-ci**: CI build check (5.b 直後、検証のため)
- **5.c**: GitHub Releases 添付 (dogfooding 完了後、検証済 artifact のみ release する構造)

これにより「検証前 artifact が release される」リスクを構造的に閉じる。

### 4.2 dogfooding の 2 段階化 (Codex spec fix #5 反映)

- **5.d-canary**: 5.b 完了直後、Claude Code でスキルを使って qgb 自身の小さな改善 (例: docstring 1 つ追加) を試す。「絶対に動く範囲」を確認
- **5.e**: 5.d (運用ガイド完成) 後、利用者目線でゼロから運用ガイドだけ見てインストール → 1 REQ 設計 → gate.json 生成までを通す

早期 dogfood で「致命的に動かない」を発見、後期 dogfood で「ガイドが正しいか」を検証。

## 5. ライン引き判断点 (user 判断が必要、本 v2 提示時に問う)

Codex r1 で各判断点に推奨回答を受領済。**user が最終確認**するのは以下:

### 判断点 1: `metadata.yaml` schema 確定範囲

**Codex 推奨**: typed hybrid (薄い、必須キーは型付きで強制)
- 必須: `skill_id`, `version`, `description`, `entry_body`, `helper_files`, `agent_bindings`
- `agent_bindings.{claude,codex,gemini}` の中身は **known keys を型付きで許可、未知 key は error**
- v1 案の (c) ハイブリッドより一段厳しい (未知 key を許さない)、converter 側に仕様が逃げる余地を閉じる

**user 確認事項**: Codex 推奨で進めるか、別案 (より緩い / より厳しい) があるか

### 判断点 2: スキル本体 (`body.md`) の分量

**Codex 推奨**: (b) + (c) の明文化 = 500〜1000 語の骨子 + trigger 明記
- `body.md` 自身は骨子 (500〜1000 語)
- 「この依頼なら `workflow.md` を読む」「段階設計なら `prompts/design-stages.md` を読む」の **trigger を本文に固定**
- 純粋な (c) の自律判断任せは agent ごとの context 読み漏れ差が出る

**user 確認事項**: Codex 推奨で進めるか、分量を変えるか (例: 1000-2000 語まで許容)

### 判断点 3: 段階設計プロンプト (`prompts/design-stages.md`) スコープ

**Codex 推奨**: オンデマンド + パターン B/C 統合 (章を分けて、肥大化したら split)
- 起動時必読にしない (`body.md` 軽量化の意味が消える)
- パターン B と C は最初は同ファイルで章分離
- ファイルが肥大化したらリファクタ split

**user 確認事項**: Codex 推奨で進めるか、最初から B/C を別ファイルにするか

### 判断点 4: dogfooding 順序

**Codex 推奨**: (b) の 2 段階化 = 5.b 後 canary + 5.d 後 利用者目線
- v1 の (a) 最後 5.e で初めて は発見が遅い
- 開発中ずっと self-use する必要もない (2 段階で十分)

**user 確認事項**: Codex 推奨で進めるか、3 段階以上にするか

### 判断点 5: CI ビルドの third-party action 追加

**Codex 推奨**: (a) `gh release upload` で third-party action 不要
- release workflow だけ `permissions: contents: write`
- 通常 test workflow は現状通り最小権限
- Phase 3 Step 3.1 SHA pin policy 規律を維持

**user 確認事項**: Codex 推奨で進めるか、別案 (action 追加 / 手動運用) があるか

### 判断点 6: Step 3.3 (Phase 2 繰越実需回収) の並走判断

**Codex 推奨**: (b) Phase 5 後 + blocker のみ例外
- 即時並走 (a) は Phase 5 の主目的を濁す
- 交互切り替え (c) は管理コスト高

**user 確認事項**: Codex 推奨で進めるか、blocker の定義を確認しておくか

## 6. Codex r1 finding 反映トレース (v2 確定)

| Codex finding | 種別 | 反映先 |
|---|---|---|
| code fix #1 (決定的ビルド契約) | code fix | §3.3 / §4 Step 5.b に「決定的ビルド契約」を必須 acceptance に組み込み |
| code fix #2 (`pyyaml` dev/build 限定) | code fix | §3.3 / 関連ファイル §8 で `pyyaml` を dev extras 追加、template engine 不採用 |
| code fix #3 (`metadata.yaml` を JSON Schema 化) | code fix | §3.1 で `metadata.schema.json` を中間表現に追加、§4 Step 5.a-1 で schema 本実装 |
| code fix #4 (`gh release upload` 推奨) | code fix | §3.3 / §4 Step 5.c で確定 |
| spec fix #1 (5.a を 5.a-0/-1/-2 に分割) | spec fix | §4 で 3 分割確定 |
| spec fix #2 (typed hybrid) | spec fix | §5 判断点 1 で Codex 推奨採用 |
| spec fix #3 (`body.md` を (b)+(c) で明文化) | spec fix | §5 判断点 2 で Codex 推奨採用 |
| spec fix #4 (オンデマンド + B/C 統合) | spec fix | §5 判断点 3 で Codex 推奨採用 |
| spec fix #5 (dogfooding 2 段階) | spec fix | §4 で 5.d-canary + 5.e に分離、§5 判断点 4 で確定 |
| spec fix #6 (5.c を分割: build check と release 添付) | spec fix | §4 で 5.b-ci と 5.c に分離 |
| spec fix #7 (3 agent acceptance 限定) | spec fix | §3.3 / §3.5 で「実 agent の完全同等挙動保証は機械検証対象外」を明示 |
| spec fix #8 (5.g を optional 降格) | spec fix | §3.4 で確定、§ §7 で要件書 §13 Phase 5 との整合性を Task 46 同型で整理 |
| out of scope #1 (Step 3.3 = (b) Phase 5 後) | out of scope | §5 判断点 6 で Codex 推奨採用 |
| out of scope #2 (AI Agent 評価 NG、dogfooding checklist は OK) | out of scope | §3.5 で「dogfooding checklist と人間 review rubric は別、Phase 5 内で作る」を明示 |
| out of scope #3 (adapter / 新 verification / SBOM / 自動 installer / 完全互換) | out of scope | §3.5 維持 |

## 7. 規模実績の参考 (v2 で上方修正)

Phase 3 の各 Step 規模実績:

| Step | 計画見積もり | 実績 | 上振れ理由 |
|---|---|---|---|
| 3.0 | 2.0〜2.5 | 約 2.8 | 段 1 で spec-drift 6 件発見 |
| 3.1 | 1.5〜2.0 | 約 3.5〜4.0 | ステート不在化への補修方針転換 + 5 観点並列 48 件 |
| 3.2 | 0.9〜1.5 | 約 1.6 | CI 補修 chain 5 連 (環境固有問題) |

**Phase 5 v2 見積もり 7.0〜12.0** (Codex 上方修正、agent contract probe / golden fixture / context budget / release packaging / dogfood 補修分)、**上振れリスク線 15〜18** (Codex 推奨)。

特に 5.a-2 (中間表現本文) と 5.b (コンバータ + 決定的ビルド) で判断点が多発する可能性が高い。

## 8. 関連ファイル (本 Phase で触る予定、v2 で拡張)

- `skills/source/` 配下全ファイル (本実装)
  - `metadata.yaml` (新規) + `metadata.schema.json` (v2 追加、JSON Schema)
  - `body.md` / `workflow.md` / `references.md` / `prompts/design-stages.md` / `prompts/review-policy.md`
- `tools/build_skill.py` (新設) + golden fixtures (`tools/_golden/` 等)
- `pyproject.toml` (dev extras に `pyyaml>=6,<7` 追加、NF-010 慎重判断 + Phase 3 Step 3.2 で確立した lock 更新規律)
- `requirements.lock` / `requirements-dev.lock` (`pyyaml` 追加で再生成、Windows × Python 3.10 規律維持)
- `.github/workflows/test.yml` (build check job 追加) + `.github/workflows/release.yml` (新設、release タグ trigger で `gh release upload`)
- `dist/` 配下 (`.gitignore` で除外、CI で生成)
- `.gitignore` (`dist/` 追加)
- `SECURITY.md` (Phase 5 で `pyyaml` lock policy + release workflow 説明追加)
- `development/docs/journal/phase5-step5-*.md` (各 Step の prejournal + 完結 journal)
- `development/docs/detailed-design.md` §16 新設 (Phase 5 詳細)
- `development/docs/requirements_and_development.md` §13 (Phase 5 進捗反映)
- `README.md` (利用者向けインストール経路 = リリースから 1 セット入れる)
- `CLAUDE.md` (Phase 5 完結反映 + Phase 6 以降の方針)
- `tools/diff_locks.py` (既存、Phase 3 Step 3.2 で確立) はそのまま使い回し

## 9. 不確実性 (Step 単位の判断で扱う)

v1 で Codex 計画レビューに問うた点は r1 で消化済。本 Phase 5 着手後、Step 単位で再点検する:

1. **`metadata.yaml` schema の細部**: typed hybrid の具体的 key 定義 (5.a-1 で確定)
2. **`body.md` trigger 設計**: 「この依頼なら X を読む」の文言と網羅性 (5.a-2 で確定)
3. **`tools/build_skill.py` のテスト戦略**: golden fixture の作り方、3 agent 成果物の差分検出 (5.b で確定)
4. **CI release workflow の権限境界**: `permissions: contents: write` の最小化 (5.c で確定)
5. **3 agent 挙動差吸収の限界**: どこまで converter で吸収、どこから「これは各 agent の責任」と線引きするか (5.b〜5.e で都度判断)

## 10. レビュープロセス (Phase 1〜3 と同じ運用)

各 Step ごとに:

1. **本体実装** (サブステップ単位で commit)
2. **段 1 観点別並列レビュー** (5 観点: correctness / P9 / philosophy / NF-004 / spec-drift)
3. **段 2 Claude 集約**
4. **段 3 Codex 横断レビュー**
5. **補修 + 段 5 K=2 収束**

「small だから省略禁止」を Phase 3 Step 3.2 で再証明済。Phase 5 も同様の厳格運用。各 Step 内で発生する補修は Phase 3 Step 3.1 の 7 件 / Step 3.2 の 5 件 + 5 件パターンを参考。

## 11. v2 着手準備状況

- ✅ prejournal v1 commit (`dc6c9a7`)
- ✅ Codex 計画レビュー r1 (code fix 4 + spec fix 8 + out of scope 3、判断点推奨回答 6 件)
- ✅ 本書 v2 起草 (Codex r1 全件反映)
- ⏳ **user による判断点 6 件最終確認** (Codex 推奨をそのまま採用するか、別案で進めるか)
- ⏳ user 判断後、**Step 5.a-0 (agent contract probe + acceptance 固定) から着手**

## 12. user 提示用判断点まとめ (再掲)

Codex 推奨をそのまま採用する場合の最終確認:

| # | 判断点 | Codex 推奨 |
|---|---|---|
| 1 | `metadata.yaml` schema | typed hybrid (必須キー型付き、未知 key error) |
| 2 | `body.md` 分量 | 500〜1000 語骨子 + trigger 明文化 |
| 3 | `design-stages.md` スコープ | オンデマンド + パターン B/C 統合 (章分離) |
| 4 | dogfooding 順序 | 2 段階 (5.b 後 canary + 5.d 後 利用者目線) |
| 5 | CI ビルド third-party action | `gh release upload` のみ (third-party action 不要) |
| 6 | Step 3.3 並走判断 | Phase 5 後 + blocker のみ例外 |

別案の検討が必要なものがあれば user 介入で確定、すべて Codex 推奨でよければ Step 5.a-0 着手。
