# 段階設計プロンプト (qgb design-stages、パターン B / C)

> 本ファイルは Phase 5 qgb スキルの **オンデマンド読み込み正本**。
> body.md の trigger 表で「段階作って」「契約設計」「policy.json を作って」「stages を増やしたい」等の依頼に該当したときに読み込む。
>
> full モード: SKILL.md に embed される。
> split モード: 独立 helper として配置される。

## 1. 段階設計とは何か

qgb は **L1〜L6 のような固定階層を強制しない** (philosophy P10)。各プロジェクトは自分の対象系 (Web アプリ / CLI / バッチ / ドキュメント群 / プロンプト集 / 法務テンプレ等) に合わせて段階数 / 各段階の責務を設計する。

段階設計とは **「このプロジェクトで何を保証したいか」を機械的検査可能な単位に分解する作業**。設計後は `policy.json#stages[]` として固定され、`qgb run` がそれを順に実行する。

### 設計の柱

- **段階数の推奨レンジ**: 3〜7 (1〜2 は階層化の意味薄い、8 以上は単一責任原則破綻のサイン)
- **各段階に `responsibility` を明示** (一文、複数センテンスは単一責任違反の警告)
- **段階間は DAG** (循環禁止、線形は DAG の特殊ケース)
- **採用根拠は機械検査のみ** (P6 / P7)、LLM 主観評価で ALLOW を出さない
- **段階の選択は REQ メタの `stages[]`** (宣言外段階は判定対象外)

## 2. 設計プロセス: パターン B と パターン C の使い分け

qgb は段階設計の進め方として **2 つの公式パターン** を提供する。利用者の環境と作業スタイルに応じて選ぶ。

### パターン B (Phase 2 Step 2.5 で確立): external-LLM proposal/adopt 経路

**前提**: qgb 自身は LLM を一切呼ばない。LLM (= 本スキルを動かしている agent) が外部で段階設計を行い、proposal JSON として qgb に渡す。

**流れ**:

1. `python -m qgb design-stages propose-context [--out FILE]`
   - qgb が対象プロジェクトの自己定義 (`.quality-system/project-context.json` + `knowledge/project-context.md`)、設計例パック (`examples/`)、既存 `policy.json` / `knowledge.jsonl` をすべて JSON として書き出す
   - これは LLM への **入力素材** (context payload)
2. LLM (本スキル) がその context を読んで段階案を起草
   - `examples/` から近い 1〜3 例を参照 (few-shot)
   - 対象プロジェクトの `purpose` / `technologies` / `artifact_kinds` を踏まえる
   - 段階数 3〜7、各段階の responsibility を一文で書く
   - 段階間の DAG を決める
   - 各段階の `verification_type` (`command` / `file_exists` / `substring_match` / `json_schema` / `manual_check`) と `required_contract_fields` を決める
3. proposal JSON として書き出す (schema: `qgb/schemas/proposal.schema.json`)
4. `python -m qgb design-stages adopt <proposal.json>`
   - qgb が proposal を schema 検証 + 既存 `policy.json` / REQ メタとの整合検証
   - `human_reviewed: true` フィールドの存在を確認 (人間が承認したことの記録)
   - 検証通過なら `policy.json#stages[]` に焼き込み

**使うべき場面**:

- LLM が外部 LLM (= 本スキルを動かす agent) として動いている、つまり Phase 5 スキル経路の通常運用
- 人間が proposal を **承認するステップ** を明示的に挟みたい場合
- 設計判断の根拠を `proposal.basis[]` として記録に残したい場合 (audit trail として価値が高い)
- 複数案を比較検討してから 1 つを採用したい場合 (`propose-context` 経由なら別案を別 proposal として平行起草できる)

### パターン C (Phase 1 互換、自律実行): rule-based proposer

**前提**: qgb が rule-based に段階案を生成。`examples/generic-minimal` をデフォルトテンプレートとして提案、利用者が y/n/edit で確定。LLM 関与は最小。

**流れ**:

1. `python -m qgb design-stages [--commit] [--json]`
   - qgb が `examples/generic-minimal` の段階構造をテンプレートとして提案
   - `--commit` なしなら提案のみ、`--commit` で `policy.json` に焼き込み
   - `--json` で JSON 出力 (CI 用)

**使うべき場面**:

- 利用者が「とりあえず汎用最小段階で始めたい」「LLM 起草不要」と判断した場合
- CI 内で非対話的に段階を自動採用したい場合 (`--json` 出力を後続処理に流す)
- Phase 1〜2 で既に確立した運用との互換性を保ちたい場合

### B / C の選択判断 (Phase 5 スキル経路では B 推奨)

