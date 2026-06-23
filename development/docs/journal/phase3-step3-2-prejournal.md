# Phase 3 Step 3.2 着手前判断: 依存解決固定 (lock + hash)

着手前判断確定: 2026-06-24 (v1)
Codex セカンドオピニオン反映 + ライン引き再点検: 2026-06-24 (v2)
位置: Phase 3 残り 1 ステップ (Step 3.0 / 3.1 完結後)、Phase 5 着手前提条件の最後

## v2 改訂サマリ (v1 → v2)

v1 commit (`5212c0d`) を Codex セカンドオピニオン r1 にかけ、7 件 finding を受領。さらに user との対話で 1 段上のライン引き (artifact 化が qgb 本体 CI 責務か否か) を再点検し、以下を確定:

- **artifact 化撤回**: 「過去のコミット時点の lock を 90 日保管する」は qgb 本体の正しさに影響しない、利用者運用 (社内コンプライアンス / SOC2 / SBOM 要求等で必要期間が異なる)。Step 3.1 で JUnit XML を WONTFIX 整理したのと同型。Codex finding 5 (upload-artifact SHA pin) は自動消滅
- **qgb 本体 CI の責務範囲を再定義**: 「Phase 5 配布物としての qgb 本体の品質を機械的に保証する」だけ。CI による証跡保管 / artifact 運用 / SBOM 等は利用者運用
- **CI 設計例の置き場所**: `development/docs/ci-examples.md` 新設で 1 ページ程度の参考資料、本格的な利用者プロジェクト向け CI テンプレは Phase 5 Skill Creator が生成
- **Codex finding 1〜4, 6, 7 全反映**: `pip-compile --check` → temp lock + `git diff --exit-code`、layered lock (`-c requirements.lock`)、文言修正 (PyPI install ≠ lock 再現)、`--only-binary :all:` 追加、pip-tools 根拠の正確化 (Jazzband / pip-compatible / mature / dev-only)、build dep / tool bootstrap の信頼層境界明記

## 経緯

Phase 3 Step 3.0 (`46d892a`, 2026-06-21) で detect 廃止 + project-context 二重ファイル設計、Step 3.1 (`564092b`, 2026-06-24) で command runner 強化 + CI 雛形 + 補修 7 件が完結。残るは **依存解決の固定** だけで、これが終われば Phase 5 (Skill Creator 化) 着手前提条件 (機械責務側の最終整備) が揃う。

1. ✅ Step 3.0: 対象認識のライン引き (LLM / 機械 / 補佐 Agent 三層)
2. ✅ Step 3.1: command 実行の機械的信頼性 (process tree kill / per-stream cap / .bat escape / CI matrix)
3. **Step 3.2 (本書)**: 依存解決固定 (lock + hash、supply-chain 信頼)
4. (任意) Step 3.3: Phase 2 繰越実需回収

仕様の出典は `development/docs/detailed-design.md` §14.2 Step 3.2、`development/docs/requirements_and_development.md` §13 Phase 3 サブステップ、§14 Phase 4 廃止に伴う「依存 audit / SBOM」の吸収方針。

## 本 Step の理念的位置づけ

Step 3.0 / 3.1 で確立した 2 つのライン引き教訓を本 Step に適用する:

- **機械責務 vs LLM 責務の混同を避ける** (Step 3.0 教訓): 「依存ライブラリの選定 / 監査」は LLM (人 + Phase 5 スキル) が判断、「再現可能な hash 固定」は qgb / CI が機械的に強制
- **症状対処より入らない設計** (Step 3.1 教訓): 「壊れたらアラート」でなく「壊れた依存解決が CI を緑にできない構造」を作る

v2 で再点検した 3 つ目のライン引き:

- **qgb 本体の責務 vs 利用者運用の責務**: qgb 本体 CI は **「Phase 5 配布物としての qgb 本体の品質を機械的に保証する装置」**。lock の artifact 化 / 証跡の長期保管形式 / SBOM 等は **利用者運用** (qgb は git 環境外でも使う可能性あり、CI そのものを使うかも利用者判断)

### 1. なぜ依存解決を固定するのか (P7 / NF-010 / NF-011 の補完)

Phase 5 で Skill Creator が利用者に qgb を配布するとき、「qgb を実行する環境で再現可能な依存解決が成立する」ことが supply-chain 信頼の前提になる。現状の `pyproject.toml` は:

