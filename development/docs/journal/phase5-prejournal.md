# Phase 5 着手前判断: Skill Creator 化

着手前判断確定: 2026-06-26
位置: Phase 3 全体完結後の Phase 5 着手前

## 1. 経緯

Phase 1 (Python CLI MVP, 2026-05) / Phase 2 (編集を安全にする, 2026-06-13 完結) / Phase 3 (機械責務側の最終整備, 2026-06-26 完結) を経て、qgb 本体は機械責務側の整備を完了した。残る Phase 4 (CI 連携) は 2026-06-21 に **廃止**、Phase 5 (Skill Creator 化) が次の主軸:

1. ✅ Phase 1: Python CLI MVP (3 例 examples、verification_type 4 種)
2. ✅ Phase 2: 編集を安全にする (JSON Patch / waiver / check / Pattern B external-LLM)
3. ✅ Phase 3: 機械責務側の最終整備
   - Step 3.0: detect 廃止 + project-context 二重ファイル設計
   - Step 3.1: command runner 強化 + CI 雛形 + 異常時責務分離
   - Step 3.2: 依存解決固定 (lock + hash) + 利用者運用との境界
4. 🚫 Phase 4: 廃止 (Step 3.1 + Step 3.2 + Phase 5 で吸収)
5. **Phase 5 (本書)**: Skill Creator 化 — エージェント中立スキル提供

Phase 5 で qgb は **「Python CLI として動く」だけ** から **「Claude Code / Codex CLI / Gemini CLI のいずれにも投入可能なスキルとして配布される」** 状態に進化する。

## 2. Phase 5 の理念的位置づけ

### 2.1 何を解決するか

Phase 1〜3 で qgb 本体は完成したが、**「LLM 環境からどう qgb を呼び出すか」** という運用層が未整備。利用者は qgb CLI を直接叩くか、自前で Claude Code / Codex CLI 用のスキル定義を書く必要がある。Phase 5 はこれを:

- スキル本体 (qgb の使い方 + philosophy + 段階設計手順 + プロンプト) を **エージェント中立な中間表現** として 1 つだけ書く
- コンバータ `tools/build_skill.py` が 3 エージェント (Claude Code / Codex CLI / Gemini CLI) 向け成果物を機械的に生成する
- 利用者は自分のエージェント用 1 セットだけを取得して入れる

### 2.2 ライン引きの維持

Phase 5 で **Phase 3 で確立した境界を一切緩めない**:

- **Step 3.0 ライン引き (対象認識)**: スキルは対象を Read で読んで理解する (LLM 責務)、qgb 本体は contract で宣言されたコマンドを実行するだけ (機械責務)
- **Step 3.1 ライン引き (異常時責務分離 + ドメイン依存性)**: スキルは利用者プロジェクトに responsibility 分離を提案するが、リアルタイム制御等の他ドメインには qgb 流を普遍適用しない注意喚起を含める
- **Step 3.2 ライン引き (lock 文化 vs 利用者運用)**: スキルは利用者プロジェクトに `--require-hashes` を**提案**できるが**強制しない**、利用者の package manager / コンプライアンス要件に応じて判断

### 2.3 Phase 6 以降との関係 (Phase 5 が終わってからの話)

Phase 5 完結後、qgb は「フレームワーク + LLM 向けスキル」のセット配布物となる。Phase 6 以降は実需に応じて:

- Step 3.3 残務 (Phase 2 繰越実需回収)
- 新 verification_type (Phase 5 で利用者から要望が出たもの)
- adapter 復活の検討 (Phase 3 で撤回したが、利用者プロジェクトの偏りが見えてから判断)

これらはすべて Phase 5 が advance しないと判断不能なので、本 prejournal では扱わない。

## 3. Phase 5 スコープ

### 3.1 中核: F-019 エージェント中立スキル提供

`requirements_and_development.md` §F-019 と `framework-shape.md` §5 で確定済の構造を本実装する:

