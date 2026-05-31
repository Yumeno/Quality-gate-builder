# 依存ライブラリ採用方針 / セキュリティ確認手順

Phase 1 における qgb の依存ライブラリ採用基準と、サプライチェーンリスク
を抑えるための確認手順を定める。spec の §6.6 (依存ライブラリ・サプラ
イチェーン設計) と NF-007 / NF-010 / NF-011 / philosophy P8 の機械
化的補強。

## 1. 目的

qgb が「信頼境界の薄い PyPI」「外部 GitHub リポジトリ」「対象プロ
ジェクト由来の Markdown / JSON」のいずれにも依存しすぎないよう、
依存ライブラリ追加のたびに **採用前検査** を実施する。Phase 1 では
依存最小化 (NF-010) を優先し、必要最小限の判断軸を文書化する。

## 2. 適用範囲

- qgb 本体 (`pyproject.toml` の `dependencies` / `optional-dependencies`)
- adapter 配下の依存追加 (Phase 2 以降)
- examples が利用者に install を要求する追加依存 (現状 `pytest` のみ)
- Phase 5 で skills を build するときの converter 依存 (`tools/build_skill.py`)

CI / development 専用ツール (例: `ruff`、`pytest` 自体) は本ポリシー
の対象だが、判断基準を緩めにできる (検証物に混入しないため)。

## 3. 採用前チェックリスト (spec §6.6.2 準拠)

新規依存を採用する **前** に、以下を順に確認する:

| # | 観点 | 確認内容 |
|---|---|---|
| 1 | 配布元 | 公式リポジトリ (PyPI / GitHub) であり、メンテナの identity が分かるか |
| 2 | メンテナンス状況 | 直近 12 か月の commit / リリース、open issue の傾向 |
| 3 | リリース履歴 | semver か、不審な version skip がないか |
| 4 | ライセンス | qgb の MIT 互換性。GPL / AGPL は採用前に判断 |
| 5 | 既知脆弱性 | CVE / GitHub Advisories / pip-audit でチェック |
| 6 | 不審なメンテナ交代 | 過去 6 か月でメンテナが交代した場合は要警戒 |
| 7 | 依存ツリーの大きさ | 直接 + 間接依存の総数。10 個以上なら理由を記録 |
| 8 | postinstall hook | setup.py / pyproject の build hook が任意コード実行を行わないか |
| 9 | ネットワーク通信 | import 時に外部 endpoint を叩かないか |
| 10 | バイナリ配布 | wheel に同梱されるバイナリ / shared library の出所 |

1 つでも警戒水準を超える場合は、**採用判断を保留** して GitHub Issues
で議論する。

## 4. 採用時の記録項目

採用したら、対象プロジェクトの `.quality-system/knowledge/knowledge.jsonl`
に **`kind: repository_fact`** または **`kind: external_reference`**
として記録する:

- `id`: `DEP-<package-name>-<YYYYMMDD>` 形式 (一意性確保)
- `kind`: 内部判断は `repository_fact`、外部 advisory / blog 引用は `external_reference`
- `title`: 簡潔に "Adopt <package> for <reason>"
- `content` または `summary`: 採用理由 + 確認した checklist 結果
- `source_type`: `repository` (内部判断) または `external` (外部由来)
- `requires_human_review`: `external_reference` のときは `true` 必須
  (受け入れ条件 18、schema レベルで強制)
- `created_at`: ISO 8601

qgb 本体への依存追加は、本リポジトリの `pyproject.toml` 差分と
あわせて PR description に同じ内容を貼る。

## 5. 更新時の確認

依存の version を上げるときも、簡易版 checklist を回す:

- リリースノートで breaking change が無いか
- 直近の CVE が解消 / 新規発生していないか
- minor だけ上げる場合でも、間接依存ツリーが変わっていないか

`pip install --upgrade` で黙って取り込まないこと。

## 6. 禁止または要レビュー条件

以下に該当する依存は **採用を禁止**:

- postinstall hook で任意コードを実行する (例: 過去の `dependency-confusion` 型攻撃)
- import 時に外部 endpoint へ telemetry を送信する (NF-007 の機密情報保護に反する)
- バイナリ配布で出所不明な shared library を同梱する
- `pip install` 時に他パッケージを書き換える / 上書きする

