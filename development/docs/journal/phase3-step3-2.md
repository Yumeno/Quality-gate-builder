# Phase 3 Step 3.2 完結ジャーナル: 依存解決固定 (lock + hash)

完結日: 2026-06-26
着手前判断: `phase3-step3-2-prejournal.md` (v1 commit `5212c0d` / v2 Codex r1 反映 + artifact 撤回 `2a3632d`)

## Step 3.2 で確立した境界 (恒久記録)

### 機械責務として担保したもの

- `requirements.lock` (149 行 / runtime 依存 + 推移依存) と `requirements-dev.lock` (298 行 / dev 依存、`--constraint=requirements.lock` で layered + `--allow-unsafe` で pip/setuptools/wheel 含む) を **Windows × Python 3.10 で生成し repo commit**
- CI 4 matrix (Windows + Ubuntu × Python 3.10 + 3.12) で `pip install --require-hashes --only-binary :all: -r requirements-dev.lock` 通過 = sdist 任意コード実行面を構造的に閉じる + wheel 経路に固定
- `pip install --no-deps --no-build-isolation -e .` = PEP 517 build isolation 経由の hash bypass を閉じる (dev lock で install 済の setuptools / wheel を build 段階でも reuse)
- `lock-integrity` job (Windows × Python 3.10、1 job のみ) で committed lock を seed に pip-compile 再実行 → `tools/diff_locks.py` で header strip + 改行正規化 body 比較。「lock が pyproject.toml の依存範囲を満たすか」を機械検証 (= 「PyPI 新 release との diff」「脆弱性」は別問題)
- `tests/test_lock_integrity.py` 11 件で lock 静的構造検証 (hash 行 / 集合一致 / layered constraint / 同 version / 禁止 marker 不在 / 将来 inline env marker 退行防止)
- `.gitattributes` で `requirements*.lock` を LF 固定 + `tools/diff_locks.py` 改行正規化の二重防御
- `SECURITY.md` に **Dependency Lock Policy** + **Trust-Layer Boundary** + **Environment Used to Generate the Lock** + **How to Update** + **What This Policy Does NOT Manage** を新設

### qgb 本体 CI 責務範囲外として整理したもの

- **lock の artifact 化** (90 日 / 1 年 / 永続のどれが必要かは利用者ごとに違う、git 環境外運用も想定)
- **SBOM (CycloneDX/SPDX) 生成** (lock + hash で qgb 本体 immediate risk を直接閉じる、SBOM は利用者の inventory / vulnerability workflow 用)
- **vulnerability scan (pip-audit / safety)** (外部 advisory DB を qgb の closed loop に持ち込まない)
- **Dependabot / Renovate 自動更新** (人手 review loop を path に固定、qgb 哲学 P8 + 編集は構造化 JSON Patch 経由と整合)
- **JUnit XML / PR コメント連動** (利用者運用、Phase 4 廃止時に整理済)
- **PyPI install 経路の再現性** (qgb 本体 CI は contributor / CI / repo 環境の再現性のみ、`pip install qgb` from PyPI は range 解決のまま、Phase 5 配布判断は別途)

参考設計例は `development/docs/ci-examples.md` (5 patterns: 長期 lock 保管 / SBOM / vuln scan / JUnit / Dependabot)。本格的な利用者プロジェクト向け CI テンプレは Phase 5 Skill Creator が生成する。

### 信頼層境界 (`SECURITY.md` Trust-Layer Boundary)

| 層 | 制御方法 |
|---|---|
| GitHub Actions runners | `actions/checkout` + `actions/setup-python` SHA pin (Step 3.1 で確立) |
| `pip` / `setuptools` / `wheel` | dev lock 経由で hash 固定 + `--no-build-isolation` で build invocation も使う |
| PEP 517 build backend | `pyproject.toml [build-system].requires` (範囲、metadata) + `--no-build-isolation` で実体は dev lock の hash 固定版 |
| Python interpreter | `actions/setup-python` 解決 (patch level pin なし) |
| PyPI artefact hashes | lock が固定 (primary 制御点) |

