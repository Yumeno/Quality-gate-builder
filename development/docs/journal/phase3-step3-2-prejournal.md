# Phase 3 Step 3.2 着手前判断: 依存解決固定 (lock + hash)

着手前判断確定: 2026-06-24
位置: Phase 3 残り 1 ステップ (Step 3.0 / 3.1 完結後)、Phase 5 着手前提条件の最後

## 経緯

Phase 3 Step 3.0 (`46d892a`, 2026-06-22) で detect 廃止 + project-context 二重ファイル設計、Step 3.1 (`564092b`, 2026-06-24) で command runner 強化 + CI 雛形 + 補修 7 件が完結。残るは **依存解決の固定** だけで、これが終われば Phase 5 (Skill Creator 化) 着手前提条件 (機械責務側の最終整備) が揃う。

1. ✅ Step 3.0: 対象認識のライン引き (LLM / 機械 / 補佐 Agent 三層)
2. ✅ Step 3.1: command 実行の機械的信頼性 (process tree kill / per-stream cap / .bat escape / CI matrix)
3. **Step 3.2 (本書)**: 依存解決固定 (lock + hash、supply-chain 信頼)
4. (任意) Step 3.3: Phase 2 繰越実需回収

仕様の出典は `development/docs/detailed-design.md` §14.2 Step 3.2、`development/docs/requirements_and_development.md` §13 Phase 3 サブステップ、§14 Phase 4 廃止に伴う「依存 audit / SBOM」の吸収方針。

## 本 Step の理念的位置づけ

Step 3.0 / 3.1 で確立した 2 つのライン引き教訓を本 Step に適用する:

- **機械責務 vs LLM 責務の混同を避ける** (Step 3.0 教訓): 「依存ライブラリの選定 / 監査」は LLM (人 + Phase 5 スキル) が判断、「再現可能な hash 固定」は qgb / CI が機械的に強制
- **症状対処より入らない設計** (Step 3.1 教訓): 「壊れたらアラート」でなく「壊れた依存解決が CI を緑にできない構造」を作る

### 1. なぜ依存解決を固定するのか (P7 / NF-010 / NF-011 の補完)

Phase 5 で Skill Creator が利用者に qgb を配布するとき、「ユーザーが pip install qgb した結果が再現可能」が supply-chain 信頼の前提になる。現状の `pyproject.toml` は:

```toml
dependencies = [
    "jsonschema>=4.20,<5.0",
]
```

しか宣言していない。これは:

- jsonschema には複数の推移依存 (attrs / jsonschema-specifications / referencing / rpds-py) があり、それぞれが mutable な version range で解決される
- 「Claude が論証で『qgb 0.1.0 を pip install すれば動く』と言う」は LLM 評価で、P6 違反の構造 (Step 3.1 で CI 機械化したのと同じ理屈)
- jsonschema 自体が malicious 化されなくても、推移依存のどこか 1 つが乗っ取られれば pip install qgb 経由で侵入できる (NF-011 想定脅威)

つまり Step 3.2 は **「qgb 自身の依存解決を機械的に固定し、CI でその固定値が再現可能であることを毎回検証する」装置** を入れる。これは Step 3.1 で「Windows ローカルで通った ≠ POSIX で通る」を CI 緑で機械判定したのと完全に同型。

### 2. なぜ SBOM ではなく lock + hash を採用するのか (2026-06-13 Codex セカンドオピニオン経由)

繰越判定パート (`journal/phase2-step2-7.md`) で SBOM を一度 WONTFIX としたが、Codex セカンドオピニオン後に撤回した経緯:

- **pip freeze だけでは不十分**: 推移依存の version は固定できても hash は固定できない、同 version でも yanked / republish された artifact を引かされる余地が残る
- **SBOM (CycloneDX / SPDX) はやり過ぎ**: 利用者プロジェクト向け配布物の monitoring 用途。qgb 本体は package 1 個 + 推移依存数個、SBOM のために new tool を増やすと NF-010 (依存最小化) と緊張
- **着地点 = pip-compile --generate-hashes + requirements lock**: pip 公式 + stdlib に近い経路で hash 固定、CI で再現性検証、Phase 5 提供時の supply-chain 文書として lock を添付

### 3. なぜ uv / poetry / pdm でなく pip-tools なのか

候補: pip-tools (pip-compile) / uv / poetry / pdm / pip freeze + hashin 等。

