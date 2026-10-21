# qgb Phase 1 導入マニュアル

Phase 1 の qgb (quality-gate-builder) を Windows PowerShell および
POSIX シェル環境で導入・実行するためのガイド。spec
`requirements_and_development.md` §8.1 で定義された 19 章の必須章立て
に従う。

## 1. 概要

qgb は、対象プロジェクトに「機械的に再現可能な品質ゲート」を生成する
メタツール。Phase 1 MVP は **Python 製 CLI** + **JSON 正本** +
**Markdown ドキュメント** で構成され、Phase 5 以降にエージェント中立
スキルへ拡張する計画 (F-019)。

判定値:

- `ALLOW` — 定義済み必須段階を通過 (思想 P5 / P11 のもと条件付き採用可)
- `DENY` — 必須段階に失敗 (失敗ではなく再生成への signal)
- `NOT_READY` — 構成不備で run 自体を実行できない (gate.json は出ない)

LLM レビューだけで ALLOW は出さない (philosophy P6 / C-001)。

## 2. 前提環境

- **Python 3.10 以上**。3.11+ で内部 `tomllib` パスが効く (3.10 は
  正規表現フォールバックが動作)。
- **Git** (リポジトリ取得用)。
- **OS**: Windows 10/11 (PowerShell 第一級サポート、NF-004) / Linux / macOS。
- 外部依存は `jsonschema` のみ (NF-010 / NF-011 / §6.6)。

仮想環境の利用を強く推奨。`.venv` を切らない場合、依存が他プロジェクト
に漏れる可能性がある。

## 3. Python の確認

Windows:

```powershell
py -3 --version
```

POSIX:

```bash
python3 --version
```

3.10 未満なら Python 公式インストーラまたはディストリ側パッケージから
3.10+ を導入する。

## 4. リポジトリ取得

```powershell
git clone https://github.com/Yumeno/Quality-gate-builder.git
cd Quality-gate-builder
```

リリース版が出れば `git checkout <tag>` で固定する。Phase 1 はまだ
PyPI 配布をしない (§6.6.3)。

## 5. 仮想環境作成

Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

POSIX:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

> **NF-004 注:** venv を activate すると、その shell の `python` は venv 内の
> `python.exe` (Windows) または `python` (POSIX) を指す。本マニュアル以降の
> `python -m ...` 例は activate 済みを前提とする。Windows で venv を使わない
> (システム Python 直接) 構成では `python` が PATH に無いケースがある
> (Microsoft Store install など)。その場合は §19 トラブルシューティング
> および `examples/python-cli-pytest/README.md` の "Windows note" を参照。

## 6. 依存関係導入

```powershell
python -m pip install -U pip
python -m pip install -e .
```

editable インストールにすることで、qgb 開発・修正中の動作を即時反映
できる。

## 7. qgb の実行確認

```powershell
python -m qgb --help
python -m qgb --version
```

各サブコマンドのヘルプ:

```powershell
python -m qgb run --help
python -m qgb scaffold --help
```

### 7.1 spec §8.2 PowerShell 例 (full flow リファレンス)

要件§8.2 で固定されている代表的な PowerShell コマンド列。venv 作成
〜採用判定までを一気に行う形:

```powershell
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m qgb --help
python -m qgb init
# Phase 3 Step 3.0 (2026-06-21) で qgb detect は廃止。
# init が生成した .quality-system/project-context.{md,json} を
# 編集して対象プロジェクトの自己定義を書く (md は人間が、json は
# 補佐 Agent が、人間がレビューして human_reviewed: true に変える)。
python -m qgb design-stages
python -m qgb design-stages --commit
python -m qgb scaffold REQ-APP-001
python -m qgb validate-policy
python -m qgb run REQ-APP-001
```

各コマンドの意味と注意点は §3〜§11 を参照。実際に走らせる際は各
コマンドの確認プロンプトや出力を確認しつつ進める。`qgb run` は
`--yes` を付けないと確認プロンプトが出る (§F-008)。

> Phase 2 で追加された日次検証 (`qgb check` / `dev`)、Pattern B
> (`qgb design-stages propose-context` + `adopt`)、構造化編集
> (`qgb patch` / `add-waiver` / `add-knowledge`) は本マニュアル
> Phase 1 範囲外。`requirements_and_development.md` §6.2.1 を参照。

## 8. 対象プロジェクトでの初期化

対象プロジェクト直下に移動して:

```powershell
python -m qgb init
```

生成されるもの (詳細は detailed-design.md §6 参照):