```toml
dependencies = [
    "jsonschema>=4.20,<5.0",
]
```

しか宣言していない。これは:

- jsonschema には複数の推移依存 (attrs / jsonschema-specifications / referencing / rpds-py) があり、それぞれが mutable な version range で解決される
- 「Claude が論証で『qgb 0.1.0 は壊れない依存で動く』と言う」は LLM 評価で、P6 違反の構造 (Step 3.1 で CI 機械化したのと同じ理屈)
- jsonschema 自体が malicious 化されなくても、推移依存のどこか 1 つが乗っ取られれば pip 経由で侵入できる (NF-011 想定脅威)

つまり Step 3.2 は **「qgb 自身の依存解決を機械的に固定し、CI でその固定値が再現可能であることを毎回検証する」装置** を入れる。これは Step 3.1 で「Windows ローカルで通った ≠ POSIX で通る」を CI 緑で機械判定したのと完全に同型。

### 2. なぜ SBOM ではなく lock + hash を採用するのか (2026-06-13 Codex セカンドオピニオン経由 + r1 確認)

繰越判定パート (`journal/phase2-step2-7.md`) で SBOM を一度 WONTFIX としたが、Codex セカンドオピニオン後に撤回した経緯:

- **pip freeze だけでは不十分**: 推移依存の version は固定できても hash は固定できない、同 version でも yanked / republish された artifact を引かされる余地が残る
- **SBOM (CycloneDX / SPDX) はやり過ぎ**: 利用者プロジェクト向け配布物の monitoring 用途。qgb 本体は package 1 個 + 推移依存数個、SBOM のために new tool を増やすと NF-010 (依存最小化) と緊張
- **着地点 = pip-compile --generate-hashes + requirements lock**: 既存 pip resolver と同じ機構を使う dev-only tool、hash 固定、CI で再現性検証

(v2 追記、Codex r1 経由): 「lock が SBOM の代替」ではなく、**「qgb 本体の immediate risk は lock + hash で直接効く、SBOM は inventory / vulnerability workflow 用で本 Step では過剰」** という整理が正確。

### 3. なぜ uv / poetry / pdm でなく pip-tools なのか (v2 で根拠修正)

候補: pip-tools (pip-compile) / uv / poetry / pdm / pip freeze + hashin 等。

pip-tools 採用判断の根拠 (v2 で Codex r1 finding 6 反映):

- **pip と同じ resolver を使う**: lock の生成と利用環境の install が同じ機構なので「lock は通ったが install で別解決された」が原理的に起きにくい
- **pip requirements 形式と hash mode に素直に乗る dev-only tool**: pip-tools は Jazzband 配下のメンテナンスで、PyPA 公式ではないが、pip と完全互換の requirements / hash 形式を維持している
- **NF-010 (依存最小化)**: pip-tools 自体は CI / 開発時のみ依存、runtime には入らない。`pyproject.toml [project.optional-dependencies] dev` に追加 (Step 3.1 で pytest / ruff を入れたのと同じ枠)
- **NF-011 (サプライチェーン)**: long-running maintenance、actions/setup-python と同じ external 信頼層として扱う (PyPA 公式の擬装はしない)
- **uv 不採用理由**: 新興 (2024 登場)、Rust 製で qgb の「stdlib + pip」前提から大きく外れる。Phase 5 で利用者プロジェクトに uv を要求するかは別判断。qgb 本体は保守的に pip-tools。
- **poetry / pdm 不採用理由**: build backend 自体を置き換える、pyproject.toml が poetry / pdm 専用 schema になる。setuptools + pyproject.toml の現構成を維持したい (Phase 1 から不変、回帰リスク最小)
- **pip lock 不採用理由 (Codex r1 指摘経由)**: 現時点で experimental 扱い、platform / current Python 有効範囲の注意があるため、本 Step の保守性には不向き

### 4. なぜ CI で lock の hash 検証を行うのか (v2 で「artifact 化」を削除)

Step 3.1 で確立した「qgb の P6 を qgb 自身に適用 = CI 緑 = 機械的判定」の延長:

