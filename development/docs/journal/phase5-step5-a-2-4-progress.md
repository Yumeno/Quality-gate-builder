# Phase 5 Step 5.a-2-4 進行中ジャーナル (compact 跨ぎ用 v2)

作成日: 2026-07-02
位置: 実機 fixture 7/7 PASS (commit `b29ceef`) 後、Step 5.a-2-4 完結処理直前
目的: コンテキスト compact 後に作業を即再開するための受け渡し文書
モデル: 本 commit 時点で Opus 4.7 → **Fable 5 に切替済** (利用可能期間の制約による user 判断)

## 1. ここまでの作業状態 (Step 5.a-2-4 全体)

### 1.1 完結した commits (新しい順)

| commit | 内容 |
|---|---|
| `b29ceef` | **PS5.1 実機 fixture テスト追加 + 実機発見 lint bug 修正 (7/7 PASS)** |
| `8f79905` | K=2 r6 fix: runtime 別 allowlist + exec-mode 網羅 |
| `378fffb` | K=2 r5 fix: 排他判定位置限定 + 省略形検出 |
| `0976086` | K=2 r4 fix: -Command/-EncodedCommand と -File 排他 |
| `cef0d27` | K=2 r3 fix: 4 件 (post-File host option / 重複 / casing parity / README) |
| `a871d6b` | K=2 r2 fix: 5 件 (PS C5 parity / EP 隣接 / path layered / Win path / 番号) |
| `4899b48` | K=2 r1 fix: 5 件 (--script derive / C4 必須化 / C3 強化 / C5 advisory / lint 正本化) |
| `db34758` | 5.a-2-4 完結 journal 初版 (段階 7) |
| `9c57de8` / `2dd22cb` / `153a2b1` / `260e517` / `7aa9ad4` / `07de0c7` | 段階 6/5/4/3/2/1 |

### 1.2 K=2 収束系列と実機検証による決着

- Codex 机上 K=2: r1: 5 → r2: 5 → r3: 4 → r4: 1 → r5: 2 → r6: 2 (未達のまま)
- **user 判断で方針転換**: 「テストフォルダを作って実際に動かしてテストする」
- `tests/fixtures/lint_command_contract/` 新設 (contracts A1-A4 OK 系 + B1-B3 NG 系 + run-tests.ps1)
- **実機 PS 5.1.26100 で 7/7 PASS**、机上 6 ラウンドで見つからなかった lint bug 複数を発見・修正:
  - derive 経由 path 比較 false positive → `script_explicitly_provided` flag
  - 略形が required_flags を通らない → `required_flag_synonyms` 同義語 group
  - EP 重複/隣接検査の略形対応 → `ep_aliases`
  - test runner 側の PS5 罠 (null array / ErrorRecord 化 / stdout+stderr 混合)
- **「運用上問題ない」基準を実機ベースで担保完了**、Step 5.a-2-4 は完結判定可能な状態

### 1.3 Step 5.a 全体 (別系統) は K=2 達成済

commit `ebee96f` (Codex r6 で新規必須 fix 0 件判定)。5.b 着手条件 = Step 5.a 全体 K=2 (達成済) + Step 5.a-2-4 完結 (実機検証で担保、完結処理待ち)。

## 2. 未完タスク (compact 後の即時アクション)

### 2.1 【最優先・保留中】Fable 5 による repo レビュー

user 依頼 (Fable 5 切替直後): 「本リポジトリの目的や理念、そこから照らしての要件・設計や実装の状況について、レビューをもらえるとうれしい」

- philosophy.md 全文 (11 不易 P1-P11、3 群構成) は精読済
- **レビュー本文は未提出** — compact 後に最初に届けるべき成果物
- レビュー観点案: (a) 理念の内的整合性、(b) 要件/設計の理念準拠、(c) 実装状況 (Phase 1-3 完結 + Phase 5 進行中) の乖離有無、(d) 開発プロセス自体 (K=2 / Codex 多段 / journal 文化) のメタ評価、(e) リスク・懸念

### 2.2 Step 5.a-2-4 完結処理 (レビュー後)

1. 5.a-2-4 完結 journal (`phase5-step5-a-2-4.md`) §3 commit chronology に `b29ceef` (実機 fixture) 行を追記
2. §1 確立した境界に「実機 fixture 検証による運用基準担保」を追加 (机上 K=2 未達のまま実機で決着した経緯と判断根拠を明記)
3. auto-memory 更新: 実機 fixture 検証パターン (机上レビュー限界の教訓)、PS5 test runner の罠 (null array / ErrorRecord / stdout 分離)
4. Step 5.a-2-4 完結 commit + push
5. Step 5.b 着手前提の整理 (5.a-2 完結 journal §6.3 の 16 項目 + lint 同梱 + fixture 流用)

### 2.3 その後: Step 5.b (build_skill.py 実装)

- A1' 単一正本 (body.md) → converter → dist/skills/{full,split}/{claude,codex}/
- build_input_digest 8 カテゴリ / deterministic build / golden fixture
- lint script (`skills/source/lint/`) の dist 同梱 + digest カテゴリ 5
- `tests/fixtures/lint_command_contract/` は 5.b の golden/regression に流用可能

## 3. 環境ノート (compact 後の注意)

- モデル: Fable 5 (Opus 4.7 から切替済)
- pytest が Bash/PowerShell 両方で background 化して無応答になる事象が断続的に発生 (memory `pytest-bash-bg-pattern` 参照、PC 再起動後は解消傾向)
- PowerShell tool で `Set-Location` すると Bash 側の cwd に影響する場合あり → 各 tool 呼び出し後に cwd 確認
- git commit は `&&` 連結で exit 254 になる事象が 1 回発生 → add / commit / push を個別呼び出し (memory `bash-permission-patterns` 準拠)

## 4. 関連ファイル (compact 後すぐ参照)

- 本書 (最初に Read)
- `development/docs/journal/phase5-step5-a-2-4.md` (完結 journal、§3 更新対象)
- `development/docs/journal/phase5-step5-a-2.md` (5.a-2 完結 journal、§6.3 = 5.b 前提 16 項目)
- `development/docs/philosophy.md` (11 不易、レビューの基準文書)
- `tests/fixtures/lint_command_contract/run-tests.ps1` (実機検証 runner、7/7 PASS 確認済)
- `skills/source/lint/check-command-contract.{py,ps1}` (実機検証済 lint)
- auto-memory: `phase5-a1-prime-structure` / `codex-review-multi-round` / `windows-bom-encoding-rules` / `pytest-bash-bg-pattern` / `additive-first-delete-last`