pip-tools 採用判断の根拠:

- **pip と同じ resolver を使う**: lock の生成と利用環境の install が同じ機構なので「lock は通ったが install で別解決された」が原理的に起きにくい
- **NF-010 (依存最小化)**: pip-tools 自体は CI / 開発時のみ依存、runtime には入らない。`pyproject.toml [project.optional-dependencies] dev` に追加 (Step 3.1 で pytest / ruff を入れたのと同じ枠)
- **NF-011 (サプライチェーン)**: pip-tools は PyPA (公式) 配下、long-running maintenance、actions/setup-python と同じ信頼層
- **uv 不採用理由**: 新興 (2024 登場)、Rust 製で qgb の「stdlib + pip」前提から大きく外れる。Phase 5 で利用者プロジェクトに uv を要求するかは別判断。qgb 本体は保守的に pip-tools。
- **poetry / pdm 不採用理由**: build backend 自体を置き換える、pyproject.toml が poetry / pdm 専用 schema になる。setuptools + pyproject.toml の現構成を維持したい (Phase 1 から不変、回帰リスク最小)

### 4. なぜ CI で artifact 化するのか (P7 + Step 3.1 の延長)

Step 3.1 で確立した「qgb の P6 を qgb 自身に適用 = CI 緑 = 機械的判定」の延長:

- CI が `pip-compile --generate-hashes` を実行 → 結果を **artifact として保管** → 後から「あのコミット時点で qgb が要求した依存解決は何だったか」が再現可能 (P7)
- もし悪意ある PR が pyproject.toml の `jsonschema>=4.20,<5.0` を `jsonschema>=999` 等に書き換えて推移依存を増やそうとすると、lock の diff が PR review で目に見える (Dependabot/Renovate なし方針と整合、人間 review loop の path に固定)
- artifact は GitHub の retention 期間 (default 90 日) を超えると消えるが、それは qgb の責務範囲外 (利用者が長期保管したいなら lock ファイルを repo にコミットする運用、本 Step ではコミット運用も併用、後述)

## Step 3.2 スコープ確定

### A. lock ファイルの生成と運用

#### A.1 `requirements.lock` を repo に commit

- `pip-compile --generate-hashes --output-file=requirements.lock pyproject.toml` 相当を CI で生成
- **lock ファイルは repo にコミット** する (rationale: Step 3.1 で SHA pin を repo に置いたのと同型、git log で diff を人間が見られる状態を維持)
- file 名は `requirements.lock` (pip-tools 慣習)。`.txt` 拡張子も慣習にあるが、`.lock` の方が「人間が直接編集すべきでない」シグナルが強い
- 内容: runtime 依存 (`jsonschema` + 推移依存) の hash 付き固定。dev 依存 (pytest, ruff) は別 lock (`requirements-dev.lock`) として分離

#### A.2 dev 依存の分離 (`requirements-dev.lock`)

- `pip-compile --generate-hashes --extra=dev --output-file=requirements-dev.lock pyproject.toml`
- 分離理由: 利用者の install (pip install qgb) には dev 依存は不要、別 lock にしておけば「runtime supply-chain」と「開発環境 supply-chain」の audit を分けて議論できる (P9 単一責任)

#### A.3 lock の運用契約 (人手更新、Dependabot/Renovate 不使用と整合)

- lock 更新は人手 + commit メッセージで理由明示 (Step 3.1 SHA pin と同じ運用契約)
- 更新トリガ: pyproject.toml の依存範囲変更 / 推移依存の security advisory / 定期 (四半期、Step 3.1 と同じスケジュール) / ad-hoc (理由明示)
- 「Completely ad-hoc with no documented reason」は不可 (Step 3.1 と同じ規律)
- 詳細は SECURITY.md に「Dependency Lock Policy」節を追加

### B. CI 統合

#### B.1 lock との一致検証 job

CI matrix に **追加 job ではなく既存 job のステップ追加** で実装する案を本命とする (理由: matrix を増やすと job 数が 4 → 6 etc に膨らみ、Step 3.1 で確立した「最小 CI」が崩れる)。

具体的には、既存の 4 jobs それぞれで:

1. `pip install -r requirements.lock --require-hashes` で qgb の runtime 依存を hash 検証込みで install
2. `pip install -e . --no-deps` で qgb 本体だけを editable install (依存は lock 経由で確定済)
3. dev 依存は `pip install -r requirements-dev.lock --require-hashes`
4. (この時点で pyproject.toml の dependencies と lock がずれていれば、`--require-hashes` か `--no-deps` のどちらかが落ちる)

