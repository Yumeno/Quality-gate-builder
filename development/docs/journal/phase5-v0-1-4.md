# Phase 5 v0.1.4 skill 文言改善バッチ (canary #2 反映)

- 実施日: 2026-07-04 / 仕様: [Issue #29](https://github.com/Yumeno/Quality-gate-builder/issues/29) (canary #2 journal `phase5-step5-d-canary2.md` の 6 件 + 実装中発見 1 件)
- 編成: Fable 5 指揮 (文言起草・検収) + sonnet 実装 + sonnet 独立レビュー 1 レンズ (v0.1.2 と同じ比例縮退)
- 変更対象: `skills/source/body.md` / `skills/source/metadata.yaml` / `pyproject.toml` / `.github/workflows/release.yml`

## 1. 設計判断 (user 確定 2026-07-04)

- **Item 3 (examples)**: 文言修正のみ採用。zip 同梱は見送り (canary #2 で自力設計が成立した実測に基づく。5.e で必要性が実証されたら別リリースで)
- **Item 6 (バージョン 3 空間)**: **lockstep 方式** — pyproject.toml をリリースと同期 bump (v0.1.4 から)。release CI のタグ整合ガードに pyproject 検証を追加して機械強制。§10.1 に版空間の読み方を明記

## 2. 実装内容 (Issue #29 の 6 件 + 1)

1. **§3.2 proposal 例を実スキーマに同期**: `schema_version`/`proposal_type`/`stages` 必須、root additionalProperties: false、設計根拠は `source_metadata` へ。「stages[] は全置換」の重要仕様も明文化。§5.5 共通前提の `basis[]` 言及も `source_metadata` に修正
2. **§3.3/§3.4 human_reviewed を実機構に同期**: proposal に承認フラグは無い — 承認 = adopt 実行を許可する手続きそのもの (§3.5 決定所有権に接続)。§3.4 の検証リストから虚偽 2 項 (human_reviewed 確認 / 変更差分提示) を除去し実装と一致させた
3. **examples / philosophy.md の repo 限定注記**: §3.1 Read リスト + §7 冒頭 + §7.2。「参照できなくても設計は成立する」を明記
4. **スキーマ第一の作法**: 3 つの起草地点 (§6.1 step 5 project-context / 段階設計 §3.2 proposal / §6.6+レビュー §5 knowledge) すべてに「起草前に同梱スキーマを Read、例は説明用でスキーマが正」を挿入。同梱スキーマの場所特定 one-liner (`import qgb` 経由) は canary #2 の運転 agent が失敗から自力到達した手法をそのまま採用
5. **§6.1 step 8 新設 — 判定履歴の保存方針を設計分岐として提示**: 機構の事実 (latest 上書き / artifacts 揮発) は skill が開示し、残すか・どう残すかは利用者の設計判断。git を前提にしない。「機構の事実は開示、方針の判断は利用者所有」の一般則の初の明文化
6. **バージョン lockstep**: pyproject 0.1.0 → 0.1.4 (`qgb --version` / gate.json `runner.version` は importlib.metadata 経由なので自動追従)。release.yml ガードに pyproject == metadata.yaml 検証を追加。§10.1 に 3 空間 (パッケージ / skill / converter) の読み方
7. **(実装中発見) レビュー観点プロンプト §5 の knowledge 例が実スキーマ違反**: `entry_id`/`entry_type`/`llm_advisory` は存在しない field 名・enum 値で、必須 field 欠落により add-knowledge で拒否される嘘の few-shot だった。実 enum (`kind: inferred_fact` / `source_type: inferred`) に同期し、§2.2/§3.1/§3.5 の同種表記も修正。canary #2 の運転 agent がスキーマ直読で正しく書けていた (= 例を信じていたら失敗していた) ことが発見の契機

## 3. 検証

- 【要検証】3 点: proposal JSON 例 = schema validate PASS / adopt 検証リスト = proposal.py・preflight.py と一致確認 / knowledge 例 2 つ = enum 調整後 validate PASS
- 846 passed, 3 skipped。py -3.10 実ビルド = golden と同一 digest
- digest `8297056c361259ee` (v0.1.3) → `615b17206d93a251` (v0.1.4 最終、must-fix 反映後)

## 4. 独立レビュー結果 (1 レンズ、must-fix 3 件 → 全反映)

1. **取り残し**: `skills/source/lint/README.md` に旧語彙 (`entry_type: review_note` + `source_type: llm_advisory`) が残存 — body.md 外の source file で converter が verbatim copy するため一括修正の網から漏れた。→ 実 enum に修正
2. **番号衝突**: 段階設計プロンプト §3.3 の「(§3.5 決定の所有権)」が、同プロンプト自身の §3.5 (整合性の機械検証) と衝突 — split モードで helper file 単体を読む読者が誤解する。→ 「本文 §3.5『対話の姿勢』の決定の所有権。本プロンプト自身の §3.5 とは別」に明確化
3. **P8 記述の 3 箇所目との矛盾**: レビュー観点プロンプト §2.3 が「human_reviewed: true は人間のみが立てる」の旧・厳格形のままで、本バッチが §6.1/§3.3 に入れた緩和 (明示承認発話直後の agent 代行は可) と矛盾。→ §2.3 にも同じ carve-out を反映 (判断は利用者のもの / 代行は明示承認直後のみ / 無断・自動 true 化は P8 違反)

レビューの検証系発見: adopt 検証リストは実装と一致、JSON 例 3 つ validate PASS、バージョン 0.1.4 は golden 全域で整合、release.yml regex は実 pyproject に対して動作確認済み。既知の非標準慣行として「§12 = 段階設計プロンプト全体のエイリアス」(full モードで実在しない番号) が指摘されたが、既出荷の確立済み慣行のため本バッチでは変更せず (将来の見出し体系整理の候補として記録)。

## 5. リリース

commit → CI green → user が `skill-v0.1.4` タグ → release workflow (新ガード: metadata + pyproject の二重検証の初実戦) → Issue #29 close。
