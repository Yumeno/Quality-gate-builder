# v0.1.6 skill 文言改善バッチ (TDD 実走 qgb_soukoban の発見反映)

- 実施日: 2026-07-12 / 仕様: [Issue #31](https://github.com/Yumeno/Quality-gate-builder/issues/31) (確定コメント 3 本が正本: 初期 2 件 + item 3 合意 + ログ解析確定 + gpt-5.6-sol レビュー修正)
- 由来: qgb_soukoban (倉庫番ゲーム、skill v0.1.5、Fable 5 指揮 + Codex 実装 + Sonnet 異観点レビューの実運用) のセッションログ解析 (502 events)
- 編成: Fable 5 指揮 (文言確定・検収) + sonnet 実装 + sonnet 独立レビュー 1 レンズ。スコープ自体は事前に gpt-5.6-sol の内容レビュー済み (組み込みタイプ免除の撤回 / 依存判定テスト / red の exit code 非反転、の 3 修正を反映)

## 実装内容 (4 items)

1. **§3.5 に時間方向の規律**: 承認待ち中は承認対象に依存する後続作業を並行発進させない。判定テスト「承認案が変わったら成果物の変更・破棄が必要か?迷ったら依存扱い」。根拠は P12 (評価系の設計が既製の実装に引っ張られる利害同一化) — 実走で指揮 agent 自身が「3 系統並行発進」した事件 (機械関門は無傷) の対処
2. **§6.7 新設 — サブエージェント委任の規律**: 子は skill を読んでいない。委任 prompt に最小規律セット (承認状態 / 禁止操作 / 実行経路 / 成果物は候補) を毎回含める。実走でリカバー後の運転者が自力発明した形式の規範化
3. **§6.8 新設 — 検証系の校正**: ALL GREEN は検査が機能している証明ではない (弁別力)。対象は**利用者が構成した全検査インスタンス** (組み込みタイプの設定ミスも常緑になる — sol レビューで免除範囲を修正)。強い順に恒久メタテスト / 一度の観測記録 / 受容、選択は利用者 (§3.5 の型) + §6.6 記録
4. **§6.9 新設 — TDD mode の最小案内**: 実走では「TDD で実装」の文脈でも phase=red が一度も使われなかった (全 gate verify)。red→green→verify の骨子 + **exit code 非反転の明記** + 4 値 (red/green/refactor/verify) と red の ALLOW = unexpected pass (decision.py 実装で裏取り)

派生: §6.2 step 4 から §6.8/6.9 へのポインタ、§2 trigger 表に 2 行 (TDD / 委任・校正)。version lockstep 0.1.6。

## 検証

- 846 passed, 3 skipped / py -3.10 と 3.13 で digest 一致 (最終 `e19b3516e5bbe5a8`) / §6.7〜6.9 の番号衝突なし (事前 grep ゼロ確認)
- 検収補正 1 件: §6.9 が --phase の 4 値と refactor の存在に触れていなかった → decision.py の phase 意味づけ (red のみ特別、red+ALLOW=unexpected pass) を裏取りの上追記
- 独立レビュー (sonnet 1 レンズ): **must-fix ゼロ**。機械正本 (cli.py / decision.py / F-016) との一致、split 跨ぎ参照の既存規約整合、P12「校正」の適用拡張が憲章原文に忠実であること、metadata description 非更新が既存慣行であることまで裏取りされた。nice-to-have 1 件 (trigger 表から §3.5 判定テストへの直接参照) を反映済み

## 関連

- evidence↔ソース紐付け (provenance) は Issue #32 として別トラック (qgb 本体、Phase 6 候補。オプション検討 + 理念ガードレール P3/P5 済み)
- 実走の副次観測 (P5 限界→P12 応答の模範ループ、timeout 変更管理、難易度評価機の校正サイクル) は走行完了後の総括 journal で扱う (qgb_soukoban 側にも記録あり)
