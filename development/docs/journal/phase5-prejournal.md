# Phase 5 着手前判断: Skill Creator 化

着手前判断確定: 2026-06-26 (v1)
Codex セカンドオピニオン r1 反映 + ライン引き再点検: 2026-06-26 (v2)
**user 視点反映 (agent 変化前提 / build mode / trigger ハーネス依存): 2026-06-26 (v3)**

## v3 改訂サマリ (v2 → v3)

v2 commit (`5fd1689`) を user に提示したところ、Codex 推奨 (typed hybrid + 骨子 + trigger 表) の前提を覆す重要な観点 3 件を頂いた:

### user 視点 1: Agent CLI の "終息と後継" は構造的に起きる

- 直近事例: Gemini CLI 終息 / Antigravity CLI 登場 (Phase 5 着手期前後)
- 含意: v2 の typed hybrid は **「3 agent が安定的に存在する」前提** で yaml に詳細を寄せていた。この前提は事実上崩れている
- 結論: **「変換ロジックは Python (`tools/build_skill.py`)」「設計判断は journal/spec」「yaml は薄い目印に留める」** という構造に転換

### user 視点 2: body.md は build mode で選べる構造に

- user の経験 (別スキル開発): 「全部盛りモード」と「補助文書分割モード」をインストール時に選べる設計が便利だった
- 含意: 案 (a) 大盛り (`body.md` に philosophy/stage-design 全文埋め込み) と案 (b)+(c) 骨子 + trigger を **片方に決めず両方提供**できる
- まず full モードで書いて token 数を計測し、必要なら split モードを追加するのが実証主義として妥当

### user 視点 3: trigger / hook は harness 依存

- user 指摘: 「LLM の指示遵守だけに依存する trigger 表」と「harness レベル hook (settings.json hook 等)」は別物
- 含意: trigger 表は **agent をまたいだ minimum 保証**、hook は **agent ごとに利用可否が違う追加層**
- 結論: trigger 表 (α) を base に、hook 利用可能な agent (Claude Code の settings.json hook 等) には **install option で hook 設定を提供** (γ)、agent 仕様次第なので 5.a-0 probe で確認

これら 3 件は Phase 5 設計の根幹に関わる。Codex r2 で **agent 変化前提下での typed hybrid 縮退判断** を独立評価する必要あり。

## 1. 経緯

Phase 1 (Python CLI MVP, 2026-05) / Phase 2 (編集を安全にする, 2026-06-13 完結) / Phase 3 (機械責務側の最終整備, 2026-06-26 完結) を経て、qgb 本体は機械責務側の整備を完了。Phase 4 (CI 連携) は 2026-06-21 廃止。Phase 5 (Skill Creator 化) が次の主軸:

1. ✅ Phase 1: Python CLI MVP
2. ✅ Phase 2: 編集を安全にする
3. ✅ Phase 3: 機械責務側の最終整備
4. 🚫 Phase 4: 廃止
5. **Phase 5 (本書)**: Skill Creator 化 — エージェント中立スキル提供

## 2. Phase 5 の理念的位置づけ

### 2.1 何を解決するか

Phase 1〜3 で qgb 本体は完成したが、**「LLM 環境からどう qgb を呼び出すか」** という運用層が未整備。Phase 5 はこれを:

- スキル本体 (qgb の使い方 + philosophy + 段階設計手順 + プロンプト) を **エージェント中立な中間表現** として書く
- コンバータ `tools/build_skill.py` が agent 向け成果物を機械的に生成する
- 利用者は自分の agent 用 1 セットだけを取得して入れる

### 2.2 ライン引きの維持 (Phase 1〜3 で確立した境界の継承)

Phase 5 で **Phase 1〜3 で確立した境界を一切緩めない**:

- **Step 3.0 ライン引き (対象認識)**: スキルは対象を Read で読んで理解する (LLM 責務)、qgb 本体は contract で宣言されたコマンドを実行するだけ (機械責務)
- **Step 3.1 ライン引き (異常時責務分離 + ドメイン依存性)**: スキルは利用者プロジェクトに responsibility 分離を提案するが、リアルタイム制御等の他ドメインには qgb 流を普遍適用しない注意喚起を含める
- **Step 3.2 ライン引き (lock 文化 vs 利用者運用)**: スキルは利用者プロジェクトに `--require-hashes` を**提案**できるが**強制しない**

