# Phase 5 Step 5.e 記録: dogfood 残セルの消化 (進行中)

- 実施日: 2026-07-04〜 / 対象: acceptance の未消化セル 5 件。順序 = 機械化可能なものから (5→4→1→2、3 は証跡整理のみ)

## Item 5: setup-qgb.sh の POSIX 実機検証 — ✅ 合格 (CI 恒久化)

`test.yml` に `setup-script-posix` job を新設 (commit `21836a2`)、初回実行で green。検証内容: ubuntu-latest 実機で (a) build した setup-qgb.sh を素の user project dir で `--from-path` 実行 → `.venv/bin/python -m qgb --version` 成功、(b) install された版が pyproject.toml と一致 (lockstep 検証)、(c) 冪等性 (2 回目実行で .venv 内 marker が生存 + "already exists" メッセージ)。設計判断: デフォルト経路 (`git+...@skill-v<ver>`) は CI では**意図的に不検証** — 開発中 push では metadata が次版に bump 済みでタグが未存在のため必ず 404 する。デフォルト経路は実リリースごとの利用者 install で暗黙検証される。

## Item 4: japanese-docs-pwsh 実走 (θ+ι+κ) — ✅ 合格

scratchpad の日本語文書 testbed で PowerShell 5 経路をフル往復 (2026-07-04、qgb 0.1.4 editable):

- **契約**: BOM 付き UTF-8 の日本語 .ps1 (PS 5 規律準拠: `[Console]::OutputEncoding` / `$ErrorActionPreference='Stop'`)、argv 完全明示 (`powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ...`)、`runtime: "powershell-5"` (θ)
- **往復**: check DENY (仕込んだ用語欠落を正しく検出、日本語 FAIL 行が log に無傷) → 修正 → check ALLOW → run ALLOW (curated evidence + basis 3 件 + meaning verbatim)
- **κ**: check/run 両系統の stage log で U+FFFD = 0 を機械確認。「用語検査: 合格」等の日本語出力が PS5 パイプ経由で完全保全
- **lint 両実装 parity**: check-command-contract.{py,ps1} を同一 contract に実行 → **findings・exit code 完全一致**。しかも初回実行で C1 (runtime 宣言欠落) を実検出 — 設営者 (Fable 5) が書いた contract の実欠陥を lint が捕まえた。修正後は両実装とも advisory 1 件 ($OutputEncoding 推奨) + exit 0
- **κ 既知偽陽性の記録**: qgb repo 内の sentinel 文書 (5.a-2-4 の κ fixture) と lint script 自体は U+FFFD を正当に含む (検出パターンの定義のため)。repo 全域 grep での κ 監査時は `tests/fixtures/` と `skills/source/lint/` を除外して読むこと

## Item 3: A1' 一行変更の伝播 — ✅ 実戦消化済み (証跡紐付け)

v0.1.2 (`ad76912`) / v0.1.3 (`dc18fa1`) / v0.1.4 (`b6fecef`) の 3 リリースで「body.md 変更 → regen → golden test → CI 4 matrix + golden-integrity → 両系譜 release 検証」を 3 往復。うち v0.1.2 では独立レビュー must-fix の一行修正 → 再 regen の追い込み込み。保守シナリオとしてこれ以上の実証は不要と判断。

## Item 1: claude split の実走 — ✅ 合格 (split 参照機構は成立、新発見 6 件)

方式: golden の claude-split セルを testbed に配置し、Sonnet 運転で init → project-context → Pattern B → scaffold → contract (Python runtime) → check → run を実走 (2026-07-05)。native skill ロード自体は canary full で実証済みのため、本セルの検証対象は**分割参照の解決可能性**に絞った。

- **split 機構: 成立**。trigger 表と `@see` 行から workflow.md / references.md / prompts/design-stages.md / prompts/review-policy.md の全 helper に正しく到達し、ALLOW まで完走 (gate.json: meaning verbatim / scope P11 / basis 3 件 / κ クリア)
- **運転 agent の報告から新発見 6 件** (v0.1.5 候補、Codex smoke 完了後にまとめて Issue 化):
  1. **「§12」エイリアスが split で実害**: workflow.md 内の「§12 の capability-based dispatch checklist」等は split の実ファイルに §12 が存在せず検索不能 — 運転 agent は design-stages.md の通読で §5.5 を発見する追加コストを払った (v0.1.4 レビューで「既出荷慣行」と見送った件の実害実証。文書名 + 節番号への置換が必要)
  2. **§6.1 の手順順序が実機と矛盾**: step 6 (scaffold) が段階設計より先に書かれているが、実機は `policy.json#stages` 空だと scaffold を拒否する (`scaffold.py` L113 確認済)。文字どおり番号順に進むと必ず一度エラー
  3. **scaffold は `req/<REQ>.md` を生成しない** (実装確認済: meta.json + contract placeholder + gitkeep のみ)。SKILL.md §4 構造図と §6.2 step 3 は .md 雛形も出ると誤読させる
  4. **非対話実行の `--yes` が全文書に不記載**: `qgb run` は non-TTY で `--yes` 必須だが、workflow.md §6.2 step 7 も CLAUDE.md の CLI 一覧も素のコマンドを提示 — agent 経由が前提の Phase 5 スキルとして明白な欠落
  5. **patch の project-wide preflight 連動が §6.4 から読めない**: 無関係に見える小 patch が未充填 contract の blocker で弾かれる挙動
  6. **contract の TODO 初回充填が「直接編集禁止」(review-policy §4.3) と「contract の設計」(workflow §6.2 step 4) のどちらに該当するか曖昧** — 初回充填 = 設計 (直接可)、以後 = patch 経由、の線引きを明文化すべき
- 副次観測: 回答シート方式でも §3.5/§6.6 準拠の挙動 (設計分岐の knowledge 記録、human_reviewed の承認ベース true 化) が再現

## Item 2: Codex full/split smoke — (未着手、user 端末協力が必要)
