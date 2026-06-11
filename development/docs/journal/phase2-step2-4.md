# Phase 2 Step 2.4 — daily verification channel 作業記録

着手: 2026-06-11
完結: 2026-06-12 (計画 Codex レビュー → 着手前判断 [案 A、prejournal] → 本体実装 → 段 1 観点別 5 subagent (Explore 失敗 → default 再投入) → 補修 A1-A7 → backward-compat 再投入 → 補修 B1-B3 → 段 3 Codex 横断 (sandbox エラーで提示ベース) → 段 5 実コード同梱 2 周目「指摘なし収束」)

## Step 2.4 のスコープ (detailed-design.md §13.2)

`qgb run` を curated 証跡を汚さずにリハーサルする日常検証チャネル。

### 完成した機能

- **`qgb check REQ-ID`** — official run rehearsal。`run_preflight` → `run_stages` → `decide` を `qgb run` と共有 (DRY/P9) し、`write_evidence` を呼ばず check 専用 writer で `.quality-system/artifacts/<REQ>/checks/<ts>-<runid>/` にのみ gate.json / summary.md / stages/*.log を出力。exit 0=would ALLOW / 1=would DENY / 2=NOT_READY。F-008 プロンプトなし (curated を変異しないため)。knowledge orphan は **advisory 表示のみ** (unrelated orphan blocker が daily check を止めない — Step 2.3 申し送りの解)
- **`qgb check`** (REQ 省略) — project-wide validate-policy 診断のみ (orphan blocker は exit 2 で enforce)。`--phase` 指定時は無視警告
- **`qgb dev`** — thin alias (watch / changed-files は Phase 3)
- **`mode: "check"`** — gate schema 共用で check gate のみ mode を持つ (公式 run gate は mode 不在 = byte 互換)。mode=check のとき `paths.curated_latest_dir` 禁止 / 不在のとき必須 (allOf 条件)。decision.meaning は公式文言 verbatim + rehearsal note suffix、summary.md に日本語 banner
- **prune** — QGB_KEEP_RUNS 流用で checks/ 木のみ (runs/ は不変)

### 着手前判断 (prejournal: phase2-step2-4-prejournal.md)

計画文言 `.qgb/tmp/check/` は「init が `.qgb/` を gitignore 予約済み」という**事実誤認**由来と判明 (実際の予約は `.quality-system/artifacts/` のみ)。理念照合 4 点 (P7 同種同所 / tool-private でないものを `.qgb/` に置くのは分類の誤り / NF-010 表面積最小化 / 境界 3 の正本は curated 不変でパスは例示) で **案 A (`artifacts/<REQ>/checks/`) を user 確定**、§13.1 改訂 (版 0.21、commit bff04fb)。

## 段 1 観点別 5 subagent レビュー

### プロセス事故と恒久対応 (今 Step の重要な学び)

初回投入 (`subagent_type: "Explore"`) は複数 agent が PowerShell `Get-ChildItem`、`cd /d ... && grep` 連結、**絶対パスの手打ちミス** (`OneDrive` → `OneDike`/`OneDonde`/`OneDoing`) で承認申請を多発させ全 reject。対応:

1. memory `parallel-strategy` テンプレ強化 (PowerShell 禁止 / パスはコピペ・相対パス / Explore type 不使用)
2. settings に非破壊傘追加 (`Read(//c/Users/vz7a-/**)` / `PowerShell(Get-ChildItem *)`、user 承認)
3. memory `bash-permission-patterns` 新設 (&&連結 / 変数代入 / リダイレクトで包むと傘から外れる)
4. skill `ask-codex-with-context` の手順例を許可設計と整合する形に補修 (mktemp/heredoc/`RESPONSE=$()` 例の排除)
5. **再投入は default agent + 「要実機確認タグで報告、実行は host が代行」の出口明示** — backward-compat 再投入では申請ゼロで完走し、タグも設計通り使われた

再投入後の 4 観点 + backward-compat の指摘は、probe 依存の主張を host が静的読みで全件裏取りしてから採用した。

### 補修 A 系 (correctness / edge-cases / windows / test-quality)

| # | 重要度 | 内容 |
|---|---|---|
| A1 | 高 (windows) | CLI 実行時出力の U+2014 → ASCII 化 3 箇所。cp932 リダイレクトで UnicodeEncodeError → 未捕捉 exit 1 が would-DENY と衝突する経路を排除 |
| A2 | 中 (edge) | knowledge.jsonl の byte-torn tail (multi-byte 文字途中で切れた partial tail) で UnicodeDecodeError クラッシュ → validate.py / knowledge.py を `read_bytes().decode(errors="replace")` 化し torn tail を既存 partial-tail skip に合流 |
| A3 | 中 (3 観点が同一指摘) | gate.runtime.schema.json の waived 未対応 (Step 7 drift)。check gate は揮発木にしか存在せず load-bearing 化 → enum + ALLOW/DENY allOf (all-waived oneOf 分岐含む) を curated と同義に |
| A4 | 低 | 文書化: basis fidelity over resolvability (check の KNOWLEDGE-WAIVER 行は公式 run 前は未解決 id) / Windows lock 下の prune 繰越 / curated schema が mode=check を受理する consumer 注記 |
| A5 | 低 (edge) | REQ 省略 + `--phase` の黙殺 → stderr 警告 |
| A6 | 中 (test-quality ×2) | snapshot fixture を read_text → **read_bytes + dir 記録** 化 (CRLF 書換・空 dir 作成を検出可能に、"byte-identical" の看板を実体化) |
| A7 | 高〜低 | テスト +11: waived REQ の check ×3 (**run と check が分岐する唯一の世界状態**)、runs/ 不 prune、env 経由 prune、meaning 等値 (F-016 verbatim 保証)、phase=red、DENY schema 検証、orphan advisory text、dev text、--phase 警告 |

### 補修 B 系 (backward-compat、補修後状態に再投入)

| # | 重要度 | 内容 |
|---|---|---|
| B1 | 中 | A2 の残余クラス: JSON 文字列値内部の byte 破損が U+FFFD 置換後も構文 valid なまま黙過 (旧: loud crash → 新: silent pass の後退)。validate.py は**終端行**の U+FFFD を read_error (torn tail のみ skip 維持)、knowledge.py の 2 reader は U+FFFD 行から一切結論を導かない (garbled applies_to による bogus orphan blocker 防止) |
| B2 | 低 | schemas/README.md に checks/ 木 / mode / waived 追補を反映 |
| B3 | 低 | snapshot dir marker をファイル内容と衝突不能な object() sentinel に |

backward-compat 判定: schema 再構成は mode 無し文書に対し受理/拒否集合不変 (微妙ケース机上検証済)、公式 run の gate.json / summary.md は byte 不変、runtime schema の mode キー名予約は意図的縮小 (実害なし、記録)。

## 段 3/5 Codex 横断レビュー

1 周目: 「中程度以上の新規 cross-seam finding なし」— 継ぎ目 4 点 (Step 2.5 拡張性 / mode と Step 2.7 strictness / 破損検出規約と Step 2.3 保証文言 / 三重の official・rehearsal 区別) すべて整合と判定。ただし sandbox 起動エラーで実コード未読のため「コード本文にのみ現れる不整合は未検出リスク」と注記。

2 周目 (実コード主要部を context に同梱、確立済みパターン):

> 判定: **指摘なし収束** でよいです。… 1 周目の未検出リスクだった「実コード本文だけに出る不整合」は解消確認できています。

## 成績

- pytest: 666 (Step 2.3 完結時) → 686 (本体 +20) → 697 (A 補修 +11) → **698** (B 補修 +1)、全緑
- ruff: clean
- 新テスト: tests/test_check.py (32)
- 公式 run の出力は byte 不変 (mode 不在経路)、既存 example / fixture 無変更通過

## Phase 2 後続 Step への申し送り

### Step 2.5 (Pattern B)

- check は override seam を使わず disk world を検査する。proposal 適用後の world を check したい場合は「仮想 overlay として読む別 seam」になる (Codex 1 周目注記) — propose/adopt の設計時に「adopt 前検証は validate_policy_preflight の override seam / adopt 後検証は qgb check」という分担で足りるかを最初に確認すること
- 既存申し送り維持: contract_overrides key = canonical contract_ref / 複数 doc 同一 world / knowledge.jsonl は JSON Patch 対象外 / EditError.reason・PatchApplyError.reason 安定 API

### Step 2.7 (strictness review)

- `mode` を予約済み discriminator として扱う (Codex)。additionalProperties: false 全面適用判断時に mode=check 文書の curated schema 受理 (A4 で注記済み) を再訪
- gate.schema.json と gate.runtime.schema.json の意味論二重保守 (A3 で同義化したが、構造的に重複) の解消可否
- helper 重複整理に追加: tests/test_patch_apply.py の local `_snapshot_dir` (str 版) と conftest `snapshot_dir` (bytes 版) の統合
- 既存: formats strict 化 / `$id` 明文化 / log アサーション規約 / 命名統一 / force warning 文言

### Phase 3 送り (§13.5 繰越判定行き、記録のみの低指摘)

- 書込中 check dir の prune 競合 (runs/ と同根の既存クラス、daily channel 化で暴露面は拡大)
- req_id 形式検証なしの filesystem パス流入 (run と完全パリティ)
- stage_id の filesystem-unsafe 文字 (`:` / `\` 等) で stage log 書込が OSError (Phase 1 write_evidence と同根)
- 全 REQ 一括 check / QGB_KEEP_CHECKS 専用 env / watch mode / changed-files

## プロセス軸の変化 (Step 2.4 で確立したもの)

- **subagent 規律の第 3 世代**: テンプレ (hook 注入) + 「要実機確認タグ」の出口 + default agent 固定。禁止だけでは破られる (Explore 事故) — 「実行は host が代行する」という具体的な退路を prompt に書くことで初めて成立した
- **probe 主張の裏取り規律**: agent の「実機確認済み」は鵜呑みにせず、host が静的読みで再検証してから補修判断に使う
- **許可運用**: 否認ベースの調整プロトコル (user 提案) が 2 サイクル回り、bash-permission-patterns / codex-context-files / parallel-strategy の 3 memory + settings 傘 2 件 + SKILL.md 補修に結実。backward-compat 再投入と Codex 2 周は申請ゼロ
- 規模実績: 約 1.0 (計画 1.0 と一致)
