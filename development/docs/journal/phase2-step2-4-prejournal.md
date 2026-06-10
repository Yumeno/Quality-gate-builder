# Phase 2 Step 2.4 — daily verification channel 着手前判断記録 (prejournal)

記録日: 2026-06-11
状態: 実装着手前。Codex 計画レビュー受領 + 揮発出力先の user 確定まで完了。

## 1. 計画レビューの経緯

- コンテキスト: `codex_ctx_p2_step24_plan_20260611-003401.txt` (Step 2.4 スコープ +
  現行アーキテクチャの事実 + 実装方針案 + 相談観点 10 件)
- Codex 判定: 「現方針は大筋で妥当。`run_preflight → run_stages → decide` を共有する
  方向は P9 と Step 2.5 に対して一番きれい」+ 中程度以上の設計リスク 5 件

## 2. 着手前に発見した事実誤認 (計画文言の修正理由)

§13.2 完了条件の「tmp artifacts が .gitignore に自動追加される (init で既に予約され
ている `.qgb/` 配下)」は **事実誤認** だった。init が .gitignore に予約するのは
`.quality-system/artifacts/` のみ (`init.py` `_GITIGNORE_ENTRY`)。`.qgb/` は
どこにも予約されていない。§13.1 境界 3 の `.qgb/tmp/check/<timestamp>/gate.json`
というパス例示はこの誤認の上に書かれていた。

## 3. 揮発出力先の判断 (案 A 採用、user 確定 2026-06-11)

| 案 | 内容 |
|---|---|
| **A (採用)** | `.quality-system/artifacts/<REQ>/checks/<ts>-<runid>/` — 既予約の揮発木に同居 |
| B | 計画文言通り `.qgb/tmp/check/` 新設 + init に `.gitignore` 追記を実装追加 |

理念照合 4 点 (user への提示内容、いずれも案 A を指した):

1. **P7 (同種のものは同じ場所に)**: check の出力は「REQ に対する検証機構の出力」で
   あり run の揮発出力と同種。`runs/` と `checks/` が並ぶことで公式とリハーサルの
   関係が構造自体から読める。証跡の場所が予測可能になる
2. **`.qgb/` は分類の誤り**: tool-private な状態 (キャッシュ等) なら外出しが正しい
   が、check 出力はユーザーが読む前提の per-REQ 検証結果であり tool-private では
   ない。構造が実態を偽る。将来本物のキャッシュが生まれたとき初めて `.qgb/` は
   正当化される
3. **NF-010 (表面積最小化)**: 案 B は新 top-level dir + 新 gitignore 規約 + init
   責務拡張 + 既存プロジェクト再 init 手当てと不変条件を 4 つ増やすが機能利得ゼロ
4. **境界 3 の正本は「curated 不変」**: 原文は「`.qgb/tmp/...` **のような**揮発パス」
   で、パス字面は例示。誤認に基づく例示を正本扱いしない (Step 2.3 B3 の「保証の
   過大表現を文言側で直す」と同じ向き)

Codex も同判断 (「実務上いちばん強い」)。ただし「設計境界 3 の変更として明示承認
necessary」との指摘に従い user 確認を経て確定。§13.1 / §13.2 改訂済 (版 0.21)。

## 4. Codex 計画レビュー指摘 5 件と確定対応

1. **check に validate-policy をどこまで含めるか**: `qgb check REQ` の主責務は
   「official run rehearsal」。exit code を支配するのは run_preflight + verification
   のみ。knowledge orphan は advisory 表示 (exit に影響しない)。project-wide orphan
   blocker で無関係 REQ の daily check が落ちるのは日常導線として重すぎる
   → Step 2.3 申し送り「unrelated orphan blocker 問題」の解
2. **tmp パス変更は境界 3 の明示承認必須** → §3 の通り user 確定済
3. **mode:"check" の誤認対策はフィールドでも**: decision.meaning 文言だけでは機械
   利用者に弱い。`mode: "check"` (schema enum 拡張) + evidence_dir が check tmp を
   指す + 出力での「curated evidence not updated」明示 + ALLOW は「rehearsal would
   allow」表示、をセットで
4. **"read-only" と呼ばない**: command stage を実行する以上、表示・help・docs は
   「does not update curated evidence」と言い、safe/read-only は避ける (NF-010)
5. **check tmp の prune を Step 2.4 で**: write_evidence を呼ばないと QGB_KEEP_RUNS
   の prune も効かない。`QGB_KEEP_RUNS` 流用で checks/ にも prune を入れる
   (専用 env `QGB_KEEP_CHECKS` は Phase 3)

## 5. 相談観点 10 件の確定 (Codex 回答の採否)

| # | 観点 | 確定 |
|---|---|---|
| 1 | tmp 出力先 | 案 A (§3) |
| 2 | REQ 省略時 | project-wide validate-policy 診断のみ (verification なし、揮発出力なし、exit 0/2)。全 REQ 一括 check は Phase 3 |
| 3 | 出力 document | gate schema 共用 + mode:"check"。専用 schema は二重管理になるため作らない |
| 4 | 副作用 | command stage は実行する (リハーサルの価値)。F-008 プロンプトなし、`--yes` 不要。help に「verification commands may run」明記 |
| 5 | orphan blocker | (c) 系: run_preflight が exit を支配 + orphan advisory 表示。project-wide orphan は REQ 省略時 / validate-policy の責務 (P9) |
| 6 | qgb dev | thin alias で実装 (check handler に委譲)。help に「currently equivalent to check; watch mode is reserved (Phase 3)」 |
| 7 | exit code | run と同じ 0/1/2 (スクリプト一貫性優先)。表示は「would ALLOW / would DENY」で rehearsal を明示 |
| 8 | 命名/prune | `<ts>-<runid>` 予約ロジック (`_reserve_run_dir`) を再利用 (Windows first-class の衝突堅牢性)。prune は QGB_KEEP_RUNS 流用 |
| 9 | テスト | snapshot_dir fixture で curated 不変 + knowledge.jsonl 不変 + `artifacts/<REQ>/runs/` 不変を machine-verify。「check 専用 tmp だけが増える」ことを検証 |
| 10 | 規模 1.0 | 上記すべてで 1.0 内。Phase 3 送り: watch / changed-files / 全 REQ check / 専用 check schema / 専用 keep env / orphan UI 改善 |

## 6. 実装構成 (予定)

- `qgb/core/check.py` (新設): check orchestration + check 専用 writer。
  `evidence.py` の部品 (`make_timestamps` / `_reserve_run_dir` / `build_basis` /
  `build_gate_document` / `build_summary_md` / prune 系) を再利用するが、
  curated swap / waiver knowledge append は**呼ばない** (P9: evidence.py は
  official evidence の writer のまま)
- `qgb/schemas/gate.schema.json` (+ runtime variant があれば同様): mode enum に
  "check" 追加。if/then 整合性制約との関係は実装時に精査
- `qgb/cli.py`: `check` / `dev` subcommand
- tests: `tests/test_check.py` (+ CLI レベル)

## 7. Step 2.5 への接続 (この Step で保証すべきこと)

- check が run と preflight / verification 経路を共有していること (Pattern B の
  adopt 前検査で同じ部品を使う前提)
- 正式 evidence (curated / knowledge / runs) を汚さない保証が machine-verify
  されていること