```text
skills/source/                   # 中間表現 (正本、repo で保守、Phase 5 で本実装)
  metadata.yaml                  # skill id, version, agent_bindings
  body.md                        # スキル本体 (中立 Markdown)
  workflow.md                    # 作業手順 (.quality-system/ を作るまで)
  references.md                  # philosophy / stage-design 等への参照集
  prompts/
    design-stages.md             # 段階設計プロンプト (パターン B/C)
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

- 中間表現 (`skills/source/`) の本実装 (各ファイルを埋める、Phase 1 で予約した README.md は撤去または更新)
- `tools/build_skill.py` 実装 (3 エージェント成果物の機械的生成)
- 3 エージェント向け成果物 (`dist/skills/{claude,codex,gemini}/`) の生成と検証
- CI ビルド + GitHub Releases 添付の自動化 (Phase 3 Step 3.1/3.2 で確立した SHA pin policy + Dependabot/Renovate 不採用 + `shell: bash` 明示等の規律を踏襲)
- 3 エージェント向け運用ガイド (インストール / 更新 / トラブルシューティング)
- スキル自身を Claude Code で dogfooding (Phase 5 開発後半で、qgb メンテナンス作業の中で実使用)

### 3.4 スコープ内 (任意、Phase 5 で必要が見えたらやる)

- **利用者プロジェクト向け CI テンプレ生成機能** (旧 Phase 4 吸収項目): `ci-examples.md` Pattern A〜E が出発点、Phase 5 スキルが対象プロジェクトに応じて選択する形
- **言語非依存ドメインの examples 追加** (prompt-collection / sql-schemas / legal-templates 等): 既存 6 例で出発、利用者からの要望が出てから追加

### 3.5 スコープ外 (Phase 5 でやらない)

- **Phase 2 繰越実需回収 (Step 3.3)**: 並走可能だが先回りしない、Phase 5 中に判明した実需だけ拾う原則
- **新 verification_type 追加**: Phase 5 進行中に LLM 側から要望が出てから判断
- **adapter 復活**: Phase 3 Step 3.0 で撤回した方針を Phase 5 で覆さない (対象認識は LLM 責務)
- **AI Agent 評価フレームワーク**: スキルの「良さ」を機械評価する装置は philosophy P6 (LLM 単独 ALLOW 禁止) と緊張、Phase 5 では人間判断 + dogfooding で代替
- **SBOM 自動生成 / vuln scan**: Phase 3 Step 3.2 で out of scope 整理済、Phase 5 でも持ち込まない

## 4. サブステップ構成 (案)

Phase 1〜3 の経験から、**6 サブステップ + 任意 2 個** に圧縮する案。各サブステップは Step 3.1 / 3.2 同様の規模感 (1.0〜2.5)。

| Step | 内容 | 規模 | 自走可否 |
|---|---|---|---|
| **5.a** | スキル中間表現の本実装 (`skills/source/` 配下、`metadata.yaml` schema 確定 + `body.md` + `workflow.md` + `references.md` + `prompts/`) | 1.5〜2.5 | 部分自走 (ライン引き判断点あり) |
| **5.b** | `tools/build_skill.py` 実装 + 3 エージェント成果物生成 + ビルド検証 | 1.5〜2.5 | 自走 (5.a 確定後) |
| **5.c** | CI ビルド + GitHub Releases 添付 (SHA pin / Dependabot 不採用 / shell:bash 規律踏襲) | 0.5〜1.0 | 自走 (Step 3.1/3.2 パターン) |
| **5.d** | 3 エージェント向け運用ガイド (インストール / 更新 / トラブルシューティング) | 0.5〜1.0 | 自走 (template ベース) |
| **5.e** | dogfooding (Claude Code でこのスキルを使って qgb 自身を 1 サイクル改善できることを実証) | 0.5〜1.0 | 部分自走 (実使用で判断点出る) |
| **5.f** | 完結ドキュメント + journal + memory (Phase 3 Step 3.1/3.2 同型の Task 22/46 相当) | 0.5〜1.0 | 自走 (パターン確立) |
| 任意 5.g | 利用者プロジェクト向け CI テンプレ生成 (旧 Phase 4 吸収、`ci-examples.md` ベース) | 0.5〜1.0 | スコープ判断点 |
| 任意 5.h | 言語非依存 examples 追加 | 0.3〜0.8 | 実需待ち |

**合計規模見積もり**: 5.0〜9.0 (Phase 1〜2 全体相当、Phase 3 の 1.5〜2 倍)

### 4.1 各 Step の自走可否 (重要)

- **完全自走可能**: 5.b / 5.c / 5.d / 5.f (パターン確立済、Codex r1 で承認されれば連続実行可)
- **部分自走 (ライン引き判断点で user 確認が必要)**: 5.a (metadata.yaml schema / プロンプト分量 / dogfooding 範囲) / 5.e (実使用で見える判断点)
- **スコープ判断**: 5.g / 5.h (実需見極めが必要)

### 4.2 Step 順序の理由

- 5.a → 5.b: 中間表現が確定しないとコンバータが書けない (依存)
- 5.b → 5.c: ローカルでビルドが通らないと CI に乗らない (依存)
- 5.c → 5.d: CI が回らないと「リリース成果物の入手方法」を書けない (依存)
- 5.d → 5.e: ガイドが整わないと dogfooding で利用者目線に立てない (推奨依存、緩い)
- 5.e → 5.f: dogfooding の知見を完結 journal に反映 (依存)

## 5. ライン引き判断点 (user 判断が必要、prejournal v2 提示時に問う)

Phase 5 の構造的判断で、私が独走するべきでない箇所:

### 判断点 1: `metadata.yaml` schema の確定範囲

`framework-shape.md` §5 に例があるが、本実装段階では:
- どのフィールドを **必須** にし、どこから **オプション** にするか
- 各エージェント固有設定 (Claude の `allowed-tools`、Codex の `placement`、Gemini の `command_name` 等) をどこまで `metadata.yaml` で吸収するか、コンバータのデフォルト判断に任せる範囲
- スキーマ自身を JSON Schema で固定するか (qgb の他 schema と同じ規律、NF-010 整合性)

**選択肢**:
- (a) 最大主義: 全エージェント固有設定を `metadata.yaml` に書く → コンバータが薄くなるが maintainer の編集負担増
- (b) 最小主義: 中立部分のみ `metadata.yaml`、エージェント固有はコンバータがデフォルト → maintainer 編集楽だがコンバータの責務が膨らむ
- (c) ハイブリッド: `metadata.yaml` で「skill_id, version, helper_files, agent_bindings の存在のみ」を宣言、各 agent_bindings の中身はそのエージェント側で必要最小限

### 判断点 2: スキル本体 (`body.md`) の分量と詳細度

`body.md` は LLM の context に毎回乗る。分量が大きいと context を食い、小さいと指示不足:
- 思想憲章 (philosophy.md, 11 不易) を全文埋めるか、参照だけにするか
- 段階設計フェーズの具体例 (パターン B/C) を `body.md` に含めるか `prompts/design-stages.md` に分離するか
- examples/ 6 例の構造説明をどこまで詳しく書くか

**選択肢**:
- (a) `body.md` を充実 (2-3 千語): 1 回読めば自走可能、context 重い
- (b) `body.md` を骨子のみ (500-1000 語): context 軽い、補助ファイルを都度参照する設計
- (c) スキルの起動段階で `body.md` を読み、必要に応じて補助を読む設計 (LLM の自律判断にゆだねる)

### 判断点 3: 段階設計プロンプト (`prompts/design-stages.md`) のスコープ

`stage-design.md` のパターン B / C を:
- スキル起動時に必ず読むか (`helper_files` で必須化)
- ユーザーが「段階設計やって」と言ったときだけ読むか (オンデマンド)
- パターン B (Pattern B external-LLM) と パターン C (自律実行) で別ファイルにするか統合するか

### 判断点 4: dogfooding の範囲

Phase 5 開発中の Claude Code 自身がこのスキルを使うか:
- (a) dogfooding は最後 (5.e) で初めて: skill 開発中の bootstrap 問題を避ける
- (b) dogfooding を 5.b 完了後に始める: 早期に問題を発見できるが、開発が混乱する可能性
- (c) dogfooding はしない、利用者向けの release 後にコミュニティ feedback 待ち: Phase 5 完結が早いが品質確信が薄い

### 判断点 5: CI ビルド時の third-party action 追加範囲

GitHub Releases 添付には `actions/upload-release-asset` 系の third-party action が必要になる可能性:
- (a) 純正 `gh release upload` CLI を `run:` ステップで使う (SHA pin 不要、Step 3.1 NF-011 と整合)
- (b) `actions/upload-release-asset` を SHA pin で追加 (Step 3.1 で確立した SHA pin policy 拡張)
- (c) リリースのみ手動運用にする (Phase 5 規模を抑える)

### 判断点 6: Step 3.3 (Phase 2 繰越実需回収) の並走判断

Phase 5 中に繰越項目の実需が判明したとき:
- (a) 即座に並走拾う (Phase 5 が長期化するが個別実需に応える)
- (b) Phase 5 後にまとめて 3.3 を回収 (Phase 5 集中)
- (c) Phase 5 と 3.3 を交互に切る (細かい振り分け)

## 6. 規模実績の参考

Phase 3 の各 Step 規模実績:

| Step | 計画見積もり | 実績 | 上振れ理由 |
|---|---|---|---|
| 3.0 | 2.0〜2.5 | 約 2.8 | 段 1 で spec-drift 6 件発見 |
| 3.1 | 1.5〜2.0 | 約 3.5〜4.0 | ステート不在化への補修方針転換 + 5 観点並列 48 件 |
| 3.2 | 0.9〜1.5 | 約 1.6 | CI 補修 chain 5 連 (環境固有問題) |

**Phase 5 見積もり 5.0〜9.0 も同様に 1.5〜2 倍の上振れ可能性あり** (7.5〜18.0 まで膨らむシナリオ)。特に 5.a (中間表現) でライン引き判断が多発する可能性が高い。

## 7. レビュープロセス (Phase 1〜3 と同じ運用)

各 Step ごとに:

1. **本体実装** (サブステップ単位で commit)
2. **段 1 観点別並列レビュー** (5 観点: correctness / P9 / philosophy / NF-004 / spec-drift)
3. **段 2 Claude 集約**
4. **段 3 Codex 横断レビュー**
5. **補修 + 段 5 K=2 収束**

「small だから省略禁止」を Phase 3 Step 3.2 で再証明済。Phase 5 も同様の厳格運用。

## 8. 関連ファイル (本 Phase で触る予定)

- `skills/source/` 配下全ファイル (本実装)
- `tools/build_skill.py` (新設)
- `.github/workflows/test.yml` (Phase 5 用 build job 追加) または `.github/workflows/release.yml` (新設)
- `dist/` 配下 (.gitignore で除外、CI で生成)
- `pyproject.toml` (dev extras に `tools/build_skill.py` 必要な依存追加、NF-010 慎重判断)
- `SECURITY.md` (Phase 5 で新 third-party action 追加するなら SHA Pin Policy 拡張)
- `development/docs/journal/phase5-step5-*.md` (各 Step の prejournal + 完結 journal)
- `development/docs/detailed-design.md` §16 新設想定 (Phase 5 詳細)
- `development/docs/requirements_and_development.md` §13 (Phase 5 進捗反映)
- `README.md` (利用者向けインストール経路 = リリースから 1 セット入れる)
- `CLAUDE.md` (Phase 5 完結反映)

## 9. 不確実性 (Codex 計画レビューで問いたい点)

1. **6 サブステップ案 (5.a〜5.f) の分割粒度は適切か**: Phase 1〜3 経験から 1 ステップ 1.5〜2.5 規模で揃えたが、5.a が肥大化リスクあり (中間表現 6 ファイルを 1 ステップに集約) — 5.a-1 (metadata.yaml + body.md) / 5.a-2 (workflow + references + prompts) に分割すべきか
2. **`metadata.yaml` schema 確定戦略**: 案 (a)(b)(c) のどれを推奨するか、別案はあるか
3. **`body.md` 分量**: 案 (a)(b)(c) のどれを推奨するか、Phase 1〜3 で蓄積した spec / journal を frame に LLM context cost と instruction quality の trade-off をどう判断するか
4. **dogfooding 順序**: 案 (a)(b)(c) のどれを推奨するか
5. **CI ビルドの third-party action**: 案 (a)(b)(c) のどれを推奨するか、`gh release upload` で済むなら NF-011 整合
6. **規模見積もり 5.0〜9.0 の妥当性**: Phase 3 実績ベースで 1.5〜2 倍の上振れリスクを織り込んでいるが、Phase 5 特有の見落とし要素 (LLM context cost 検証 / 3 エージェント挙動差吸収 / スキル品質評価の人間判断比重) はないか
7. **Step 順序 (5.a → 5.b → 5.c → 5.d → 5.e → 5.f)**: 依存関係は正しく整理されているか、並走可能な箇所はあるか
8. **`tools/build_skill.py` の依存**: 新 dev 依存追加 (YAML パーサー、template engine 等) と NF-010 (stdlib 中心) のバランス — `pyyaml` 等を追加するか、stdlib で済ませるか

## 10. レビュープロセス (本書 v1 → v2)

1. ✅ 本 prejournal v1 commit
2. **Codex 計画レビュー r1** (`/ask-codex-with-context` 経由、本 prejournal を context として渡す)
3. r1 finding を反映、ライン引き判断点 6 件を整理して **user 提示用 v2** を作成
4. user 判断確定後、Step 5.a 着手

Phase 1〜3 で確立した「prejournal v1 → Codex r1 → v2 → 着手」パターンに従う。