```text
.quality-system/
  config.json
  policy.json            (stages: [])
  knowledge/
    knowledge.jsonl      (空)
    project-context.md
  artifacts/             (.gitignore 対象)
  evidence/              (.gitignore 対象)
.gitignore (.quality-system/artifacts/, .quality-system/evidence/ を追記)
```

`.quality-system/artifacts/` と `.quality-system/evidence/` は run の
生成物なので `.gitignore` 対象。`evidence-reference/` (例えば examples
の手書きリファレンス) は別経路で残す (§6.2 / examples/generic-minimal/
の運用を参照)。

## 9. 段階設計フェーズの実行

提案フェーズ (policy.json は書き換えない):

```powershell
python -m qgb design-stages
```

採用フェーズ (policy.json#stages を atomic に書き換え、内部で
validate-policy を通す):

```powershell
python -m qgb design-stages --commit
```

Phase 1 では template = `examples/generic-minimal` のみ。Python CLI
や Markdown ドキュメントの対象でも、現状はこの 1 つから出発する
(stage-design.md §10.1)。

## 10. サンプル REQ 生成

```powershell
python -m qgb scaffold REQ-APP-001
```

生成されるもの:

- `.quality-system/req/REQ-APP-001.meta.json`
- `.quality-system/contracts/REQ-APP-001/{S1,S2,...}.json` (schema-valid placeholder)
- `tests/quality/L1_behavior/` と `tests/quality/L5_contract/` (.gitkeep のみ)

contract は schema を通る placeholder。`qgb run` を直後に走らせると
`DENY` (target が実在しない placeholder のため)。利用者は contract の
target / command 等を実プロジェクトに合わせて編集する。

## 11. quality-gate 実行 (run)

```powershell
python -m qgb run REQ-APP-001
```

確認プロンプトが出る (F-008)。CI などで自動化するときは `--yes`:

```powershell
python -m qgb run REQ-APP-001 --yes
```

TDD phase=red を期待値として証跡化する場合:

```powershell
python -m qgb run REQ-APP-001 --yes --phase red
```

JSON 出力:

```powershell
python -m qgb run REQ-APP-001 --yes --json
```

## 12. gate.json の読み方

`./.quality-system/evidence/REQ-APP-001/latest/gate.json` を確認する:

- `status` — `ALLOW` / `DENY` (NOT_READY は gate.json を生成しない)
- `failed_stage` — DENY のとき最初に失敗した stage の id (all-waived
  DENY のときは空文字列)
- `decision.result` — `ALLOW` / `DENY`
- `decision.meaning` — F-016 表通り (phase ごとに verbatim 文言)
- `decision.scope` — project-local 性 (P11) を明記
- `stages[]` — 各 stage の result / exit_code / log_ref など
- `basis[]` — REQ id / POLICY-id / CONTRACT-* / KNOWLEDGE-WAIVER-* な
  どの根拠リスト

`stages[].synthetic` が `true` なら runner integrity 起因の欠落
(通常 failure と区別される、Step 6+7 統合レビュー RA1)。

## 13. summary.md の読み方

`./.quality-system/evidence/REQ-APP-001/latest/summary.md` は gate.json
を Markdown で要約。判定結果 / 実行情報 / 段階別結果 / basis / 注意
(P5, P11) を 1 画面で読める形。CI のサマリ表示や、人間 reviewer への
通知に使う想定。

## 14. NOT_READY になった場合の対応

NOT_READY は「設計が壊れている」状態。代表的な原因と対処:

- `manual_check_required` — `verification_type=manual_check` を `required:
  true` の stage で使っている (受け入れ条件 15)。当該 stage を分解する
  か、`waived: true` + `waiver_reason` を付けて知識ベースに記録する
- `missing_contract` / `misplaced_contract` — contract ファイルが見つから
  ない、または canonical layout 外に置かれている。`qgb validate-policy`
  でも検出される
- `verification_type_mismatch` — policy 側と contract 側で
  verification_type が異なる
- `schema_violation` — JSON 正本のいずれかが schema を満たしていない。
  `qgb validate` で具体的な path / message を確認

修正したら `qgb validate` → `qgb validate-policy` → `qgb run` の順で
通す。

## 15. DENY になった場合の対応

DENY は「再生成への signal」(philosophy P5)。代表的な原因:

- 必須 stage の実行が失敗 (例: pytest が落ちた、target file が無い)
- 期待された contract が満たされない (substring が見つからない、
  expected_exit_code と不一致)