検討: 別途 `pip-compile --check` で lock と pyproject.toml の整合性も verify するか?

- 案 A: `pip-compile --check` を CI に追加 (lock が古いと CI が落ちる)
- 案 B: 検証なし、人手運用に任せる
- 暫定方針: **案 A 採用** (机上では微小コスト、Step 3.1 教訓「機械化できるものは機械化」と整合)。ただし `--check` の CI への露出形は本体実装段階で再検討 (新規 step を増やすか、既存 install step に折り込むか)

#### B.2 lock を artifact として保管

- 既存 4 jobs のうち 1 つ (例: ubuntu-latest + Python 3.12) で lock を artifact upload
- retention は GitHub default の 90 日で足る (永続保管したければ tag / release に紐付け、その判断は Phase 5 配布時に再検討)

#### B.3 CI ファイル variant の境界

- Step 3.1 の CI は **pytest only**、本 Step では同じファイル `test.yml` に install ステップを差し込む形で完結させる
- 別 workflow (例 `lock.yml`) を新設しない (NF-010 minimum surface、Step 3.1 で確立した「workflow 1 個」を維持)

### C. SECURITY.md 拡張

#### C.1 「Dependency Lock Policy」節を新設

- runtime lock / dev lock の分離理由
- 更新トリガ 5 種 (Step 3.1 SHA pin policy と並列形式で記述、運用負荷の二重化を避ける)
- 更新手順 (pip-compile 実行 + 単一目的 commit)
- ad-hoc bump の commit メッセージ規約
- Dependabot/Renovate 不採用理由 (Step 3.1 と同じ理由、参照で済ませる)

#### C.2 SBOM 撤回履歴の整理

- 「SBOM (CycloneDX/SPDX) を WONTFIX した経緯」と「pip-compile --generate-hashes に着地した理由」を簡潔に記録
- これは spec / journal で重複しない、SECURITY.md は **policy** に集中、経緯は journal に置く

### D. 文書更新

#### D.1 spec の更新

- `detailed-design.md` §14.2 Step 3.2 完結記録 + §15 改訂履歴 0.29 entry
- `requirements_and_development.md` §13 Phase 3 サブステップ表に Step 3.2 完結反映、§14 Phase 4 廃止項目で「依存 audit / SBOM」を Step 3.2 完結扱いに更新
- `framework-shape.md` 影響なし (Layer 構造に変化なし、runtime 依存の挙動は変えていない、Layer 0 supply-chain の運用が増える)
- `CLAUDE.md` の Architectural invariants 「Minimum dependencies, supply-chain-aware」段落に lock 運用を追記、Phase 3 Step 3.2 で確立 → 確立済の文言に更新
- `README.md` インストール手順に「再現可能インストール = `pip install -r requirements.lock --require-hashes`」を追記

#### D.2 journal

- `phase3-step3-2.md` 完結ジャーナル新設 (Step 3.0 / 3.1 同型)
- Phase 5 申し送り: 「利用者プロジェクト向けに同じ規律を要求するかは Phase 5 スキル設計時に再判断」(qgb 本体の運用 ≠ 利用者プロジェクトの強制)

### E. テスト

#### E.1 lock 検証の機械化レイヤ

CI で `pip install --require-hashes` が実際の checker になるので、Python テストでは:

- `requirements.lock` / `requirements-dev.lock` が存在し、pip-compile 形式として parse できる
- hash 行が runtime 依存全部に付与されている (`--require-hashes` 要件)
- lock 内の package 名集合と pyproject.toml の dependencies / dev extras が一致 (古い lock 検出)
- 上記を「実 lock ファイルを repo から読む」テストで行う (fixture 不要、実 lock が固定装置)

予定テスト 4〜6 件、規模 0.1〜0.2。テスト総数 742 → 746〜748 件 (+4〜6) を見込む。

### F. スコープ外 (明示)

