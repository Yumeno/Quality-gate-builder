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

## 4. プロセスノート

5.b 段階 5 で確立した「push 後の CI 確認を検収に含める」を本 Step から適用 — 2 commit とも push 後に run 結果を機械確認してから完結判定した。release workflow は外向き権限 (contents: write) を持つため、指揮役が全文精読の上で commit した。