### lock 生成環境の規約

- **Windows × Python 3.10** で生成 (`SECURITY.md` "Environment Used to Generate the Lock")
- 理由 1 (Python marker superset): matrix 最小 Python = 3.10 で生成すれば `typing-extensions` / `exceptiongroup` / `tomli` 等 Python 3.10〜3.11 限定 transitive が全部 lock に入る
- 理由 2 (OS marker superset): Windows で生成すれば `colorama` 等 `platform_system == "Windows"` / `sys_platform == "win32"` 限定 transitive が lock に入る (Linux 生成だと colorama 不在で Windows runner の `--require-hashes` install が失敗)
- 不要 transitive は install 時に env marker で skip されるので superset でも実害なし

## Step 3.2 のサブステップ構成

prejournal v2 でサブステップ 3.2a〜3.2f に分割 (v1 の 5 個 + ci-examples.md で 6 個に拡大)。

| サブステップ | commit | 内容 |
|---|---|---|
| 3.2a | `df90b1c` | `pyproject.toml` dev extras に `pip-tools>=7.4,<8.0` + `tomli; python_version < '3.11'` 追加 |
| 3.2b | `fcabf82` | `requirements.lock` + layered `requirements-dev.lock` 初回生成 + commit |
| 3.2c | `a45e0b9` | CI に `--require-hashes --only-binary :all:` install + `lock-integrity` job 追加 |
| 3.2d | `2b56fda` | `SECURITY.md` に "Dependency Lock Policy" + "Trust-Layer Boundary" 節新設 |
| 3.2e | `3570894` | `tests/test_lock_integrity.py` 10 件新設 |
| 3.2f | `520dbd9` | `development/docs/ci-examples.md` 新設 (5 patterns、利用者運用参考) |

## CI 補修 chain (5 連、Step 3.1 補修 7 件と同型の "ローカル PASS でも CI 投げないと検出されない" 群)