| 観点 | パターン B 推奨 | パターン C 推奨 |
|---|---|---|
| 設計判断の audit | 必要 (proposal.basis[]) | 不要 |
| 人間承認ステップ | 明示的に挟む | y/n で簡素 |
| 対象プロジェクト | 非自明 (ドキュメント群 / 法務テンプレ等) | 汎用 CLI / Web 等 |
| 初回設計 | B (LLM の理解を活かす) | C (テンプレ起点) |
| 段階の見直し | B (--revise 同型で B を再実行) | C (テンプレ差分で済む) |

**Phase 5 スキル経路では原則 B を推奨**。スキルを動かしている agent が LLM である以上、proposal/adopt 経路で audit trail を残すのが philosophy P6 (LLM 単独 ALLOW 禁止) との整合度が高い。

## 3. パターン B の詳細手順 (本スキル経路の中心)

### 3.1 propose-context の実行

```powershell
python -m qgb design-stages propose-context --out .quality-system/_proposal_input.json
```

出力には以下が含まれる:

- `project_context_json`: `.quality-system/project-context.json` の中身
- `project_context_md_excerpt`: `.quality-system/knowledge/project-context.md` の先頭部分 (LLM が全文を Read で読む前提)
- `examples_index`: `examples/` 配下の `<example>/design-notes.md` / `policy.json` の pointer リスト (LLM が必要な例を Read で読む)
- `existing_policy_json`: 既に `policy.json` があれば現状の `stages[]`
- `knowledge_jsonl_summary`: knowledge entry の件数と種別
- `philosophy_anchors`: P5 / P6 / P7 / P8 / P9 / P10 / P11 の id と一文サマリ

### 3.2 段階案の起草 (LLM 責務)

LLM (本スキル) は context を読んで段階案を JSON で起草する。最低限の構造:

```json
{
  "proposal_version": "1.0",
  "policy_id": "default",
  "stages": [
    {
      "id": "S1",
      "name": "コマンド成立",
      "responsibility": "CLI コマンドが終了コード 0 で完了する",
      "depends_on": [],
      "verification_type": "command",
      "required_contract_fields": ["command", "expected_exit_code"]
    },
    {
      "id": "S2",
      "name": "出力契約",
      "responsibility": "出力ファイルが JSON Schema を満たす",
      "depends_on": ["S1"],
      "verification_type": "json_schema",
      "required_contract_fields": ["target", "schema"]
    }
  ],
  "basis": [
    {"type": "example", "ref": "examples/python-cli-pytest/", "rationale": "Python CLI の典型段階構造として参照"},
    {"type": "philosophy", "ref": "P10", "rationale": "段階の可変性を尊重、対象に応じて 4 段階に絞った"},
    {"type": "project_context", "ref": ".quality-system/project-context.json#purpose", "rationale": "purpose = '入力検証 + 変換' から S1〜S4 を導出"}
  ],
  "human_reviewed": false,
  "notes": "S4 (異常系) を分離した理由: 不正入力の安全な拒否を別段階で保証 (P1 一要求一外部化)"
}
```

### 3.3 人間承認

LLM は `human_reviewed: false` のまま proposal を出す (P8 違反になるため自動 true 化禁止)。利用者が proposal を読んで承認したら `human_reviewed: true` に書き換える (手動編集 or 確認 UI 経由)。

### 3.4 adopt の実行

```powershell
python -m qgb design-stages adopt .quality-system/_proposal_input.json
```

qgb が以下を機械検証:

- proposal schema 検証
- `human_reviewed: true` の確認 (false なら error)
- DAG (循環なし)
- stage id 一意
- responsibility 非空
- verification_type が定義済み列挙値
- 既存 `policy.json` がある場合は変更差分を提示

検証通過なら `policy.json#stages[]` に書き込み。**書き込みは atomic swap** (途中状態が残らない、Phase 2 規律)。

### 3.5 整合性の機械検証

`policy.json` 更新後、必ず:

```powershell
python -m qgb validate-policy
```

を実行。Phase 1 必須検査項目 (stage id 重複なし / depends_on の DAG / responsibility 存在 / contract layout 等) が機械検査される。blocker があれば修正して再実行。

## 4. パターン C の詳細手順 (Phase 1 互換)

```powershell
# 提案のみ (policy.json は書かない)
python -m qgb design-stages

# 採用 (policy.json に焼き込み)
python -m qgb design-stages --commit

# CI 用 JSON 出力
python -m qgb design-stages --json
```

`examples/generic-minimal` の 2 段階構造 (S1: コマンド成立、S2: 出力契約) がデフォルトで提案される。利用者が y/n/edit から選ぶ。

**注意**: パターン C はテンプレ起点のため、対象プロジェクトの自己定義 (`project-context.{md,json}`) は反映されない。対象が generic-minimal から外れる場合はパターン B を選ぶ。

## 5. 設計時の典型的判断ポイント

### 5.1 段階数をどう決めるか

