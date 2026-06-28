# qgb skill lint (Phase 5 Step 5.a-2-4)

`verification_type=command` の contract.json と script を skill 内部で検査する portable helper。Codex 設計再検討レビューで推奨された **(η改) θ command authoring protocol + ι capability-based dispatch** の実装の一部 (skill 内部 lint、qgb 本体機能ではない)。

## 配置

| ファイル | 役割 |
|---|---|
| `check-command-contract.py` | Cross-platform Python 実装 (Windows / macOS / Linux 共通)、Phase 1 から runtime 依存の Python 3.10+ で動く |
| `check-command-contract.ps1` | Windows native PowerShell 実装 (PS5/7 両対応、pure ASCII + Unicode escape で BOM 不要) |

dist build で converter が `dist/skills/{full,split}/{claude,codex}/lint/` 配下に copy される (`build_input_digest` カテゴリ 4 同梱 hook と同様の扱い、5.b 実装時の必須項目)。

## 利用タイミング (skill agent が自動実行)

`verification_type=command` の contract を新規作成 / 既存編集した直後、`qgb design-stages adopt` 前に skill agent が以下を呼ぶ:

```powershell
# Windows native
powershell -ExecutionPolicy Bypass -NoProfile -File <skill_install>/lint/check-command-contract.ps1 `
  -Contract <contract.json path> -Script <script.ps1 path> [-Evidence <stage.log path>]
```

```bash
# Cross-platform
python <skill_install>/lint/check-command-contract.py \
  <contract.json path> [--script <script path>] [--evidence <stage.log path>]
```

exit 0 → adopt OK (fix-required findings なし、advisory note があっても 0)。
exit 1 → fix required (proposal を直す)。exit 2 → usage error。

## 検査項目 (6 件、body.md §6.5 + §12.5.5 と対応)

| ID | 種別 | 検査内容 | 失敗例 |
|---|---|---|---|
| **C1** | fix-required | script 拡張子と confirmed runtime の整合 | `runtime=powershell-5` なのに `.sh` を指定 |
| **C2** | fix-required | PowerShell 5 + 非 ASCII `.ps1` の BOM 有無 | 日本語コメント含む `.ps1` を BOM なし保存 (cp932 誤読で parse error) |
| **C3** | fix-required | PowerShell argv の完全明示 (invoker basename / runtime 整合 / required flag (case-insensitive) / host option は -File より前 / 重複 -ExecutionPolicy / -File 検出 / **-Command / -EncodedCommand と -File の排他** (両方あると script 実行されず silent exit 0) / -ExecutionPolicy Bypass 隣接 / -File ↔ --script path 整合 (絶対 path を含む場合は normalized full path、相対 path 同士は basename equality)) | `contract.command = ["script.ps1"]` (PowerShell invoker を経由しない) / `-ExecutionPolicy RemoteSigned ... Bypass` (隣接していない) / `-File script.ps1 -NoLogo` (host option が -File より後ろ) / `-ExecutionPolicy Bypass ... -ExecutionPolicy RemoteSigned` (重複) / `-Command "..." -File script.ps1` (排他違反、script が実行されない silent failure) |
| **C4** | fix-required | PowerShell `.ps1` で `[Console]::OutputEncoding = UTF8` 設定 (必須) | `$OutputEncoding` 単独 (child process 向け、必須を満たさない) / 設定なし (cp932 出力で qgb 文字化け) |
| **C5** | **advisory** | confirmed runtime executable がローカル PATH にあるか | `runtime=node` だが skill agent 環境に Node なし (利用者環境では存在する可能性あり、advisory note 出力のみ、exit code に影響しない) |
| **C6** | fix-required | qgb check stage log に `U+FFFD` (mojibake sentinel) | cp932 出力を qgb が utf-8 decode → 文字化け |

**C5 は advisory** (Codex K=2 r1 fix #4 確定): 検査は skill agent の local env で実行されるため、利用者の host とは異なる場合がある。advisory note として stderr に出力するが exit code 1 には**しない** (false negative を避ける)。

## 設計境界

- **skill 内部の lint** であり qgb 本体機能ではない (philosophy P9 + framework-shape §5「対象判定を qgb 本体へ戻さない」境界遵守)
- lint の役割は **proposal adopt 前の検査**、ALLOW 判定の根拠にはならない (philosophy P6)
- 検査結果は `knowledge.jsonl` に `entry_type: review_note` + `source_type: llm_advisory` で記録可能 (advisory として、basis にしない)

## 制限

- 検査は skill agent の local env (= 開発機 / CI runner) で実行、利用者環境とは異なる
- C5 (runtime PATH) は利用者環境では別途確認必要 (利用者プロジェクトの README / `project-context.md` で runtime install 手順を案内)
- C2 / C4 (PowerShell encoding) は最頻ケースのみ網羅、複雑な script は手動レビューも併用推奨

## 関連

- `skills/source/body.md` §6.5 command authoring protocol (本 lint が検証する protocol)
- `skills/source/body.md` §12.5.5 capability-based dispatch checklist (本 lint が参照する runtime checklist)
- `development/docs/journal/phase5-step5-a-2-4-prejournal.md` (本 Step の設計判断)
- `development/docs/journal/phase5-step5-a-2.md` §6.3 step 16 lint helper 同梱 (5.b 着手前提)