- CI で `pip install --require-hashes --only-binary :all: -r requirements.lock` が 4 matrix (Windows + Ubuntu × Python 3.10 + 3.12) で緑になることを毎回検証
- これにより「lock の hash が改竄されていない」「lock 内 package が全 matrix で binary wheel で install 可能」が機械的に保証される
- もし悪意ある PR が `pyproject.toml` の `jsonschema>=4.20,<5.0` を `jsonschema>=999` 等に書き換えて推移依存を増やそうとすると、`pip-compile` 結果と repo の lock の差分が CI で検出される (`git diff --exit-code`、Codex r1 finding 1 反映)
- repo の lock 自体が git 履歴で永続的に追跡可能 (P7 再現可能な証跡)

**v2 で確定: artifact 化は qgb 本体 CI 責務外** (上記「3 つ目のライン引き」参照)。artifact / 長期保管 / SBOM 等の証跡保管形式は利用者運用。

## Step 3.2 スコープ確定

### A. lock ファイルの生成と運用

#### A.1 `requirements.lock` を repo に commit

- `python -m piptools compile --generate-hashes --output-file=requirements.lock pyproject.toml` を人手実行
- **lock ファイルは repo にコミット** する (rationale: Step 3.1 で SHA pin を repo に置いたのと同型、git log で diff を人間が見られる状態を維持)
- file 名は `requirements.lock` (pip-tools 慣習)。`.txt` 拡張子も慣習にあるが、`.lock` の方が「人間が直接編集すべきでない」シグナルが強い
- 内容: runtime 依存 (`jsonschema` + 推移依存) の hash 付き固定。dev 依存 (pytest, ruff, pip-tools) は別 lock (`requirements-dev.lock`) として分離

#### A.2 dev 依存の layered 分離 (`requirements-dev.lock`) — v2 で構造変更 (Codex r1 finding 2)

- `python -m piptools compile --generate-hashes --extra=dev -c requirements.lock -o requirements-dev.lock pyproject.toml`
- **`-c requirements.lock` (constraint) が重要**: dev lock の解決が runtime lock の pin に制約されることで、「dev lock を install したら runtime 依存が別 version に上書きされた」が原理的に起きない
- 分離理由: 利用者の install (`pip install qgb`) には dev 依存は不要、別 lock にしておけば「runtime supply-chain」と「開発環境 supply-chain」の audit を分けて議論できる (P9 単一責任)

#### A.3 lock の運用契約 (人手更新、Dependabot/Renovate 不使用と整合)

- lock 更新は人手 + commit メッセージで理由明示 (Step 3.1 SHA pin と同じ運用契約)
- 更新トリガ: pyproject.toml の依存範囲変更 / 推移依存の security advisory / 定期 (四半期、Step 3.1 と同じスケジュール) / ad-hoc (理由明示)
- 「Completely ad-hoc with no documented reason」は不可 (Step 3.1 と同じ規律)
- 詳細は SECURITY.md に「Dependency Lock Policy」節を追加

### B. CI 統合 (v2 で artifact 化撤回)

#### B.1 lock との一致検証

CI matrix に **追加 job ではなく既存 job のステップ追加** で実装 (理由: matrix を増やすと job 数が 4 → 6 etc に膨らみ、Step 3.1 で確立した「最小 CI」が崩れる)。

既存の 4 jobs それぞれで:

1. `python -m pip install --require-hashes --only-binary :all: -r requirements.lock` で qgb の runtime 依存を hash 検証 + sdist 任意コード実行面を閉じた状態で install (Codex r1 finding 4 反映)
2. `python -m pip install --require-hashes --only-binary :all: -r requirements-dev.lock` で dev 依存を install
3. `python -m pip install --no-deps -e .` で qgb 本体だけを editable install (依存は lock 経由で確定済)

#### B.2 lock と pyproject.toml の整合性検証 (Codex r1 finding 1 で実装変更)

`pip-compile --check` は現行 pip-tools reference に存在しない。代わりに以下の方式:

```bash
python -m piptools compile --generate-hashes -o /tmp/runtime.lock pyproject.toml
git diff --exit-code --no-index requirements.lock /tmp/runtime.lock
python -m piptools compile --generate-hashes --extra=dev -c requirements.lock -o /tmp/dev.lock pyproject.toml
git diff --exit-code --no-index requirements-dev.lock /tmp/dev.lock
```

- これにより「lock が古い (pyproject.toml の依存範囲変更が反映されていない)」を CI で機械検出できる
- ubuntu-latest + Python 3.12 の 1 job のみで実行 (整合性は OS 非依存、4 matrix で重複実行する必要なし、NF-010)
- 実行コストは pip-compile が数秒 + git diff が瞬時、CI 全体時間への影響は無視できる

