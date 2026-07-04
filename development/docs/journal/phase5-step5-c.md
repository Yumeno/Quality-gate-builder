# Phase 5 Step 5.b-ci + 5.c 完結ジャーナル: golden CI 統合 + release workflow

- 完結日: 2026-07-04
- prejournal: `phase5-step5-c-prejournal.md` (commit `e420c10` 同梱)
- 編成: Fable 5 指揮 + sonnet subagent 実装 (5.b 以降継続)

## 1. 成果物と完結判定

| Step | 成果物 | 完結条件 | 判定 |
|---|---|---|---|
| 5.b-ci | test.yml `golden-integrity` job (`2ff877c`) | push CI green | ✅ (`e420c10` run で success) |
| 5.c | release.yml + prejournal (`e420c10`) | **workflow_dispatch dry-run green** | ✅ (dry-run run success — lineage (a) golden 一致 + lineage (b) epoch build 2 回 byte 一致 + zip 4 種生成を CI 上で機械確認) |

これで §6.3 item 16 (CI golden 検証) は pytest matrix (build_all 直接経路 × 4 セル) + golden-integrity job (regen script 経路) の二経路で完結。

## 2. 設計判断 (prejournal から確定、詳細はそちら)

タグ pattern `skill-v*` / 二系統検証 / **rebuild-instead-of-transfer** (release job は artifact 転送でなく再 build = 決定性保証の dogfood + action 面を checkout/setup-python の 2 pin に維持) / dispatch = dry-run・tag = release の入口分離 / write 権限は release job のみ / commit hash は zip 内容でなく release notes (golden 自己参照の構造的回避) / `gh release create --verify-tag`。

## 3. 残工程 (Phase 5)

1. **実タグ push** (user 決裁): `git tag skill-v0.1.0 && git push origin skill-v0.1.0` → release workflow が初回 GitHub Release (4 zip) を publish。version は metadata.yaml (0.1.0) と揃える
2. **5.d canary**: release zip (または dist build) の Claude full を `~/.claude/skills/qgb/` に配置 → 実セッションで「qgb 入れて」による skill 発火確認 — **対話型、user と共同**
3. **5.e dogfood**: Claude full/split 深掘り + Codex full/split smoke + 保守シナリオ (A1' 一文変更の伝播 / japanese-docs-pwsh の θ+ι+κ 実機 / 5.b 申し送りの κ false positive 確認) — 対話型
4. 5.b-ci 送りの改善 2 件 (BuildError 境界の完全統一 / regen cell 列挙の metadata 由来化) は 5.e 後のバックログ

## 3.5 配布戦略の階段 (2026-07-04 追記、user 質問「python パッケージが含まれないのは今後どう対策する?」への回答を正本化)

スキルは qgb 本体を同梱しない (framework-shape の Layer 分離)。本体入手の対策は 3 段:

1. **短期 (v0.1.1 バックログ、3 点セット)**:
   - **venv を既定の documented path に** (user 指摘 2026-07-04: 「ユーザー目線でも、いきなりグローバルに入れるのは勇気いる」)。現行 INSTALL.md / body.md §10.1 は venv 言及なしの `pip install -e` で、字義どおり実行するとグローバルに入る — NF-003 (最小侵襲性) を利用者マシン環境にも適用し、`py -3 -m venv .venv` → activate → install の正順を既定に。グローバルは注記に降格
   - **タグ固定 install**: `pip install git+https://github.com/Yumeno/Quality-gate-builder.git@skill-v<version>`。version は metadata.yaml 由来で build 時に既知なので converter が自タグを焼き込める。version skew を構造的に解消
   - **skill 側の venv 認識規律**: セッション shell は venv を自動 activate しないため、skill が `python -m qgb` を叩く前に「このプロジェクトの qgb はどの python にいるか」を確定する (§6.5 runtime 解決の思想を qgb 自身の呼び出しに適用)。5.d canary でこの摩擦の実態を観察してから文言化
2. **中期 (v0.1.1 同時候補)**: release workflow で `python -m build` した wheel を同じ GitHub Release に添付 (git 不要・オフライン可・スキルと本体が同一 Release で version ペア。新規 action 不要、sha256 は release notes)
3. **長期 (Phase 6 判断)**: PyPI 公開 + trusted publishing + 名前の防衛確保 (squatting リスクの根治)。SECURITY.md への配布ポリシー追記とリリース運用コミットメントが伴うため、5.e の利用者像の実感を得てから判断

5.d canary 時点の実務: 利用者はスキル同梱 INSTALL.md / body.md §10.1 の記載どおり clone + `pip install -e` (v0.1.0 の documented path)。canary ではこの documented path 自体も検証対象。

## 4. プロセスノート

5.b 段階 5 で確立した「push 後の CI 確認を検収に含める」を本 Step から適用 — 2 commit とも push 後に run 結果を機械確認してから完結判定した。release workflow は外向き権限 (contents: write) を持つため、指揮役が全文精読の上で commit した。