### 2.3 新規ライン引き (v3 で追加): Agent 変化前提

**Agent CLI は終息・後継が頻繁に起きるドメイン** という前提を明示化する。これは Phase 1〜3 のドメイン依存性 (Step 3.1) と並ぶ、Phase 5 固有の運用前提:

- 各 agent (Claude Code / Codex CLI / Gemini CLI など) を **「永続不変」とは扱わない**
- 各 agent の skill / agent file 仕様は **「現時点のスナップショット」** として扱い、変換ロジックは Python コンバータに集約
- 新 agent (Antigravity CLI 等) 対応は **コンバータ追加 + journal 記録** で行う
- yaml に書いた agent_bindings は **存在宣言** に留め、変換詳細は yaml で表現しない

これは Phase 3 で確立した **「機械正本 (json) + 人間正本 (md)」二重ファイル設計** の Phase 5 版:
- **コンバータ Python = 機械正本** (実行可能、決定論的)
- **converter design journal = 人間正本** (なぜそう変換するか、各 agent 仕様の理解、変化への追従履歴)

### 2.4 Phase 6 以降との関係

Phase 5 完結後、qgb は「フレームワーク + LLM 向けスキル」のセット配布物となる。Phase 6 以降は実需に応じて Step 3.3 残務 / 新 verification_type / adapter 復活検討。

## 3. Phase 5 スコープ

### 3.1 中核: F-019 エージェント中立スキル提供 (v3 で再整理)

```text
skills/source/                   # 中間表現 (正本)
  metadata.yaml                  # 薄い宣言 (v3): skill_id, version, build_modes, agent_bindings の存在のみ
  metadata.schema.json           # metadata.yaml の JSON Schema (v2 で導入、v3 で薄い構造に追従)
  body.md                        # スキル本体 (v3: まず full モードで書く、後で split 可能)
  workflow.md                    # 作業手順 (.quality-system/ を作るまで)
  references.md                  # philosophy / stage-design 等への参照集
  prompts/
    design-stages.md             # 段階設計プロンプト (パターン B/C 統合、章分離)
    review-policy.md             # レビュー観点プロンプト
  hooks/                         # v3 で追加: hook 利用可能な agent 向けの install option
    claude-code/                 # Claude Code 用 settings.json hook テンプレ
      settings.example.json
    codex/                       # Codex CLI 用 (5.a-0 で確認後)
    antigravity/                 # 後継 agent 用 (5.a-0 で確認後)

tools/build_skill.py             # コンバータ (Phase 5 で新設、変換ロジックの正本)
tools/_golden/                   # decision build の golden fixture (5.b で確立)
development/docs/skill-converter/  # v3 追加: コンバータ設計 journal (各 agent 仕様の理解 + 変化対応履歴)
  README.md                      # converter の責務と保守原則
  agent-claude.md                # Claude Code 仕様の現在の理解
  agent-codex.md                 # Codex CLI 仕様の現在の理解
  agent-antigravity.md           # Antigravity CLI 仕様 (5.a-0 で probe)
  transitions/                   # agent 終息 / 後継対応の履歴
    2026-06-gemini-to-antigravity.md  # 例: Gemini → Antigravity 移行記録

dist/skills/                     # ビルド成果物 (.gitignore、CI で生成)
  full/   claude/ codex/ antigravity/   # 全部盛りモード
  split/  claude/ codex/ antigravity/   # 補助分割モード
```

### 3.2 対象エージェント (v3 で再設定)

Phase 5 着手期 (2026-06) 時点の対象想定:

| エージェント | 状態 | 5.a-0 probe 必須項目 |
|---|---|---|
| Claude Code | 現役 | SKILL.md frontmatter / hook 機構 / 配置先 |
| Codex CLI | 現役 | AGENTS.md 構造 / config.toml hook 可否 |
| Gemini CLI | **終息予定** | 現時点で対応するか、Antigravity に移行か判断 (5.a-0) |
| Antigravity CLI | **新規後継** | 仕様調査 (5.a-0)、Phase 5 で対応するか先送りか判断 |