#### B.3 CI ファイル variant の境界 (v2 で artifact 化撤回を反映)

- Step 3.1 の CI は **pytest only**、本 Step では同じファイル `test.yml` に install ステップ + 整合性検証ステップを差し込む形で完結させる
- 別 workflow (例 `lock.yml`) を新設しない (NF-010 minimum surface、Step 3.1 で確立した「workflow 1 個」を維持)
- **artifact 化は採用しない** (v2 確定): lock は git に commit されているので `git show <sha>:requirements.lock` で永続取得可能、artifact は 90 日制限がある一時的補助に過ぎず、追加する third-party action (upload-artifact) 分の supply-chain surface を入れる価値がない
- artifact 化は qgb 本体 CI 責務外 (利用者運用)、§D.3 で参考設計例として docs に置く

### C. SECURITY.md 拡張

#### C.1 「Dependency Lock Policy」節を新設

- runtime lock / dev lock の分離理由 (P9 単一責任)
- layered lock の構造 (`-c requirements.lock`、Codex r1 finding 2)
- 更新トリガ 5 種 (Step 3.1 SHA pin policy と並列形式で記述、運用負荷の二重化を避ける)
- 更新手順 (pip-compile 実行 + 単一目的 commit)
- ad-hoc bump の commit メッセージ規約
- Dependabot/Renovate 不採用理由 (Step 3.1 と同じ理由、参照で済ませる)
- **qgb 本体 CI 責務の境界明記** (v2): 「matrix CI が単一 lock の妥当性を検証する」(Codex r1 質問 4 への回答)、「artifact 化 / 長期保管 / SBOM は利用者運用」

#### C.2 信頼層境界の明示 (v2 新設、Codex r1 finding 7)

`pip install --no-deps .` でも PEP 517 build isolation が build-system requires を取得する場合がある。lock を検証するための pip-tools 自身も bootstrap 問題を持つ。

- runtime lock は **runtime 依存のみ** (jsonschema + 推移依存)
- pip / setuptools / build backend / GitHub Actions runner / pip-tools 自身は **別信頼層**
- 各信頼層の管理:
  - pip / setuptools: actions/setup-python の SHA pin で固定
  - build backend (setuptools): pyproject.toml `build-system.requires` で範囲指定 (本 Step では lock 化しない、build backend lock は次世代の議論)
  - GitHub Actions runner: actions/checkout + actions/setup-python の SHA pin
  - pip-tools: dev lock で hash 固定 (bootstrap は CI が `python -m pip install pip-tools==<pin>` で行う前段がある可能性、本体実装段階で詳細確定)

#### C.3 SBOM 撤回履歴の整理

- 「SBOM (CycloneDX/SPDX) を WONTFIX した経緯」と「pip-compile --generate-hashes に着地した理由」を簡潔に記録
- これは spec / journal で重複しない、SECURITY.md は **policy** に集中、経緯は journal に置く

### D. 文書更新

#### D.1 spec の更新

- `detailed-design.md` §14.2 Step 3.2 完結記録 + §15 改訂履歴 0.29 entry
- `requirements_and_development.md` §13 Phase 3 サブステップ表に Step 3.2 完結反映、§14 Phase 4 廃止項目で「依存 audit / SBOM」を Step 3.2 完結扱いに更新
- `framework-shape.md` 影響なし (Layer 構造に変化なし、runtime 依存の挙動は変えていない、Layer 0 supply-chain の運用が増える)
- `CLAUDE.md` の Architectural invariants 「Minimum dependencies, supply-chain-aware」段落に lock 運用を追記、Phase 3 Step 3.2 で確立 → 確立済の文言に更新
- `README.md` インストール手順に「再現可能な検証用 install = `pip install --require-hashes --only-binary :all: -r requirements.lock`」を追記 (Codex r1 finding 3、「pip install qgb で再現可能」は言わない)

#### D.2 journal

- `phase3-step3-2.md` 完結ジャーナル新設 (Step 3.0 / 3.1 同型)
- Phase 5 申し送り: 「利用者プロジェクト向けに同じ規律を要求するかは Phase 5 スキル設計時に再判断」(qgb 本体の運用 ≠ 利用者プロジェクトの強制)、「CI / artifact / SBOM 等の証跡保管形式は利用者運用」

#### D.3 CI 設計例の docs 化 (v2 新設)

