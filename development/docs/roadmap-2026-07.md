# qgb 今後の展望 (2026-07-05 時点)

Fable 5 (メインループ担当) の利用可能期間の区切りにあたり、現在地・確立した資産・今後の作業計画・遂行体制をまとめる。**本書は計画のスナップショットであり、正本は philosophy.md (憲章) → requirements_and_development.md → detailed-design.md の優先順位に従う。** 個々の作業の「なぜ」は `journal/` の各記録が一次資料。

## 1. 現在地

- **Phase 1〜3 完結** (Python CLI MVP → 構造化編集 → 機械責務側の最終整備)。Phase 4 は欠番。
- **Phase 5 (Skill Creator 化) は全 Step (5.a〜5.e) 完結** (2026-07-05、journal `phase5-step5-e.md` 総括)。skill リリース v0.1.0〜v0.1.4 公開済み。canary #1 (Fable 5 運転・機構検証) / canary #2 (Sonnet 運転・ブラインド維持・実運用ワークフロー) とも合格。
- **Phase 5 全体の完結宣言は未実施** — v0.1.5 (Issue #30) の扱いを決めてから、ドキュメント現実化とあわせて行う (§3)。
- 思想憲章は **v2.0** (P12「評価系もまた設計物である」追加、P6 の根拠を監査可能性 + 利害独立に再接地)。

## 2. この期間に確立した思想・設計資産 (今後の判断の土台)

1. **P12 と評価機の外部化・固定・校正** (philosophy v2.0): LLM/VLM/人間検査員も「qgb へ評価情報を渡すインターフェース」を守る評価機として枠組みに入れられる。P6 の禁止対象は「経路を通らない評価」であり、外部化・固定・校正された評価機は対象外。利害独立 (GMP 型) は原則、評価機設計段階の人間承認決裁を例外条件とする。
2. **「機構の事実は skill が開示し、方針の判断は利用者が所有する」** (canary #2 で確立、v0.1.4 §6.1 step 8 が初の明文化)。skill 設計の分岐が迷ったらこの線で切る。
3. **skill の合格ライン = 利用者代表 (Sonnet 級) が文言だけで完走できる水準**。「強いモデルなら動く」は品質保証にならない。canary は設営者と受験者の系統を分ける (P12 の独立性の実装)。
4. **オーケストレーション設計論** (`journal/orchestration-design-notes.md`): 至高は一発、以下は全て次善策 / ガチャの正否は検証コストで決まる (qgb はガチャの免許証) / 数より多様性 / 手戻り単価は検出位置 / 集約は指揮官課税 / 委任 prompt は能力でなく予算を指定する。
5. **バージョンの lockstep** (v0.1.4〜): skill (metadata.yaml) = qgb パッケージ (pyproject.toml) = リリースタグ。release CI が三点一致を機械強制。converter_version は独立。
6. **リリース基盤**: 決定論ビルド (golden 二系譜) + タグ整合ガード + rebuild-instead-of-transfer。文言バッチの実装テンプレ = Issue 起草 → 指揮側が文言確定 → sonnet 適用 → 独立レビュー 1 レンズ → 検収 → golden regen → CI → タグ → close (v0.1.2/0.1.4 で 2 回実証、毎回 must-fix を実検出)。

## 3. 直近の作業 (順序込みの推奨計画)

1. **v0.1.5** ([Issue #30](https://github.com/Yumeno/Quality-gate-builder/issues/30)): 5.e split 実走の発見 6 件 (「§12」エイリアス解消 / §6.1 手順順序 / scaffold 生成物の正確化 / `--yes` 記載 / patch preflight 連動 / contract TODO 初回充填の線引き)。全件文言修正、上記テンプレの 1 バッチ。緊急度低・工数小。
2. **Phase 5 完結のドキュメント現実化**: requirements_and_development.md §13 / detailed-design.md / CLAUDE.md / framework-shape.md (必要なら) を Phase 5 完結状態に揃え、完結 journal を書く。「ドキュメントは Phase ごとに現実装へ揃える」規律 (CLAUDE.md) の対象。
3. (任意) CI matrix への **Python 3.11 追加の再判断** — test.yml に「Phase 5 提供前に再判断」と明記した宿題。判断だけでも記録する。

## 4. 中期 (Phase 6 候補領域)

優先度順ではなく領域の列挙。着手時に理念 (P 番号) に照らして要否を判断する:

- **配布の階段の続き** (journal `phase5-step5-c.md` §3.5): 現在 = GitHub Releases (zip) + タグ固定 git+ install。次段 = **wheel を Releases に添付** (pip install の対象をタグから wheel へ)。終段 = **PyPI 公開 + 名前防衛** (`quality-gate-builder` / `qgb` の名前空間確保。公開時は SKILL.md §10.1 の「PyPI 未公開」文言の更新が必須連動)。
- **実運用 dogfood**: canary #2 の testbed (blog_survey_test) は実プロジェクトとして継続利用可能。「テストとしての canary」から「実需としての運用」へ移すと、v0.1.x の改善が実運用起点になる (5.d/5.e で発見の供給源はテスト設営から実運用に移りつつある)。
- **Step 3.3 (Phase 2 繰越実需回収) の再評価**: 「Phase 5 実需待ち」で任意繰越していた。Phase 5 完結により評価材料が揃った — 実需が観測されなければ close してよい。
- **他 agent 対応** (§10.4): Antigravity CLI 等は issue 駆動で判断。codex は 5.e で smoke 済み (full/split とも)。
- **bare `qgb` entry point** (Phase 3+ backlog、低優先): console_scripts 追加。PyPI 公開と同時が自然。

## 5. 長期・思想課題 (Fable 5 横断レビュー Part F 繰越分を含む)

- **waiver の期限 (expiry)**: waiver が永続免罪符化しない仕組み (期限 + 再審トリガ)。F-007 の運用強化。
- **human_attestation**: 人間承認の証跡構造化 (誰が・いつ・何を見て承認したか)。P12 の承認決裁を gate.json 級の機械証跡にする方向。
- **qgb-on-qgb (dogfooding)**: qgb 自身の開発に `.quality-system/` を張る。CI が既に機械ゲートの役を果たしているため実益との見合いで判断 (理念的完成度 vs 二重管理コスト)。
- **P12 評価機の実例作り**: 「外部化・固定・校正された LLM 評価機」の参考実装 (例: 表記ゆれ検査の LLM 評価機版 — canary #1 で「規模に比して過剰」と正しく不採用になった経路を、大規模プロジェクト向けに実際に通す)。評価機の校正記録・利害独立の設計例を examples/ に足すことも視野。
- **理念の対外発信**: 憲章 v2.0 とオーケストレーション設計論は記事素材として成熟している。要約・再構成は Haiku 級で可能だが、思想の本論は上位モデルまたは人間の筆 (配役原則)。

## 6. 遂行体制 (モデル承継)

Fable 5 の window 終了後も、体制は**役割で定義**されており代替可能:

| 役割 | 担当 (2026-07-05 時点の想定) | 備考 |
|---|---|---|
| 指揮・設計・憲章・検収 | Opus 4.7/4.8 (Fable 5 の後任) | 起点は本書 + CLAUDE.md + memory + journal |
| 実装 | Sonnet subagent | 文言バッチは §2-6 のテンプレどおり |
| 独立レビュー | Sonnet 別個体 (1 レンズ〜5 レンズ、変更規模で比例) | 縮退判断は journal に明記する |
| 横断監査 | Codex (`codex exec` / wrapper) | 異系統レンズ。不可逆 Step は r0/r1/r2 の 3 段 |
| skill 運転・canary | Sonnet | 利用者代表性 + 系統分離 |

引き継ぎ装置: **CLAUDE.md (規律) → auto-memory (作業の癖・過去の合意) → journal (個々の判断の「なぜ」) → 本書 (計画)** の 4 層。新しい指揮モデルはこの順に読めば、compact 済みセッションと同等の文脈で立ち上がれる (journal 文化の設計意図そのもの)。操縦様式は理念駆動 — 詳細で迷走したら P 番号に照らす問いを自分から出すこと (memory `rinen-driven-steering`)。

## 7. Open Issues / 未起票 backlog 一覧

| 項目 | 状態 | 出所 |
|---|---|---|
| v0.1.5 文言バッチ | **Issue #30 (open)** | 5.e item 1 |
| Phase 5 完結ドキュメント現実化 | 未起票 (直近作業 §3-2) | CLAUDE.md 規律 |
| CI 3.11 再判断 | 未起票 (判断のみでも可) | test.yml 内コメント |
| wheel 添付 → PyPI + 名前防衛 | 未起票 (Phase 6) | 5.c 配布の階段 |
| Step 3.3 再評価 | 未起票 | Phase 3 繰越 |
| 5.b-ci 残 (BuildError 境界完全統一 / regen のセル列挙を metadata 由来に) | 未起票 (低優先) | 5.b 段階 5 |
| waiver expiry / human_attestation / qgb-on-qgb | 未起票 (長期) | Fable 5 横断レビュー Part F |
| Antigravity 等の他 agent 対応 | 未起票 (要望駆動) | SKILL.md §10.4 |