- **SBOM (CycloneDX/SPDX) 生成**: WONTFIX (上記 §3)、Phase 5 提供時に利用者要求があれば別議論
- **依存の vulnerability scan (pip-audit / safety)**: 本 Step では入れない。理由: vulnerability DB 自体が外部信頼層、qgb の closed-loop CI に runtime 依存を増やす判断は Phase 5 配布前に別途検討。NF-011 で「audit は qgb 本体外で行う」整理が現状の決め。
- **私的 PyPI mirror / proxy**: Phase 5 配布時の運用判断、qgb 本体には入れない
- **Windows-specific wheel pin**: jsonschema は pure Python、推移依存 (rpds-py) は C 拡張ありだが PyPI 配布の binary wheel を pip が選択するので OS 別 lock は不要 (本 Step 着手前確認事項)

## 規模見積もり

| サブステップ | 内容 | 規模 (Step 5 = 1.0 基準) |
|---|---|---|
| 3.2a | pip-tools を dev extras に追加 + lock 生成スクリプト確立 | 0.1〜0.2 |
| 3.2b | requirements.lock / requirements-dev.lock 初回生成 + commit | 0.1 |
| 3.2c | CI に lock install ステップ + `--check` (案 A) | 0.2〜0.3 |
| 3.2d | SECURITY.md「Dependency Lock Policy」節追加 | 0.1〜0.2 |
| 3.2e | lock 検証テスト 4〜6 件 + ruff 通過確認 | 0.1〜0.2 |

合計 **0.6〜1.0** (prejournal 計画段階見積もり、detailed-design.md §14.2 の 0.5〜0.8 とほぼ整合、補修なしの見通し)。

Step 3.1 で発生した「ステート不在化への補修方針転換」のような大幅上振れ要因は、本 Step では構造的に少ない (subprocess race のような微妙なステート空間がない、ほぼ装置の配線)。ただし Codex 計画レビューで supply-chain 観点の見落としが出る可能性は織り込んでおく。

## レビュープロセス (review-process memory v3 に従う)

Step 3.1 で確立した手順をそのまま適用:

1. 本 prejournal v1 commit
2. **Codex 計画レビュー** (`/ask-codex-with-context` 経由、本 prejournal + 関連 spec 部分を context として渡す)
3. 指摘を本 prejournal v2 に反映、または別途設計判断を確定
4. 本体実装 (3.2a〜3.2e)
5. **段 1 観点別 5 並列レビュー** (correctness / P9 / philosophy / NF-004 / spec-drift)
6. 段 2 Claude 集約
7. 段 3 Codex 横断レビュー
8. 補修 + 段 5 K=2 収束

小規模 Step だが省略しない (Step 3.1 教訓「small だから省略は禁じ手」)。

## 不確実性 (Codex に問いたい点候補)

1. **pip-tools か uv か pip + hashin 直接か**: NF-010 / NF-011 / Phase 5 配布視点で pip-tools が最適という判断が妥当か (新興 tool を避ける判断と「現代的な lock 機構を使う」判断のどちらを優先するか)
2. **lock ファイルを repo に commit する vs CI artifact のみ**: repo にコミットしても CI artifact にも残す二重化が必要か、片方で足りるか
3. **`pip-compile --check` を CI で発火させるか**: 案 A vs 案 B、Step 3.1 の「機械化できるものは機械化」と「最小 CI 維持」の衝突をどう裁くか
4. **OS / Python version 別 lock の要否**: 本 Step 着手前確認では「不要」と判断したが、推移依存に C 拡張 (rpds-py) があるので Windows / Linux / Python 3.10 / 3.12 で wheel が異なる影響を見落としていないか
5. **Phase 5 配布時に利用者に lock を強制するか**: 本 Step では qgb 本体の運用のみ、Phase 5 で「利用者プロジェクトにも同じ規律」を要求するかは別判断とする整理で妥当か

## 関連ファイル (本 Step で触る予定)

- `pyproject.toml` (dev extras に pip-tools 追加、3.2a)
- `requirements.lock` / `requirements-dev.lock` (新設、3.2b)
- `.github/workflows/test.yml` (install ステップ + lock check、3.2c)
- `SECURITY.md` (Dependency Lock Policy 節追加、3.2d)
- `tests/test_lock_integrity.py` (新設、3.2e)
- `development/docs/journal/phase3-step3-2.md` (完結ジャーナル、Step 完結時)
- `development/docs/detailed-design.md` §14.2 + §15 (完結時)
- `development/docs/requirements_and_development.md` §13 + §14 (完結時)
- `CLAUDE.md` (Architectural invariants 段落、完結時)
- `README.md` (再現可能インストール手順、完結時)