- `development/docs/ci-examples.md` 新設、1 ページ程度
- 内容:
  - 「qgb 本体 CI は qgb 本体のテスト機械化装置」「lock の artifact 化は qgb 本体責務外」の文脈
  - 利用者が「lock を artifact として 90 日保管」「SBOM 生成」「vulnerability scan (pip-audit)」を CI に組み込みたい場合の **参考例** (実装の押し付けでなく選択肢として)
  - 本格的な利用者プロジェクト向け CI テンプレは Phase 5 Skill Creator が生成する旨を明記 (Phase 5 への送り)

### E. テスト

#### E.1 lock 検証の機械化レイヤ

CI で `pip install --require-hashes --only-binary :all:` と `git diff --exit-code` が実 checker になるので、Python テストでは:

- `requirements.lock` / `requirements-dev.lock` が存在し、pip-compile 形式として parse できる
- hash 行が依存全部に付与されている (`--require-hashes` 要件)
- lock 内の package 名集合と pyproject.toml の dependencies / dev extras が一致 (古い lock 検出)
- 上記を「実 lock ファイルを repo から読む」テストで行う (fixture 不要、実 lock が固定装置)

予定テスト 4〜6 件、規模 0.1〜0.2。テスト総数 742 → 746〜748 件 (+4〜6) を見込む。

### F. スコープ外 (明示、v2 で qgb 本体責務範囲を明示)

#### F.1 利用者運用 (qgb 本体 CI 責務外)

- **lock の artifact 化 (CI 上の長期保管)**: 90 日 / 1 年 / 永続のどれが必要かは利用者ごとに違う (社内コンプライアンス / SOC2 audit / 業界規制等)。qgb は git 環境外での利用も想定、CI そのものを使うかも利用者判断。設計例は §D.3 の docs/ci-examples.md で参考提示
- **SBOM (CycloneDX/SPDX) 生成**: 利用者運用、本 Step では WONTFIX、Phase 5 提供時に利用者要求があれば別議論
- **依存の vulnerability scan (pip-audit / safety)**: 利用者運用、本 Step では入れない。理由: vulnerability DB 自体が外部信頼層、qgb の closed-loop CI に runtime 依存を増やす判断は Phase 5 配布前に別途検討。NF-011 で「audit は qgb 本体外で行う」整理が現状の決め
- **JUnit XML / PR コメント連動**: 利用者運用 (Phase 4 廃止時に整理済)

#### F.2 別信頼層 (本 Step では触らない、§C.2 で境界明記)

- **私的 PyPI mirror / proxy**: 利用者運用の領域、qgb 本体には入れない
- **build backend (setuptools) の lock 化**: 次世代の議論、本 Step では pyproject.toml `build-system.requires` の範囲指定のまま
- **Windows-specific wheel pin**: jsonschema は pure Python、推移依存 (rpds-py) は C 拡張ありだが PyPI 配布の binary wheel を pip が選択するので OS 別 lock は不要 (本 Step 着手前確認事項、CI 4 matrix で実証)

## 規模見積もり (v2 で上方修正、Codex r1 反映)

| サブステップ | 内容 | 規模 (Step 5 = 1.0 基準) |
|---|---|---|
| 3.2a | pip-tools を dev extras に追加 + lock 生成スクリプト確立 | 0.1〜0.2 |
| 3.2b | requirements.lock 初回生成 + layered requirements-dev.lock 生成 + commit | 0.1〜0.2 |
| 3.2c | CI に `--require-hashes --only-binary :all:` install ステップ + temp lock + git diff 整合性検証 (Codex r1 finding 1, 2, 4) | 0.3〜0.4 |
| 3.2d | SECURITY.md「Dependency Lock Policy」+「信頼層境界」節追加 (Codex r1 finding 7) | 0.2〜0.3 |
| 3.2e | lock 検証テスト 4〜6 件 + ruff 通過確認 | 0.1〜0.2 |
| 3.2f | `docs/ci-examples.md` 新設 (v2 追加) | 0.1〜0.2 |

合計 **0.9〜1.5** (v2 で上方修正、prejournal 計画段階見積もり、Codex r1 経由で 0.6〜1.0 → 0.9〜1.5 へ拡大、補修なしの見通し)。