`stages[].log_ref` の log を見て原因を特定する。対象コードまたは
contract を修正して再 run。phase=red で DENY が出ているなら、それは
TDD red ステップとして期待される状態 (`decision.meaning` が "expected
failure" となる)。

## 16. 免除（waived）の指定方法

REQ meta の `stages[]` 該当 entry に追記:

```json
{
  "stage_id": "S3",
  "contract_ref": ".quality-system/contracts/REQ-APP-001/S3.json",
  "required": true,
  "waived": true,
  "waiver_reason": "Internal CLI tool; no UI to verify"
}
```

`qgb run` 実行時に `knowledge.jsonl` に `kind: waiver` のエントリが
idempotent に追記される (受け入れ条件 16、Step 7)。

注意: Phase 1 では **waived 段階の contract / target を変更しても
再評価しない**。要件§F-007 の "判定対象から除外" 通り。詳細は spec
§F-007 の "Phase 1 における waiver の audit semantics" を参照。

waiver を取り消すときは REQ meta の `waived` を `false` (または削除) に
して、対応する knowledge.jsonl の `waiver` エントリも手で削除し、
`qgb run` を再実行する。

## 17. TDD phase の使い方

`--phase` フラグで TDD サイクル上の局面を gate.json に記録する:

| phase | 用途 |
|---|---|
| `red` | テスト追加直後、実装前。DENY が期待される状態 |
| `green` | 実装完了後、テストが通る確認 |
| `refactor` | refactor 後、テストが通り続ける確認 |
| `verify` | TDD サイクル外の通常採用判定 (既定値) |

```powershell
python -m qgb run REQ-APP-001 --yes --phase red
python -m qgb run REQ-APP-001 --yes --phase green
python -m qgb run REQ-APP-001 --yes --phase refactor
```

CLI 終了コードは status と一致 (`ALLOW`=0, `DENY`=1)。phase=red でも
DENY なら exit 1 を返すので、CI 側で `phase=red` と組み合わせて
expected failure を判定する。

## 18. 依存ライブラリ確認手順

新しい依存ライブラリを採用する際は、`development/docs/security-dependency-policy.md`
の checklist に従う。Phase 1 で使用している依存は **`jsonschema` のみ**。
追加候補があれば:

1. 配布元・メンテナンス状況・ライセンス・既知脆弱性を調査
2. 依存ツリーの大きさ・postinstall hook の有無を確認
3. ネットワーク通信・バイナリ配布の有無を確認
4. 採用判断と確認内容を `knowledge.jsonl` に `kind: repository_fact`
   または `kind: external_reference` で記録 (external_reference の場合は
   `requires_human_review: true` 必須、受け入れ条件 18)

## 19. トラブルシューティング

| 症状 | 原因の見当 | 対処 |
|---|---|---|
| `qgb run` が NOT_READY を返す | preflight が design issue を検出 | `qgb validate-policy <REQ>` で具体的な kind / where を確認 |
| `qgb validate` が schema_violation | knowledge.jsonl に `source_type: external` 行があるが `requires_human_review: true` がない | 当該行に `requires_human_review: true` を追記 (受け入れ条件 18) |
| `command` stage で "command not found" | Windows で `python` が PATH にない (Microsoft Store 経由 install) | contract をローカルで `["py", "-3", ...]` に書き換える (commit しない)。詳細は `examples/python-cli-pytest/README.md` の Windows note を参照 |
| Windows で `npx` / `npm` 等の `command` stage が "command not found" (stage log に `hint:` 行) | `npx` 等は Windows では `.cmd` shim。qgb は shell を介さず argv をそのまま起動し、PATHEXT 解決をしない (Issue #35) | `node <CLI エントリ>` を直接指定する (例: `["node", "node_modules/vitest/vitest.mjs", "run"]`)。Windows 専用 contract なら `npx.cmd` のように拡張子を明示 |
| gate.json の `paths.run_dir` に backslash が混じる | Phase 1 では POSIX forward slash 固定。混じったらバグ | issue で報告 |
| `qgb design-stages --commit` で validate-policy エラー | tmp tree での validation が failed | エラー詳細を確認、policy.json / config.json を修正 |
| `examples/python-cli-pytest` が DENY を返す | demo_cli が editable install されていない / pytest が無い | `pip install -e ".[test]"` を当該例ディレクトリで実行 |
| `qgb validate` で knowledge.jsonl の 1 行目が "invalid JSON" として弾かれる | エディタが UTF-8 BOM を追加した | knowledge.jsonl を **BOM 付きでない UTF-8** で保存し直す (Windows のメモ帳は BOM を付けがち。VS Code / nvim 等で再保存) |

その他の症状や設計に関する質問は GitHub Issues で報告。philosophy /
spec / detailed-design の 3 文書も合わせて参照すると、Phase 1 の判断軸が
理解しやすくなる。