| # | commit | 失敗原因 | 修正 |
|---|---|---|---|
| 1 | `73d90a8` | yaml で `:all:` が mapping 値と誤読 (`Missing expression after '...':all:'`) | `run:` 値を double-quoted scalar に変更 |
| 2 | `9b41e56` | Python 3.13 で生成した lock に 3.10/3.12 用 `typing-extensions` 不在 | Python 3.10 で lock 再生成 + `lock-integrity` job も 3.10 に揃える + SECURITY.md に "Python Version Used to Generate the Lock" 節 |
| 3 | `938f60c` | PyPI 新 release (click 8.4.1→8.4.2、ruff 0.15.18→0.15.19) で diff、tmp/ path で header diff | committed lock を seed として copy してから regen + `tools/diff_locks.py` で header strip + 改行正規化 body 比較 |
| 4 | `dbbd657` | Ubuntu runner で `colorama` (Windows-only env marker) 不在 | `lock-integrity` job を Windows runner に移行 + SECURITY.md "Environment Used to Generate the Lock" を OS 規律含めて更新 |
| 5 | `598e3af` | Windows runner default shell PowerShell で bash 構文 `\` line continuation が parser error | 該当 step に `shell: bash` 明示 (Git Bash 経由) |

CI 6 回目 (`598e3af`) で初の全 5 jobs success。各補修は本質的に「環境固有問題」で qgb のコア設計 (lock + hash) を揺るがすものではない。**Step 3.1 教訓「small だから省略は禁じ手」が本 Step でも証明された** (ローカル Python 3.13 + Windows で PASS でも CI 4 matrix + lock-integrity で初めて壊れる問題が 5 つ)。

## 段 1〜5 のレビュープロセス (Codex セカンドオピニオン 3 周経由で K=2 収束)

| 段 | 周 | 内容 | finding |
|---|---|---|---|
| 0 | r1 | prejournal v1 計画レビュー | 7 件指摘 (5 採用、2 自動消滅) → prejournal v2 + artifact 化撤回判断 |
| 1 | — | 観点別 5 並列レビュー (correctness / P9 / philosophy / NF-004 / spec-drift) | 40 件 (P0 0 / P1 5 / P2 35)、段 2 で Claude 集約 |
| 3 | r1 | 横断レビュー (補修 M1-M3 後の集約結果) | 新規 P2 2 件 (M1' SECURITY.md How to Update 漏れ / M3' inline env marker test) → 補修 M1' / M3' |
| 5 | r2 | K=2 第 1 周 (M1' / M3' 補修後) | 新規 finding なし → 第 1 周カウント |
| 5 | r3 | K=2 第 2 周 (= 達成判定、second look) | 新規 finding なし → **K=2 達成、Step 3.2 完結確定** |

## 補修群 (段 1〜5 で発生、5 件)

「ステート不在化」の Step 3.1 と異なり、本 Step は「**境界の明文化と漏れの拾い直し**」が主軸:

| 補修 | commit | 解消した finding | 設計 |
|---|---|---|---|
| M1 | `63d7569` | 段 1 correctness F-correctness-1 (P1) build isolation 経由 hash bypass | `--no-build-isolation` 追加 + SECURITY.md Trust-Layer Boundary 表に dev lock 経由 setuptools/wheel 固定を明記 |
| M2 | `32777ae` | 段 1 NF-004 F-nf004-2 (P1) `.gitattributes` 不在で改行コード変換次第で偽陽性 diff | `.gitattributes` で `requirements*.lock` を LF 固定 + `tools/diff_locks.py` で改行正規化 (二重防御) |
| M3 | `7f5410f` | 段 1 correctness F-correctness-3 (P1) 将来 inline env marker pin の正規表現非対応 | `_PIN_LINE` に `(?:\s*;[^\\]*?)?` を追加し env marker をオプション吸収 |
| M1' | `0cb7220` | 段 3 横断 r1 (P2 spec fix) SECURITY.md How to Update Step 3 smoke test 手順の `--no-build-isolation` 漏れ | smoke test コマンドを `--no-build-isolation` 付きに統一 |
| M3' | `11bcbf0` | 段 3 横断 r1 (P2 code fix) M3 regex 拡張の意図を退行防止する fixture テスト不在 | synthetic fake.lock fixture で inline marker pin の parse 退行防止 test 追加 |

## 作業プロセス記録 (timeline)

| 時刻 (相対) | 出来事 |
|---|---|
| 段 0 r1 | prejournal v1 commit (`5212c0d`)、Codex r1 で 7 件指摘 + 「pip install qgb 再現可能」言い過ぎ指摘 + SBOM 整理 |
| **user 介入 1** | 「artifact 化は qgb 本体 CI 責務外、利用者運用 (git 環境外利用も想定)」→ artifact 化撤回 + `ci-examples.md` 新設方針確定 |
| 段 0 r1 反映 | prejournal v2 commit (`2a3632d`)、artifact 化撤回 + Codex finding 7 件反映 |
| 3.2a〜3.2f | 6 サブステップ commit、ローカル 752 passed |
| 3.2c 補修 | CI 1 回目 push (`73d90a8`)、yaml `:all:` 問題で全 jobs fail → quote 修正 |
| CI 2 補修 | CI 2 回目 push (`9b41e56`)、Python 3.13 lock で 3.10/3.12 install 失敗 → Python 3.10 で lock 再生成 + lock-integrity job も 3.10 |
| CI 3 補修 | CI 3 回目 push (`938f60c`)、PyPI 新 release で diff fail → seed 付き regen + `diff_locks.py` で header strip |
| CI 4 補修 | CI 4 回目 push (`dbbd657`)、Ubuntu runner で colorama 不在 → lock-integrity job を Windows に移行 |
| CI 5 補修 | CI 5 回目 push (`598e3af`)、Windows runner PowerShell で bash 構文 fail → `shell: bash` 明示 |
| CI 6 回目 | 全 5 jobs success 初達成 |
| 段 1 | 5 並列レビュー 40 件、段 2 で Claude 集約 (P0 0 件、P1 5 件、P2 35 件) |
| 補修 M1-M3 | P1 3 件本体補修 (build isolation / 改行 / regex) → CI 7 回目緑 |
| 段 3 r1 | Codex 横断、新規 P2 2 件 (M1' / M3') |
| 補修 M1' / M3' | r1 P2 を本周中に補修 → CI 8 回目緑 |
| 段 5 r2 | K=2 第 1 周判定: 新規 finding なし → カウント開始 |
| 段 5 r3 | K=2 第 2 周判定: 新規 finding なし → **K=2 達成、Step 3.2 完結確定** |
| Task 46 | spec 更新 (detailed-design / requirements / CLAUDE / README / security-dependency-policy) + 完結 journal + memory |

## ユーザー判断の重要転換点

### 転換点 1: 「artifact 化は qgb 本体 CI 責務外」(prejournal v2 のライン引き再点検)

prejournal v1 では `lock-integrity` job の lock を GitHub Actions artifact として 90 日保管する案を含めていた。user 介入で:

- 「qgb は git 環境外でも使う可能性がある」
- 「CI で artifact 保管するかは利用者運用の話 (社内コンプライアンス / SOC2 / 監査要件で必要期間が異なる)」
- 「qgb 本体 CI = 配布物としての qgb 機械品質保証のみ」

= Step 3.1 で JUnit XML を WONTFIX 整理したのと同型のライン引き。**qgb 本体 CI 責務範囲外として明示** + 利用者向け参考例は `ci-examples.md` (Pattern A〜E、5 種類) に切り出す方針へ転換。

これは Phase 5 Skill Creator が利用者プロジェクトに CI テンプレを生成するときの **責務分離の few-shot 教材** にもなる。

### 転換点 2: 「lock 生成は Windows × Python 3.10 固定」(CI 補修 chain 経由で判明)

CI 補修 2-4 連を通じて、pip-compile の resolve は「(OS, Python version) ペア」固有であることが実証された:

- CI 補修 2: Python 3.13 生成 lock → 3.10 install で `typing-extensions` 不在で fail → Python 3.10 で生成すれば 3.10〜3.13 用 superset
- CI 補修 4: Ubuntu 生成 lock → Windows install で `colorama` 不在で fail → Windows で生成すれば両 OS の superset

これは prejournal v2 §不確実性 4「OS / Python version 別 lock の要否」の答えが **「単一 lock OK、ただし生成環境は最小 Python + Windows 固定」** だったと現場で確定する経緯。SECURITY.md に「Environment Used to Generate the Lock」節を新設して固定。

### 転換点 3: 「build isolation 経由の hash bypass を閉じる」(段 1 correctness F-correctness-1)

`--no-deps -e .` は PEP 517 build isolation が default で有効。pip が build venv を作って `setuptools` / `wheel` を **PyPI から fresh fetch** する経路があり、これは `--require-hashes` 保護外。sdist 任意コード実行面を `--only-binary :all:` で閉じた直後にこの穴があると Step 3.2 主旨が部分的に空転。

修正は `--no-build-isolation` 追加 + SECURITY.md Trust-Layer Boundary 表で「dev lock 経由 setuptools/wheel hash 固定 + `--no-build-isolation` で build invocation も使う」と二段表現。これにより `--require-hashes` + `--only-binary :all:` + `--no-build-isolation` + dev lock の **4 層防御** が完成。

### 転換点 4: 「lock-integrity が答える設問の限定明文化」(SECURITY.md)

CI 補修 3 で「seed 付き regen + header strip body 比較」設計に着地した際、user との対話で **`lock-integrity` job が答える設問を限定** することが重要と判明:

- 答える: 「committed lock は現 pyproject.toml の依存範囲と整合か」(= 「pyproject 変えたのに lock 忘れた」検出)
- 答えない: 「PyPI 新 release が出ていないか」「lock に脆弱性があるか」「lock install が全環境で成功するか」(後者は test job の install 経路で別検証)

これは philosophy P5 (ALLOW の意味限定) を CI job レベルに適用したもの。「lock-integrity job 緑 = qgb 品質緑」と CI バッジが誤読されないよう SECURITY.md "Dependency Lock Policy" で明文化。

## Phase 5 への申し送り (技術と方法論を分離、Step 3.1 同型)

### supply-chain 技術 (依存解決固定の few-shot)

- **lock + hash 4 層防御**: `--require-hashes` (artifact bytes 固定) + `--only-binary :all:` (sdist 任意コード実行排除) + `--no-build-isolation` (build path も hash 経路に閉じる) + dev lock 経由 build backend 固定 (setuptools/wheel まで cover)
- **layered lock**: dev lock は runtime lock を `--constraint=` で制約することで「dev install が runtime pin を上書き」が原理的に起きない (P9 単一責任の supply-chain 版)
- **lock 生成環境の固定**: pip-compile 解決は (OS, Python version) ペア固有、CI matrix の最小 Python + Windows (matrix が含む全 env marker の superset を確保) で生成
- **整合性検証の責務限定**: lock-integrity job は「lock と pyproject.toml の整合性」のみ。「PyPI 新 release との diff」「脆弱性 scan」は別問題として分離 (philosophy P5 適用)
- **build isolation 経由の bypass**: editable install で `--no-build-isolation` を渡さないと、`build-system.requires` の package が hash 保護外で再 fetch される。sdist 排除と並ぶ重要な閉じる点
- **整合性検証の seed 戦略**: pip-compile が「PyPI 最新を取りに行く」default 動作を抑止するため、committed lock を tmp/ に copy してから regen させる (PR レビューが「pyproject 変更検出」だけになる)
- **改行正規化の二重防御**: `.gitattributes` (repo 内表現) + tool 側 normalize (実行時) の二重防御で OS / git config 差を吸収

### review 方法論 (Codex セカンドオピニオン消化の few-shot、Step 3.1 同型)

- **finding の 3 分類** (Step 3.1 で確立): `code fix` / `spec fix` / `out of scope by philosophy`
- **段 1 観点別並列 → 段 2 集約 → 段 3 横断 → 段 5 K=2** プロセスを「小規模 Step だから省略」せず実施。本 Step は規模 0.9〜1.5 だが補修 5 連 + 横断追加 2 件で「small だから省略は禁じ手」が再証明された
- **prejournal は書き換えず、完結 journal で「予期しきれなかった転換点」を記録**: Step 3.1 で確立したパターン。本 Step も prejournal v2 (artifact 化撤回後) と最終実装の 3 つの差分 (install step 数 / 整合性検証 job の OS-Python / `git diff` → `diff_locks.py`) を完結 journal で記録
- **doc cohesion の残務 = K=2 リセット要因でない**: Codex r2 で「README の Step 3.2 status と dev install 手順、workflow 冒頭コメントの古い lock-integrity 説明だけは Task 46 で掃除推奨」と整理、K=2 第 1 周成立を阻害しない判断
- **CI 補修 chain の記録価値**: 5 連の補修内容自体が「pip-compile 関連の落とし穴 catalogue」として価値が高い (yaml `:all:` / Python version 別 marker / OS 別 marker / PowerShell 互換 / shell 経由) → Phase 5 で利用者プロジェクト向け CI テンプレ生成時の参考

### 利用者運用との境界 (philosophy P11 適用)

- **qgb 本体 CI ≠ 利用者プロジェクト CI**: qgb 本体は配布物の機械的品質保証、利用者は対象プロジェクトに応じた運用 (artifact retention / SBOM / vuln scan / Dependabot / JUnit XML 等を選択)
- **lock 文化の強制は Phase 5 で別判断**: qgb 本体は repo / CI / contributor 環境の再現性を保証、`pip install qgb` from PyPI は別経路 (range 解決のまま)。利用者プロジェクトに qgb と同じ lock 規律を要求するかは Phase 5 Skill Creator が利用者の package manager / コンプライアンス要件と相談して判断
- **参考設計は `ci-examples.md` 5 patterns**: 強制でなく選択肢として提示、各 Pattern に「Why qgb does not do this」を明記して責務範囲外であることを明示

## 規模実績の振り返り

- prejournal v1 見積もり: 0.6〜1.0
- prejournal v2 上方修正: 0.9〜1.5 (Codex r1 finding 反映 + ci-examples.md 追加分)
- 実績: **約 1.6** (サブステップ 6 個 + CI 補修 5 連 + 段 1 補修 3 件 + 横断補修 2 件 + Task 46 文書反映)
- 上振れ理由: CI 補修 chain 5 連 (環境固有問題の積み重ね) + 段 1 で出た P1 3 件 (build isolation / 改行 / regex) の本体補修
- ただし「上振れ」は **supply-chain 4 層防御の知見** + **CI 補修 5 連の落とし穴 catalogue** を得た投資であり、Phase 5 提供時の信頼性と few-shot 教材価値で十分回収できる判断

## Phase 3 全体完結

Step 3.0 (2026-06-22) / Step 3.1 (2026-06-24) / Step 3.2 (2026-06-26) の 3 ステップで「機械責務側の最終整備」が完結。Phase 5 (Skill Creator 化) 着手前提条件 = (a) 対象認識のライン引き、(b) command 実行の機械的信頼性、(c) 依存解決の機械的信頼性 がすべて揃った状態。

Step 3.3 (Phase 2 繰越実需回収、任意) は Phase 5 で実需が判明したものに限定する原則を維持 (先回りで全部やらない)。

## 次の Step 申し送り

- **Phase 5 (Skill Creator 化)**: skills/source/ の中間表現整備 + tools/build_skill.py の実装 + 3 エージェント (Claude Code / Codex CLI / Gemini CLI) 向けスキル成果物の生成 + 利用者プロジェクト向け CI テンプレ生成
- **Step 3.3 (任意繰越)**: Phase 5 着手中に実需が判明したものから (Phase 5 が advance しないと判断不能)

## 関連ファイル

- `phase3-step3-2-prejournal.md` (着手前判断、v1 + v2 Codex 反映 + artifact 撤回)
- `requirements.lock` / `requirements-dev.lock` (本 Step で確立した実装、Windows × Python 3.10 生成)
- `tests/test_lock_integrity.py` (11 件、本 Step で確立した静的検証)
- `tools/diff_locks.py` (本 Step で確立した header strip + 改行正規化 body 比較 script)
- `.gitattributes` (本 Step で確立した lock 改行 LF 固定)
- `.github/workflows/test.yml` (本 Step で `lock-integrity` job 拡張)
- `SECURITY.md` "Dependency Lock Policy" / "Trust-Layer Boundary" / "Environment Used to Generate the Lock" / "How to Update" (本 Step で新設・拡張)
- `development/docs/ci-examples.md` (本 Step で新設、利用者運用 5 patterns 参考)
- `development/docs/detailed-design.md` §14.2 + §15 改訂履歴 0.29 (Step 3.2 完結記録)
- `development/docs/requirements_and_development.md` §13 / §14 (Phase 3 全体完結反映)
- `development/docs/security-dependency-policy.md` §8 / §9 (Phase 3 後の整理 cleanup)
- `CLAUDE.md` (Architectural invariants / Project status / repo 構造)
- `README.md` (Status / Documentation / 再現可能 install 手順)

memory に `lock-hash-domain-scope` 新規候補 (Step 3.1 の `subprocess-runner-domain-scope` と同型、qgb 本体 lock 文化と利用者運用の境界記録)。