Step 3.1 で発生した「ステート不在化への補修方針転換」のような大幅上振れ要因は、本 Step では構造的に少ない (subprocess race のような微妙なステート空間がない、ほぼ装置の配線)。ただし 4 matrix で hash + binary install が全部通るかの実証で予期しない wheel 不在等が出る可能性は織り込み (Codex r1 質問 4 への回答経由)。

## レビュープロセス (review-process memory v3 に従う)

Step 3.1 で確立した手順をそのまま適用:

1. ✅ 本 prejournal v1 commit (`5212c0d`)
2. ✅ **Codex 計画レビュー r1** (2026-06-24、7 件 finding 受領、本 v2 に反映)
3. ✅ v2 commit (次)
4. (任意) Codex r2 で v2 確認
5. 本体実装 (3.2a〜3.2f)
6. **段 1 観点別 5 並列レビュー** (correctness / P9 / philosophy / NF-004 / spec-drift)
7. 段 2 Claude 集約
8. 段 3 Codex 横断レビュー
9. 補修 + 段 5 K=2 収束

小規模 Step だが省略しない (Step 3.1 教訓「small だから省略は禁じ手」)。

## Codex r1 finding 反映トレース (v2 確定)

| Codex finding | severity | 反映先 |
|---|---|---|
| 1. `pip-compile --check` 危険 | High / code fix | §B.2 で temp lock + `git diff --exit-code` 方式に変更 |
| 2. dev lock を runtime lock で制約 | High / code fix | §A.2 で `-c requirements.lock` の layered lock に変更 |
| 3. 「pip install qgb 再現可能」言い過ぎ | High / spec fix | §D.1 README 文言を「再現可能な検証用 install」に修正 |
| 4. `--only-binary :all:` 追加 | Medium / code fix | §B.1 で CI install コマンドに追加 |
| 5. upload-artifact SHA pin | Medium / code fix | **自動消滅** (artifact 化を v2 で撤回) |
| 6. pip-tools の根拠を「PyPA 公式」と書かない | Medium / spec fix | §3 で「Jazzband / pip-compatible / mature / dev-only」に修正 |
| 7. build dep / tool bootstrap の信頼層境界 | Medium / spec fix | §C.2 で「信頼層境界の明示」節を新設 |

## v2 で追加した user 判断 (artifact 化撤回 + ci-examples.md)

| 論点 | v1 案 | v2 確定 | 根拠 |
|---|---|---|---|
| artifact 化 | CI で 90 日保管 | 撤回 | qgb 本体の正しさに影響しない、利用者運用 (Step 3.1 JUnit XML WONTFIX と同型)、qgb は git 環境外でも使う可能性あり |
| CI 設計例の置き場所 | (未定) | `docs/ci-examples.md` 新設 (1 ページ程度) | 「これは qgb 本体の設計ではなく利用者向け参考資料」のシグナルが強い、本格的なテンプレは Phase 5 Skill Creator |

## 不確実性 (本体実装で再検討、Codex r2 で扱う可能性あり)

1. **pip-tools 自身の bootstrap 経路**: CI で pip-tools をどう install するか (dev lock 経由か、固定 version 単独 install か)。§C.2 信頼層境界と整合する経路を本体実装で確定
2. **temp lock 生成の job 配置**: §B.2 を ubuntu-latest + Python 3.12 の 1 job のみで行う案を採用しているが、整合性検証を 4 matrix に並列散らす案も検討余地あり (本体実装段階)
3. **Phase 5 で利用者プロジェクトに lock 規律を勧めるテンプレの形**: 本 Step スコープ外、Phase 5 着手時に再判断

## 関連ファイル (本 Step で触る予定)

- `pyproject.toml` (dev extras に pip-tools 追加、3.2a)
- `requirements.lock` / `requirements-dev.lock` (新設、3.2b)
- `.github/workflows/test.yml` (install ステップ + 整合性検証、3.2c)
- `SECURITY.md` (Dependency Lock Policy + 信頼層境界、3.2d)
- `tests/test_lock_integrity.py` (新設、3.2e)
- `development/docs/ci-examples.md` (新設、3.2f、v2 追加)
- `development/docs/journal/phase3-step3-2.md` (完結ジャーナル、Step 完結時)
- `development/docs/detailed-design.md` §14.2 + §15 (完結時)
- `development/docs/requirements_and_development.md` §13 + §14 (完結時)
- `CLAUDE.md` (Architectural invariants 段落、完結時)
- `README.md` (再現可能な検証用 install 手順、完結時)
