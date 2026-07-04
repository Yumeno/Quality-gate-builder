# Phase 5 Step 5.d canary #1 完結ジャーナル (Claude full / Fable 5 運転)

- 実施日: 2026-07-04 / 場所: `C:\Users\vz7a-\Desktop\qgb-canary-docs` (qgb repo 外の独立 git repo — CLAUDE.md 継承と project root 汚染の回避)
- 素材: SD メモ集を装った日本語文書 4 本 + 仕込み欠陥 2 種 (リンク切れ / 表記ゆれ 4 変種)
- skill: **v0.1.1 release zip を GitHub Releases から実配布経路で取得**して `.claude/skills/qgb/` に配置 (claude-full)
- 運転 agent: Fable 5 / 観察者: user (qgb 作者) + 本セッション (設営・分析)
- 所要: セットアップ〜初回判定 12m17s (「導入が重い」リスクの初計測値)

## 1. ブラインド失敗 (即時の教訓)

開始直後に運転 agent が実験設営を看破 (敗因: フォルダ名 `qgb-canary-docs` / 教科書的な欠陥 / **設営者と受験者が同系統 Fable 5** = 直感の共有)。→ §3.5 の「初心者への親切さ」テストは観測不能化 (専門家適応モードに収縮 — これ自体は §3.5 準拠挙動)。**P12 独立性原則の実測例**として記録: 試験の設営者と被験 agent の系統は分けるべし。

## 2. 機構の実証 (全項目 green)

- skill 発火 (`Successfully loaded skill`) / §6.1 新フロー (qgb 可用性確認から開始)
- **venv 認識規律**: .venv 作成 + タグ固定 install + contract argv に `.venv\Scripts\python.exe -X utf8` (ι の Python checklist が契約レベルまで浸透)
- **Pattern B 完全往復**: proposal 起草 → user 承認 → adopt 機械検証 → policy 焼き込み (SHA-256 監査記録)
- **構造化編集規律**: contract は全て `qgb patch` 経由 (直接編集ゼロ)
- **θ/ι/κ**: 検査実体 = tests/quality/ Python 3 本 + terminology.json、`-X utf8` / `errors='strict'`、日本語ログ無事
- **判定往復の証跡化**: DENY 証跡を commit (651a50f) → 修正 → ALLOW 転換 (0d50362) → 再チェック ALLOW 継続 (48c584d) — P5「落とせるから何度でも生成できる」の一往復が git 履歴に残る構成
- **gate.json 模範**: meaning F-016 verbatim + scope P11 / basis[] = REQ/POLICY/CONTRACT のみ / 全 stage に exit_code + log_ref。DENY 時 failed_stage=links、verify-DENY の「signal to revise」文言
- 実地トラブル 2 件 (project-context 形式ミス / Windows CreateProcess の `/` 区切り argv[0]) を **preflight・機械検証が gate 到達前に阻止**
- 段階設計 3 段 (structure/links/terms、responsibility 一文、DAG) — 4 ファイル規模に比例した設計 (P10)
- scaffolding 分量: `.quality-system` 124K (artifacts ログ込み)。導入の重さは「一回きりの初期コスト + 運用は evidence 追記」の構造

## 3. 発見能力の実証 (運転 agent 自身の切り分けが正確)

- links/structure = **一般検出器** (答えを知らずとも全数検査) → 実証 ✅
- terms = **知識のエンコード** (「読んで見つけたものを機械が追認」— 自作自演のため発見能力は**未実証**)。運転 agent 自ら「発見の貯金箱 (再発防止の恒久化)」と正しく再定義し、当初の「全件検出」主張を実質撤回
- 表記ゆれの被覆問答: 「禁止表記リストとの照合であり言語処理的な賢さは一切ない」+ 限界 3 点開示 + P12 経路 (LLM 評価機) に言及した上で規模比例で不採用 — **P5 の模範応答**

## 4. v0.1.2 候補 (skill 改善)

1. **決定所有権の条項**: §3.5 は「説明の深さの適応」と「決定の所有権」を区別していない — 設計序盤、相談なしで検査観点を高速設定した (adopt 関門では停止したが、fait accompli のゴム印リスク)。「自信があっても設計の分岐点は必ず提示して選ばせる。専門家相手に説明を省くのは正しいが、決定を代行してはならない」
2. **話題単位の理解度観察**: 作者 ≠ 全知。人物単位でなく話題単位で調整
3. §12.5.5 Python checklist に **argv[0] は OS ネイティブ区切り** (CreateProcess は `/` 相対パスを解決しない) を追記
4. **記録の規律 — knowledge.jsonl は利用者プロジェクトの journal** (原因究明済み 2026-07-04、[Issue #28](https://github.com/Yumeno/Quality-gate-builder/issues/28) に文言案): canary で空だったのは agent の怠慢ではなく **skill 文言の欠落**。body.md の knowledge.jsonl 記載は境界規則 (外部隔離 P8 / waiver / advisory 分離) のみで、能動的な知見記録 (F-013 の本来目的) を促す文がゼロ。憲章紐付け: gate = 「何が通ったか」(P7)、knowledge = 「なぜそう決めたか」= 評価系という設計物 (P12) の設計記録であり、次にプロジェクトを触る者への引き継ぎ。qgb 開発 repo 自身の journal 文化 (途中参加モデルの即稼働を実証) の利用者プロジェクト版。記録トリガ 4 種 + 比例原則 (判断が発生したときだけ) を §6 に追加する

※ v0.1.2 の 4 件は Issue #28 に集約 (実装は body.md 改訂 + golden 再生成 + release の 1 バッチ)

## 5. canary #2 の実験設計 (運転 agent 自身が起草、採用)

- **Sonnet 運転** (利用者代表性 + 系統分離) × **user が初心者を演じる** (§3.5 の初心者モード観測)
- フォルダ名は無害に / 素材は実文書 or user が秘密裏に仕込む
- terms の発見能力テスト: ルール表**内**の変種を秘密裏に混入 → DENY を確認 + 表**外**の変種は素通りすることの**ネガティブコントロール** — 段階の守備範囲を正確に測る

## 6. 判定

**5.d canary #1: 機構検証として合格。** Claude full cell の「配置 → 起動 → 深い対話」economy が実配布物で成立。acceptance-matrix の manual smoke (Claude full) 達成。5.e (深 dogfood + Codex smoke + 保守シナリオ) と canary #2 へ。