5.a-0 で確定後、対象 agent 数とビルド対象を決定。**「Gemini を切って Antigravity に切り替え」「両方サポート」「Antigravity だけ」** のいずれかは 5.a-0 後 user 判断点。

### 3.3 build mode (v3 で新規導入)

利用者の context 予算 / 用途に応じて 2 モードを生成:

| モード | `entry_body` (body.md) | `helper_files` | LLM context 量 | 用途 |
|---|---|---|---|---|
| **full** | philosophy / stage-design / examples / trigger 表 すべて埋め込み (大盛り) | 空 (補助ファイルなし) | 大 (推定 4-6 KB / 2-3 千語) | 初心者、頻度低、token cost 許容 |
| **split** | 骨子 (500-1000 語) + trigger 表 | workflow.md / references.md / prompts/ 等別ファイル | 小 (推定 1-2 KB) | 熟練者、高頻度呼び出し、cost 重視 |

**5.a-2 で full モードを先に書き**、本文全量と token 計測。その後 split モードに切り出すか判断 (5.a-2 内 user 判断点)。

### 3.4 trigger / hook 戦略 (v3 で新規導入)

| 層 | 内容 | 対応 agent |
|---|---|---|
| **(α) body.md 内 trigger 表** | LLM 指示遵守に依存、文書としての trigger | 全 agent (minimum 保証) |
| **(γ) agent 別 hook** | harness レベル機構で trigger 発火を保証 | Claude Code (settings.json hook、Python script 起動可)。Codex / Antigravity は 5.a-0 で確認 |

(γ) は agent ごとに利用可否が違うため install option として提供。install ガイドで「Claude Code は hook 自動設定可、その他は trigger 表に従う」と説明。

### 3.5 スコープ内 (Phase 5 で必ずやる)

- 中間表現 (`skills/source/`) の本実装 (v3 構造に従って各ファイルを埋める)
- `metadata.yaml` 薄い宣言 + `metadata.schema.json` (JSON Schema 検証)
- `tools/build_skill.py` 実装 (決定的ビルド契約: clean build / LF / generator header / converter version / source commit hash / dirty tree / golden fixture)
- build mode (full / split) 両方を生成 (v3 新規)
- agent 別成果物生成と検証 (構造 / install guide / static syntax / golden output / manual smoke checklist)
- agent 別 hook テンプレ (`skills/source/hooks/`) と install ガイドへの組み込み (v3 新規)
- **converter design journal** (`development/docs/skill-converter/`) で各 agent 仕様の理解 + 変化対応履歴を記録 (v3 新規)
- CI build check (5.b 直後、`dist/` を生成 + golden fixture と diff)
- 対象 agent 向け運用ガイド (インストール / 更新 / トラブルシューティング)
- canary dogfooding (5.b 後) + 利用者目線 dogfooding (5.d 後)
- CI からの GitHub Releases 添付 (dogfooding 完了後、`gh release upload`、third-party action 不要)

### 3.6 スコープ内 (任意)

- **利用者プロジェクト向け CI テンプレ生成機能** (旧 Phase 4 吸収、5.g): optional
- **言語非依存ドメインの examples 追加** (5.h): 実需待ち

### 3.7 スコープ外 (Phase 5 でやらない)

- Phase 2 繰越実需回収 (Step 3.3): blocker のみ例外
- AI Agent 評価フレームワーク: P6 と緊張。ただし dogfooding checklist + 人間 review rubric は Phase 5 内で作る
- 新 verification_type 追加: 実需が出てから判断
- adapter 復活: Phase 3 Step 3.0 で撤回した方針を維持
- SBOM 自動生成 / vuln scan: Phase 3 Step 3.2 で整理済
- **agent 仕様への永続適合保証**: agent 終息 / 後継は構造的に起きるため、Phase 5 で「全 agent 永続対応」は約束しない。各 agent への対応は **その時点での仕様スナップショット** に基づく

## 4. サブステップ構成 (v3 で再整理)

v2 の 11 サブステップを v3 視点で更新:

| Step | 内容 | 規模 | 自走可否 |
|---|---|---|---|
| **5.a-0** | Agent contract probe (Claude / Codex / Gemini 終息状況 / Antigravity 仕様) + 対象 agent 確定 + 成果物 acceptance 固定 + **converter design journal 雛形作成** (v3 拡張) | 1.0〜1.5 | 自走 (調査) + user 確認 1 回 (対象 agent 確定) |
| **5.a-1** | `metadata.yaml` 薄い構造 + `metadata.schema.json` (JSON Schema) + minimal `skills/source/` tree | 0.5〜1.0 | 自走 |
| **5.a-2** | **full モードで body.md / workflow.md / references.md / prompts/ を書く** + token 計測 + user に提示 → split モード切り出し判断 + (必要なら) split モード本実装 | 2.0〜3.5 | 部分自走 (split 切り出し判断点) |
| **5.b** | `tools/build_skill.py` 実装 + agent 別 + build mode 別の組み合わせ生成 + golden fixture + ローカル build 検証 + **converter design journal で各 agent 変換規則を記録** | 2.5〜4.0 | 自走 (5.a 確定後) |
| **5.b-ci** | CI に build check job 追加 (Phase 3 Step 3.1/3.2 と同じ規律) | 0.3〜0.5 | 自走 |
| **5.d-canary** | canary dogfooding (Claude Code でこのスキルを使って小さな改善を 1 回試す、full モード優先、split が違うなら追加 canary) | 0.5〜1.5 | 部分自走 |
| **5.d** | 対象 agent 向け運用ガイド + hook install option ガイド (v3 新規) + dogfooding checklist + 人間 review rubric | 0.5〜1.5 | 自走 |
| **5.e** | 利用者目線 dogfooding (5.d の運用ガイドに従って、full モードと split モード両方インストールから 1 サイクル) + 補修 | 0.5〜1.5 | 部分自走 |
| **5.c** | CI からの GitHub Releases 添付自動化 (`gh release upload`、third-party action 不要) | 0.3〜0.5 | 自走 |
| **5.f** | 完結ドキュメント + journal + memory (Phase 3 Step 3.1/3.2 同型) | 0.5〜1.0 | 自走 |
| 任意 5.g | 利用者プロジェクト向け CI テンプレ生成 (旧 Phase 4 吸収、optional) | 0.5〜1.0 | スコープ判断点 |
| 任意 5.h | 言語非依存 examples 追加 | 0.3〜0.8 | 実需待ち |

**合計規模見積もり**: **8.5〜15.0** (v2 の 7.0〜12.0 から上方修正)
- 増加要因: 5.a-0 (agent contract probe 拡張 + journal 雛形) +0.5、5.a-2 (full 先行 + split 切り出し) +0.5〜1.0、5.b (build mode × agent の組み合わせ生成 + converter journal) +0.5〜1.0
- **上振れリスク線: 18〜22** (agent 終息 / 後継対応の予想外、hook 統合の複雑化)

### 4.1 5.a-0 の重要性 (v3 で再強調)

v3 で 5.a-0 が単なる probe から **Phase 5 全体の前提確定 step** に格上げされた:

- 対象 agent の選定 (Gemini を切るか、Antigravity を入れるか)
- 各 agent の hook 機構の確認 (settings.json hook / config.toml prompts / etc.)
- 成果物 acceptance (構造 / install guide / static syntax / golden output / manual smoke checklist) の固定
- **converter design journal の雛形作成** = 「各 agent 仕様の現在のスナップショット」を記録、後から変化追跡できる構造を作る

5.a-0 が固まらないと 5.a-1 以降が動けない (依存)。

## 5. ライン引き判断点 (user 判断、v3 で再整理)

v2 の 6 件のうち 3 件 (判断 1 / 2 / 4) は user 視点で再整理済。残り 3 件は v3 でも継承:

### 判断点 1 (v3 修正): `metadata.yaml` 構造 → **薄い yaml + Python コンバータ重視**

**v2 案**: typed hybrid (必須キー型付き、未知 key error)
**v3 修正**: より薄く、agent_bindings は存在宣言のみ。変換ロジックは Python に集約、設計判断は converter design journal に記録

理由: agent 終息 / 後継が構造的に起きるため、yaml に詳細を寄せても結局 Python を触ることになる。yaml は **「存在の宣言」** に留め、変換ロジックの正本は Python + journal。

