# qgb スキル本体 (Phase 5 Step 5.a-2 で本実装予定)

このファイルは Phase 5 Step 5.a-1 で作成した stub。Step 5.a-2 で full モード正本として本文を実装する。

実装時の前提 (Phase 5 v4 prejournal):

- full モードでは philosophy.md / stage-design.md / examples の要点を本文に直接埋め込む (大盛り、2-3 千語)
- split モード生成用に include marker (例: `<!-- split:helper_start workflow.md -->`) を仕込み、converter が full / split を単一正本から生成できるようにする
- trigger 表 (利用者の依頼語 → どの helper を読むか) を含める

参照: `development/docs/journal/phase5-prejournal.md` v4 §3.4 build mode, §3.5 trigger / hook 戦略
