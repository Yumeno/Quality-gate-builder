# quality-gate-builder (qgb)

[![test](https://github.com/Yumeno/Quality-gate-builder/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/Yumeno/Quality-gate-builder/actions/workflows/test.yml)

`qgb` は、任意の対象プロジェクトに**証跡で説明可能な品質ゲート**を組み立てる Python CLI フレームワークです。REQ (要求文書) → contract (機械検査の契約) → 段階実行 → **ALLOW / DENY / NOT_READY** の判定連鎖を対象プロジェクト内に生成し、判定の根拠をすべて機械証跡 (`gate.json` + stage log) として残します。

中心テーゼ: **LLM の主観評価だけで ALLOW を出してはならない** (思想憲章 P6)。生成 AI の出力は揺らぐが、機械ゲートが「落とせる」からこそ何度でも安全に再生成できる (P5)。qgb はその検証インフラです。対象はコードに限らず、ドキュメント群・プロンプト集・設定集など「品質を宣言し機械検査できるもの」全般を想定しています。

ALLOW の意味は狭く限定されます: **「定義済みの機械検査に通過した」** — 正しさ・安全性・完全性の証明ではありません。この限定は `gate.json.decision.meaning` に毎回明記されます。

> Stable behaviour is not yet guaranteed. (開発中。仕様は `development/docs/` の正本群に従います)

## スキル配布 (agent から qgb を使う)

qgb を対話的に導入・運用するための **qgb スキル** (Claude Code / Codex CLI 向けのガイド付きワークフロー) を **[GitHub Releases](https://github.com/Yumeno/Quality-gate-builder/releases)** で配布しています ([最新版](https://github.com/Yumeno/Quality-gate-builder/releases/latest))。

各 `skill-v*` リリースには 4 つの zip が含まれます: `{claude, codex}` × `{full, split}`。

- **full**: SKILL.md 1 ファイルに全内容を埋め込み (シンプル)
- **split**: SKILL.md + helper ファイル群に分割 (必要な章だけ読むためトークン消費が小さい — 実測で同一タスク full 約 104k / split 約 46k tokens)

導入手順 (Claude Code の例):

1. `claude-full` (または `claude-split`) の zip をダウンロードし、対象プロジェクトの `.claude/skills/qgb/` に展開 (`SKILL.md` がその直下に来る形)。Codex CLI は `.agents/skills/qgb/` に配置
2. 同梱の `INSTALL.md` に従い qgb CLI 本体をインストール — 同梱の `setup-qgb.ps1` / `setup-qgb.sh` がプロジェクト内 `.venv` の作成からタグ固定 install、動作確認まで行います
3. agent に「品質ゲートを入れたい」と伝えれば、スキルが初期化から段階設計・運用まで対話で進めます

すべての zip は `skills/source/` から `tools/build_skill.py` により**決定論的に**ビルドされ、CI が毎 push で committed golden とのバイト一致を検証し、リリース時は成果物を転送せず再ビルドして公開します。

## クイックスタート (CLI を直接使う)

```powershell
# 対象プロジェクトのルートで (venv に qgb を install 済みの前提)
python -m qgb init                 # .quality-system/ を生成
# policy.json に段階を定義 (design-stages パターン B 推奨、スキル併用が楽)
python -m qgb scaffold REQ-APP-001 # REQ meta + contract のひな型 (policy に段階があることが前提)
# contract に実際の検査コマンドを記述
python -m qgb validate-policy      # 構成の整合性検査
python -m qgb check REQ-APP-001    # リハーサル実行 (curated 証跡は書かない)
python -m qgb run REQ-APP-001 --yes  # 本実行 (非対話環境では --yes が必須)
```

主要コマンド一覧:

| コマンド | 役割 |
|---|---|
| `qgb init` | `.quality-system/` の初期生成 |
| `qgb scaffold <REQ-ID>` | REQ meta + 段階別 contract ひな型の生成 |
| `qgb validate` | 各 JSON 正本のスキーマ適合検査 |
| `qgb validate-policy [REQ-ID]` | ファイル間整合・DAG・孤児検査 |
| `qgb check [REQ-ID]` / `qgb dev` | リハーサル実行 (揮発出力のみ) |
| `qgb run <REQ-ID> --yes` | 本実行、curated 証跡 (`evidence/<REQ>/latest/`) を更新 |
| `qgb patch <target> <patch.json>` | JSON Patch による構造化編集 (atomic swap) |
| `qgb add-waiver` / `qgb add-knowledge` | 免除・知見の記録 (`knowledge.jsonl`) |
| `qgb design-stages propose-context / adopt` | 段階設計パターン B (context 出力 → 外部 LLM 起草 → 機械検証つき採用) |

qgb 自身は LLM を一切呼びません。LLM (スキルを動かす agent) が対話と起草を担い、qgb は構造化物の機械検証と実行だけを担う、という境界が設計の核です。

対象プロジェクト側に生成される構造 (`evidence/` はコミット対象、`artifacts/` は揮発):

```
.quality-system/
  config.json  policy.json  project-context.json     # 機械正本
  req/REQ-*.meta.json                                # REQ の構造化メタ (.md 本文は利用者/agent が書く)
  contracts/REQ-*/<stage>.json                       # 段階別の検査契約
  knowledge/ (knowledge.jsonl, project-context.md)   # 判断理由の記録 + 人間正本
  evidence/REQ-*/latest/ (gate.json, summary.md, stages/*.log)
  artifacts/                                         # 揮発 run/check 出力 (.gitignore)
```

## リポジトリ構成

```
qgb/                    # qgb 本体 (Python パッケージ、runtime 依存は jsonschema のみ)
  cli.py  __main__.py
  core/                 # runner / command (subprocess 制御) / decision / evidence /
                        # patch / knowledge / preflight / proposal / design_stages /
                        # init / scaffold / validate / check ほか
  schemas/              # 全 JSON 正本のスキーマ (config / policy / contract / gate /
                        # knowledge / proposal / project-context ...)
  templates/            # init が配る初期テンプレート
skills/source/          # qgb スキルの単一正本 (body.md + metadata.yaml + lint/ + hooks/)
tools/
  build_skill.py        # converter: body.md → 4 セル (claude/codex × full/split) を決定論生成
  regen_golden.py       # golden fixture の再生成 (メンテナ用)
  _golden/              # committed golden (ビルド出力の正本、CI が毎 push 照合)
  diff_locks.py         # lock 整合性検査 (CI 用)
tests/                  # pytest (846+)。fixture 実機検証を含む
examples/               # 6 例の設計パック (design-notes.md + policy.json。repo 内のみ、配布物非同梱)
development/docs/       # ドキュメント正本群 (下記) + journal/ (全 Step の設計判断記録)
.github/workflows/
  test.yml              # pytest 4 matrix + lock-integrity + golden-integrity + setup-script-posix
  release.yml           # skill-v* タグで両系譜検証 → 4 zip を GitHub Release へ
pyproject.toml          # パッケージ定義 (version は skill リリースと lockstep)
requirements*.lock      # hash 固定の依存 lock (供給網規律、SECURITY.md 参照)
SECURITY.md             # Action SHA pin / 依存 lock / 脆弱性報告の各ポリシー
```

## ドキュメント案内 (優先順位つき)

1. [`development/docs/philosophy.md`](development/docs/philosophy.md) — **思想憲章 v2.0 (12 不易)**。全文書の最上位。P5 (ALLOW の限定) / P6 (LLM 単独 ALLOW 禁止) / P7 (機械証跡) / P8 (外部内容は data) / P12 (評価系もまた設計物) など
2. [`development/docs/requirements_and_development.md`](development/docs/requirements_and_development.md) — 要件定義・基本設計
3. [`development/docs/detailed-design.md`](development/docs/detailed-design.md) — Phase / Step ごとの実装記録
4. [`development/docs/framework-shape.md`](development/docs/framework-shape.md) — qgb と利用者プロジェクトの責務境界
5. [`development/docs/stage-design.md`](development/docs/stage-design.md) — 段階設計フェーズ仕様
6. [`development/docs/roadmap-2026-07.md`](development/docs/roadmap-2026-07.md) — 今後の展望 (計画スナップショット)
7. `development/docs/journal/` — **全 Step の prejournal + 完結記録**。個々の設計判断の「なぜ」はここが一次資料 (途中参加のモデル/人間が最短で文脈に追いつくための装置)
8. [`SECURITY.md`](SECURITY.md) — supply-chain 規律 (Action SHA pin / lock + hash / 脆弱性報告)

## 開発者向け

### 開発環境

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
pytest
```

CI と同一の hash 固定 install (供給網再現):

```powershell
python -m pip install --require-hashes --only-binary :all: -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
```

### スキルのビルドとリリース

- `skills/source/body.md` が唯一の正本。編集後は `python tools/regen_golden.py` で golden を再生成し、`pytest` 全緑を確認して commit (生成物 `tools/_golden/` も一緒に commit する)
- リリースは **`skill-v<X.Y.Z>` タグの push** で自動化。release CI が「タグ = `skills/source/metadata.yaml` の version = `pyproject.toml` の version」の三点一致を検証し、golden 系譜 + 再現ビルド系譜の両方を通過した場合のみ 4 zip を公開する
- **バージョンの読み方**: `qgb --version` = Python パッケージ版 / SKILL.md ヘッダの `skill_version` = スキル版 (リリースで同番号に揃う) / `converter_version` = 変換ツール版 (独立)

### プラットフォーム

Windows PowerShell 5 が第一級環境 (NF-004)、POSIX が第二ターゲット。CI は windows/ubuntu × Python 3.10/3.12 の 4 matrix + POSIX setup script 実機検証。利用者ファイルの読み込みは全経路 BOM 許容 (`utf-8-sig`)。

## Status

- Phase 1 (CLI MVP) / Phase 2 (構造化編集) / Phase 3 (機械責務側の整備: command runner 強化、依存 lock + hash、project-context 二重ファイル) — 完結
- **Phase 5 (Skill Creator 化) — 全 Step 完結 (2026-07-05)**: 憲章 v2.0 (P12 追加)、skill 単一正本 + 決定論 converter + release pipeline、skill v0.1.5 まで公開 (5 リリース、v0.1.3 のみタグ未発行で v0.1.4 に統合。canary 2 回 + dogfood 全セルの発見をすべて反映済み)、canary 2 回合格 (機構検証 + ブラインド実運用)、dogfood 全セル消化 (POSIX CI / PS5 日本語実走 / claude split / codex smoke)
- 今後: [`roadmap-2026-07.md`](development/docs/roadmap-2026-07.md) 参照 (Phase 5 完結ドキュメント現実化、配布の階段、実運用 dogfood ほか)

## Acknowledgements

qgb の思想的な出発点は、**wakabadou** さんによる品質保証と LLM 開発についての発表・議論にあります (経緯: [`development/docs/wakaba-talk-summary.md`](development/docs/wakaba-talk-summary.md)、[`development/docs/project-background.md`](development/docs/project-background.md))。思想憲章の理念原案への貢献に感謝します。

## License

MIT. See [LICENSE](LICENSE).