### 判断点 2 (v3 修正): `body.md` 分量 → **build mode で選択可能**

**v2 案**: 500-1000 語骨子 + trigger 表
**v3 修正**: full と split の両モードを提供
- 5.a-2 で先に full を書く → token 計測 → split に切り出すか判断
- 利用者は自分の context 予算で選ぶ
- 両モードを `dist/skills/{full,split}/{agent}/` で生成

理由: user 別スキル経験で「全部盛り / 補助分割を選べる」設計が便利だった。case-by-case で利用者が決める方が、qgb 側で 1 つに決めるより柔軟。

### 判断点 3 (v3 維持): `design-stages.md` スコープ → オンデマンド + パターン B/C 統合 (章分離)

Codex r1 推奨採用 (v2 のまま)。`body.md` 軽量化と整合。

### 判断点 4 (v3 維持): dogfooding 順序 → 2 段階

Codex r1 推奨採用 (v2 のまま)。5.d-canary + 5.e。

### 判断点 5 (v3 維持): CI ビルド third-party action → `gh release upload` のみ

Codex r1 推奨採用 (v2 のまま)。Step 3.1 SHA pin policy 規律維持。

### 判断点 6 (v3 維持): Step 3.3 並走判断 → Phase 5 後 + blocker のみ例外

Codex r1 推奨採用 (v2 のまま)。

### 判断点 7 (v3 新規): trigger / hook 戦略 → 二段 (body.md trigger + agent 別 hook)

**(α) body.md 内 trigger 表** を全 agent 対応の minimum 保証として実装
**(γ) agent 別 hook テンプレ** を install option として提供 (5.a-0 で agent ごとに利用可否確認)

理由: user 指摘「trigger / hook は harness 依存」。trigger 表だけだと LLM が見落とすリスク、hook だけだと agent 仕様依存で網羅不能。両層で minimum + best-effort の構造。

### 判断点 8 (v3 新規): 対象 agent 選定 → 5.a-0 で確定

Phase 5 着手期に Gemini CLI 終息 + Antigravity CLI 登場が起きている。5.a-0 probe 後に user 判断:
- (a) Claude Code + Codex CLI + Antigravity CLI (Gemini 切り)
- (b) Claude Code + Codex CLI + Gemini CLI + Antigravity CLI (両方サポート)
- (c) Claude Code + Codex CLI のみ (Gemini/Antigravity は判断 9 で別追加)
- (d) その他

## 6. v3 で Codex r2 に問いたい点

### 6.1 設計判断点

1. **agent 変化前提下での薄い yaml 採用は妥当か**: v2 typed hybrid から v3 薄い宣言への縮退判断は、本当に Python コンバータ重視で正解か。typed hybrid を維持しつつ「agent 別 binding section を yaml から動的に追加削除」できる中間案はあるか
2. **build mode (full / split) の 2 モード生成は妥当か**: 維持コスト (本文重複管理、build_skill.py の責務膨張) を考えても便益が上回るか
3. **converter design journal の構造**: agent ごとに 1 file (`agent-claude.md` 等) + `transitions/` (移行履歴) の構造は適切か、別構造の方が変化追跡しやすいか
4. **trigger / hook の二段戦略**: (α) body.md trigger 表 + (γ) agent 別 hook という二段は実装可能性 / 保守性で妥当か
5. **対象 agent 選定タイミング**: 5.a-0 で確定する想定だが、Antigravity 仕様が 5.a-0 時点で十分判明していない場合 (公式 docs 未整備等) の fallback はどうあるべきか

### 6.2 規模見積もり

6. **v3 で 7.0〜12.0 → 8.5〜15.0 に上方修正**: agent 変化前提 + build mode 追加 + converter journal で +1.5〜3.0 を見込んだが、user 視点 3 件は本質的に Phase 5 の構造変更で、もっと膨らむ可能性はあるか
7. **5.a-0 規模拡張 (0.5〜1.0 → 1.0〜1.5)**: agent probe + journal 雛形 + 対象選定で 1.0〜1.5 は妥当か、もっと必要か

### 6.3 Phase 1〜3 との整合