| 状況 | 推奨 |
|---|---|
| CLI で出力 1 種、異常系少 | 2-3 段階 |
| CLI + 出力 + 異常系 + 結合 | 4-5 段階 |
| Web API + schema + 結合 + 性能 + 異常系 | 5-7 段階 |
| ドキュメント群 (link 整合 + 用語統一 + 構造) | 3-4 段階 |
| プロンプト集 (構文 + 命名 + 重複) | 3 段階 |

8 段階以上を提案するときは「責務を細かく切りすぎていないか」を再点検 (P9 単一責任)。

### 5.2 verification_type の選択

| やりたいこと | type |
|---|---|
| コマンド実行して exit code 確認 | `command` |
| ファイル存在確認のみ | `file_exists` |
| ファイル内テキスト含有確認 | `substring_match` |
| JSON ファイルの schema 適合 | `json_schema` |
| 人間の目視確認 | `manual_check` (採用判定の根拠にできない、P6) |

`manual_check` を含む段階を `required: true` で参照する REQ は `qgb run` で NOT_READY エラー。LLM レビューや人間目視は採用根拠から分離するのが philosophy の核 (`prompts/review-policy.md` 参照)。

### 5.3 depends_on の決め方

- 「段階 B は段階 A の結果に依存するか」を 1 つずつ確認
- 線形依存 (S1 → S2 → S3) が典型、その特殊ケースとして「S2 と S3 は独立、S4 が両方依存」のような DAG もあり得る
- 循環は禁止 (`qgb validate-policy` で検出)

### 5.4 REQ メタでの stage 選択

各 REQ は `policy.json#stages[]` のサブセットを宣言する。

- 全 REQ が全段階を見る必要はない (P1 一要求一外部化)
- `required: true` の段階のいずれかが failed なら DENY
- 宣言外段階は判定対象外 (出現しない)

例: REQ-DOC-001 (ドキュメント REQ) は `command` 段階を含まず、`file_exists` + `substring_match` + `link_integrity` だけを宣言、等。

## 6. 設計後の見直しフロー (`--revise` 相当)

段階を増やしたい / 減らしたい / 名称を変えたいとき:

1. **段階追加**: パターン B で新 proposal を起こし adopt 経路で追加
   - 新段階を含む REQ から `stages[]` で参照
   - `qgb validate-policy` で DAG / 整合性確認
2. **段階削除**: REQ メタで該当 stage を参照している箇所をすべて削除してから `policy.json#stages[]` から削除
   - 参照が残っているまま削除すると `qgb validate-policy` で error
3. **段階の `id` 変更**: 既存 REQ メタの `stage_id` 参照が壊れるため、警告 + 連動更新
   - 推奨: id は固定、名称 (`name`) や責務 (`responsibility`) の修正で対応

## 7. アンチパターンと回避

### 7.1 `manual_check` で ALLOW を出そうとする

❌ `manual_check` を含む REQ で `qgb run` を強行 → NOT_READY エラー。

✅ `manual_check` は別 REQ に分離し、機械化された段階と別経路で扱う。または `human_attestation` 型 (Phase 2 以降) を待つ。

### 7.2 段階を細かく切りすぎる (8 段階以上)

❌ S1 (コマンド) / S2 (exit code) / S3 (stdout 存在) / S4 (stdout 形式) / S5 (... ) と細かく分けすぎ。

✅ 責務を 1 段階に統合 (「コマンド成立」段階で exit code + stdout 確認まで含める)。`qgb validate-policy` の警告を尊重。

### 7.3 `responsibility` を複数センテンスで書く

❌ `"responsibility": "CLI コマンドが exit code 0 で完了する。stdout に期待する文字列が含まれる。stderr に warning がない。"` → 単一責任違反、警告。

✅ 1 文に絞る (`"CLI コマンドが exit code 0 で完了する"`)、追加要件は別段階に。

### 7.4 LLM 主観評価で ALLOW を出す

❌ proposal の `basis[]` に「LLM レビュー結果は問題なし」と書いて ALLOW を主張。

✅ LLM レビューは **advisory のみ**、`prompts/review-policy.md` の規律に従う。ALLOW は機械検査の通過だけ。

### 7.5 `human_reviewed: true` を LLM が自動で立てる

❌ LLM (本スキル) が proposal 起草と同時に `human_reviewed: true` を立てる → P8 違反 (外部内容を上位指示として扱う)。

✅ LLM は `false` のまま出す、人間のみが `true` に書き換える。

## 8. 関連参照

- `philosophy.md` P5 / P6 / P7 / P8 / P9 / P10 / P11
- `stage-design.md` 段階設計フェーズ仕様 v1.0 (本スキルの上位仕様)
- `requirements_and_development.md` §6.4 (validation flow)
- `examples/generic-minimal/`, `examples/python-cli-pytest/`, `examples/markdown-docs/`, `examples/python-fastapi-pytest/`, `examples/go-cli/`, `examples/node-cli-vitest/` (設計例パック、few-shot 用)
- `prompts/review-policy.md` (LLM レビューの観点と境界、本ファイルと姉妹)
