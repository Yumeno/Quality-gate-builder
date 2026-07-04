# Phase 5 Step 5.d canary #2 完結ジャーナル (Claude full / Sonnet 運転 / ブラインド維持)

- 実施日: 2026-07-04 / 場所: `C:\Users\vz7a-\Desktop\blog_survey_test` (無害なフォルダ名、user 設営)
- シナリオ: **note 向けブログ記事の AI 執筆実験** — 取材 (sonnet/haiku サブエージェント並列) → 執筆 (sonnet サブエージェント) → qgb 監査、の実運用ワークフロー。記事 3 本 (紹介記事 5,000 字 ×2 + 論説 10,000 字) すべて ALLOW 到達
- skill: v0.1.2 claude-full (INSTALL.md / setup script は漏洩対策で削除済み)。qgb 本体は user が事前に .venv へ local path install
- 運転 agent: **Sonnet 5** (canary #1 の教訓「設営者と受験者の系統分離」を適用)
- 一次資料: testbed の git 履歴 4 commits (`984f042`→`be58b62`) + `.quality-system/` + セッションログ (393 イベント)

## 1. ブラインド: 最後まで維持 (canary #1 の失敗から改善)

系統分離 (Fable 5 設営 → Sonnet 受験) + 無害なフォルダ名 + 実在の執筆課題で、運転 agent は一度もテストを疑わなかった。canary #1 §5 の実験設計が機能した。副産物として「Sonnet は言われた通りにやり、言われないことはやらない」という利用者代表性が確認され、**skill 文言の欠陥がそのまま挙動に写る**測定器として理想的だった (Fable 5 は地力で穴を暗黙に埋めてしまい検出できない — canary #1 で実証済み)。

## 2. v0.1.2 改善 2 項目の効果測定 — 両方陽性

- **§3.5 決定の所有権: 効果あり**。設計分岐ほぼ全て (検査対象 / テーマ合致の判定方式 / パラメータ置き場 / 閾値 / adopt 承認 / 証跡保持単位 / REQ 命名 / commit ルール適用範囲) で選択肢提示 → 利用者選択が実行された。実装前に「この設計案でよいか、実装に入る前に確認します」と停止する挙動も出現。canary #1 で観測した「相談なしの高速既成事実化」は消滅
- **§6.6 記録規律: 効果あり**。「設計判断を knowledge.jsonl に記録します (**記録トリガ: 設計分岐の選択**)」とトリガを名指しで引用して自発記録 (2 件)。3 件目 (commit サイクル標準化) は user の問いかけが引き金だが、問いを受けて §6.6 トリガに自己照合して追記した。全 3 エントリが「採らなかった案と理由ごと」の模範形式。比例原則も遵守 (過剰記録なし)

## 3. 機構の実証 (canary #1 の再現 + 上積み)

- check→run のリハーサル規律を全 REQ で遵守。DENY→ALLOW 往復 (REQ-002 文字数不足 4,850/5,000 → 執筆エージェントに SendMessage で加筆依頼 → ALLOW) が git 履歴に残る
- **P5 の実演としては #1 より本質的**: 「LLM が生成 → 機械ゲートが落とす → 改訂 → 再判定」のループを、生成も改訂もサブエージェントが担う編成で完走。DENY を「失敗ではなく改訂のシグナル」として利用者に説明する文言も §3.1 通り
- gate.json 模範 (meaning verbatim / scope P11 / basis 完全 / mode 区別)。argv[0] は **§6.5 準拠を明言して最初からネイティブ区切り** — canary #1 の教訓が v0.1.2 経由で完全消化された
- 運用ルールの発明: `evidence/latest` 上書き問題を利用者の質問に対し機構レベルで正直に開示 → REQ 粒度の再設計 (slug 毎連番 + `_index.json` 対応表) + **req-binding 段階** (meta.json / 対応表 / 実行中 REQ の三者一致を機械検査) を利用者と共同設計。「運用ルールに留めず機械検査化」は qgb の思想の正しい消化
- .gitignore 衛生 (.venv / settings.local.json / __pycache__)、push 前の remote 確認など周辺規律も良好

## 4. 躓きの実測 → v0.1.4 (Issue #29) の裏付け

1. **schema drift 2 連発** (§3.2 proposal 例 → project-context の object 配列)。回復コスト ≈ 18 イベント。adopt / validate の機械境界が誤り proposal の焼き込みを阻止 (P5 が skill 文言の嘘から利用者を守った)。特筆: 運転 agent は**自力で「site-packages の同梱スキーマを読む」= v0.1.4 item 4 の設計そのもの**に到達 — 改善案の方向の実地証明
2. **examples 不在**: Glob で探して不在確認 → 自力設計に graceful degradation。影響軽微と実測
3. **バージョン 3 空間の混乱**: 冒頭の「0.1.0 認識」の出所は `qgb --version` = **qgb Python パッケージ版 (pyproject、未 bump)**。skill 版 / converter 版 / パッケージ版の 3 空間があり、v0.1.3 (skill_version ヘッダ) が直したのは 1 空間のみ
4. **project-context.json `human_reviewed` が終始 false**: agent は「ユーザーのみが立てる規律」と正しく自制したが、利用者に立ててもらう工程がフロー上一度も発生しない
5. **commit サイクルの設計分岐は user 発**: skill はこの分岐を提示しなかった (item 5 の欠落の実演)。提起後の挙動 (適用範囲の確認 → knowledge 記録 → 準備/草稿/ALLOW の 3 commit 実行) は完璧

## 5. 判定と次工程

**canary #2: 合格。** ブラインド下の利用者代表 (Sonnet) が、skill 文言 + 機械境界だけで実運用ワークフローを完走。v0.1.2 の対話規律 2 項目は測定可能な行動変化として確認。躓きは全て機械境界内で回復し、v0.1.4 (Issue #29、6 件) の要求仕様として回収済み。

付随収穫: 取材フェーズのレートリミット嵐 (研究サブエージェントの内部多段展開) はオーケストレーション設計論の実測データとして `orchestration-design-notes.md` §5 に記録。

残: 5.e (Codex smoke + 保守シナリオ + POSIX setup 検証) → v0.1.4 実装。