8. **二重ファイル設計 (機械正本 = converter Python / 人間正本 = journal) を Phase 5 に持ち込む**: Phase 3 Step 3.0 の project-context.{md,json} と同型のパターンだが、Phase 5 で適用する妥当性は十分か
9. **Step 3.0 / 3.1 / 3.2 で確立した境界 (対象認識 / 異常時責務分離 / lock 文化) は v3 でも維持されているか**: agent 変化前提を導入したことで境界が弱まる箇所はないか

### 6.4 見落とし

10. **v3 で扱い漏れがある観点はないか**: Codex 視点で独立に発見すべき点

率直にお願いします。code fix / spec fix / out of scope by philosophy の 3 分類で。

## 7. 関連ファイル (v3 で拡張)

- `skills/source/` 配下 (本実装)
  - `metadata.yaml` (薄い宣言) + `metadata.schema.json`
  - `body.md` (full モード優先で本実装)
  - `workflow.md` / `references.md` / `prompts/design-stages.md` / `prompts/review-policy.md`
  - **`hooks/{claude-code,codex,antigravity}/` (v3 新規、install option)**
- `tools/build_skill.py` (新設) + `tools/_golden/` (golden fixtures)
- **`development/docs/skill-converter/` (v3 新規、converter design journal)**
  - `README.md` (converter 責務 + 保守原則)
  - `agent-{claude,codex,antigravity}.md` (各 agent 仕様スナップショット)
  - `transitions/` (agent 終息 / 後継対応の履歴)
- `pyproject.toml` (dev extras に `pyyaml>=6,<7` 追加)
- `requirements.lock` / `requirements-dev.lock` (`pyyaml` 追加で再生成、Phase 3 Step 3.2 規律)
- `.github/workflows/test.yml` (build check job 追加) + `.github/workflows/release.yml` (新設)
- `dist/` 配下 (`.gitignore` で除外)
- `SECURITY.md` (Phase 5 で release workflow 説明追加)
- `development/docs/journal/phase5-step5-*.md` (各 Step の prejournal + 完結 journal)
- `development/docs/detailed-design.md` §16 新設 (Phase 5 詳細)
- `development/docs/requirements_and_development.md` §13 (Phase 5 進捗反映)
- `README.md` (利用者向けインストール経路 + build mode 説明)
- `CLAUDE.md` (Phase 5 完結反映)
- `tools/diff_locks.py` (既存、Phase 3 Step 3.2、そのまま使い回し)

## 8. レビュープロセス (Phase 1〜3 と同じ運用)

各 Step ごとに:

1. 本体実装 (サブステップ単位で commit)
2. 段 1 観点別並列レビュー (5 観点)
3. 段 2 Claude 集約
4. 段 3 Codex 横断レビュー
5. 補修 + 段 5 K=2 収束

## 9. v3 着手準備状況

- ✅ prejournal v1 commit (`dc6c9a7`)
- ✅ Codex 計画レビュー r1 (15 件 finding 反映)
- ✅ v2 commit (`5fd1689`)
- ✅ user 視点 3 件反映 (本書 v3)
- ⏳ **Codex 計画レビュー r2** (本書 v3 を context として渡す)
- ⏳ user による v3 最終確認 (Codex r2 結果も踏まえて)
- ⏳ user 判断後、Step 5.a-0 着手

## 10. user 提示用判断点まとめ (v3 再掲)

| # | 判断点 | v2 案 | **v3 修正案** |
|---|---|---|---|
| 1 | `metadata.yaml` schema | typed hybrid | **薄い yaml + Python コンバータ重視 + converter journal** |
| 2 | `body.md` 分量 | 500-1000 語骨子 + trigger | **full / split 両モード生成** |
| 3 | `design-stages.md` スコープ | オンデマンド + B/C 統合 | 維持 |
| 4 | dogfooding 順序 | 2 段階 | 維持 |
| 5 | CI ビルド third-party action | `gh release upload` | 維持 |
| 6 | Step 3.3 並走判断 | Phase 5 後 + blocker のみ例外 | 維持 |
| 7 (v3 新規) | trigger / hook 戦略 | — | **(α) body.md trigger + (γ) agent 別 hook の二段** |
| 8 (v3 新規) | 対象 agent 選定 | — | **5.a-0 で確定** |