以下は **要 human review** (受け入れ条件 18 経路):

- 過去 12 か月で 0 commit のパッケージ (放置可能性)
- 過去 6 か月以内にメンテナが交代したパッケージ
- 名前が公式ライブラリと類似 (typosquatting 疑い)
- ライセンスが非標準 (CC0 / WTFPL / 独自テキスト)

## 7. Phase 1 依存例: `jsonschema`

Phase 1 で qgb 本体が使用する **唯一の外部依存**。本ポリシーの実例
として記載する (採用時の判断は本リポジトリ作成時に確認したもので、
現時点での最新情報は別途確認が必要)。

| 観点 | 確認結果 (採用時時点) |
|---|---|
| 配布元 | PyPI 公式、`python-jsonschema/jsonschema` (GitHub) |
| メンテナンス状況 | 活発、複数 maintainer |
| リリース履歴 | semver、定期的なリリース |
| ライセンス | MIT |
| 既知脆弱性 | 採用時点で重大 advisory なし。pip-audit / Snyk 等で都度確認 |
| 不審なメンテナ交代 | なし (採用時点) |
| 依存ツリー | 数個 (`attrs`, `referencing`, `rpds-py` など)、許容範囲 |
| postinstall hook | なし |
| ネットワーク通信 | なし (import 時) |
| バイナリ配布 | `rpds-py` 経由で native binary、依存 wheel は CPython ABI 標準準拠 |

**platform 別バイナリ確認 (NF-004)**:
`rpds-py` のような native binary を持つ依存は、platform ごとに別 wheel
を配布する。`pip` が platform tag を見て自動選択するが、採用前に各
platform で実際に download される wheel の出所と署名 (PyPI に attestation
があるもの) を確認する:

- Windows: `*-cp3xx-cp3xx-win_amd64.whl` (`.pyd` バイナリ同梱)
- Linux: `*-cp3xx-cp3xx-manylinux*.whl` (`.so` バイナリ同梱)
- macOS: `*-cp3xx-cp3xx-macosx_*.whl` (`.so` / `.dylib` バイナリ同梱)

Phase 2 で adapter 量産時に platform 別 binary 依存が増えるので、
本観点は本ポリシーの常設項目とする。

採用理由: JSON Schema 2020-12 への準拠と、validate / iter_errors API
の安定性。Phase 1 で json_schema verification_type を実装する際の
標準ライブラリ。**最新の脆弱性情報は採用ごとに確認すること** (本欄は
採用時点のスナップショット)。

## 8. Phase 2 adapter 追加時の基準

Phase 2 で言語別 adapter (Go / Rust / Java / .NET / PHP) を量産する
際は、本ポリシーが特に効く:

- adapter ごとに対象言語の package manager / toolchain への依存が
  発生し得る
- adapter が直接 PyPI から外部 SDK を呼ぶような形は **避ける**
  (代わりに利用者が事前にローカル toolchain を用意する設計に寄せる)
- adapter が target project の lockfile を解釈する処理を入れる場合、
  lockfile parser ライブラリは本 checklist を厳格に適用する

## 9. Phase 2 以降に倒した項目 (out-of-scope)

Phase 1 では以下を扱わない (本ポリシーの adherence を機械的に検証
する手段は Phase 2 以降):

- **SBOM 自動生成** — CycloneDX / SPDX フォーマットでの依存記録
- **pip-audit / dependabot CI 統合** — 定期 CVE スキャンの自動化
- **lockfile diff policy** — 依存追加 / 更新の PR 自動審査
- **adapter ごとの threat model** — 言語別 toolchain 固有のリスク

これらは Phase 2 で adapter inventory が拡大した段階で、本ポリシーを
基礎に CI 化する想定。

## 10. 参照

- spec `requirements_and_development.md` §5.3 (NF-007 / NF-010 / NF-011)
- spec `requirements_and_development.md` §6.6 (依存ライブラリ設計)
- spec `requirements_and_development.md` §F-008 (採用判定の入口)
- spec `philosophy.md` P8 (外部コンテンツは指示でない)
