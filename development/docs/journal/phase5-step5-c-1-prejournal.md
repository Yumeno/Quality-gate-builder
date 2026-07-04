# Phase 5 Step 5.c-1 Prejournal: v0.1.1 install UX 一式

- 作成日: 2026-07-04 / Issue: [#27](https://github.com/Yumeno/Quality-gate-builder/issues/27)
- 由来: 5.d canary 準備中の user 指摘 2 件 (グローバル install の心理障壁 / 1 コマンド setup の要望)。検討経緯は `phase5-step5-c.md` §3.5
- 編成: Fable 5 指揮 + sonnet subagent 実装 (継続)

## 設計判断

1. **4 点セット** (Issue #27 記載): venv 既定化 / タグ固定 install / skill の venv 認識規律 / 同梱 setup script (ps1 + sh、converter 生成)
2. **setup script は copy でなく converter 生成物**: タグ (skill-v{metadata.version}) の焼き込みが必要なため。生成物 header 付き (.sh は shebang の後)。digest への新カテゴリ追加は不要 (生成物であり入力ではない。入力側の変更 = converter source (cat 7) + body.md (cat 3) + metadata (cat 1) が digest に反映)
3. **冪等・最小侵襲**: 既存 .venv は温存 (作らない、消さない)。fail-closed (検証失敗 = 非ゼロ exit + 明確なメッセージ)
4. **--from-path (-FromPath) オプション**: ローカル clone からの editable install (オフライン / 開発 / canary 用)。既定はタグ固定 git+ install
5. **信頼境界の正直さ**: git+ install は --require-hashes 不可 = clone と同等の信頼。それ以上を装わず INSTALL と script コメントに明記 (NF-011)
6. **.ps1 は自分の規律で**: §6.5 PS5 規律 (pure ASCII / encoding 明示 / $ErrorActionPreference Stop) を skill 同梱物が自ら遵守
7. **metadata version 0.1.0 → 0.1.1**、golden 再生成、生成 script の実機 E2E (ps1/sh 両方、--from-path で scratch へ実 install → qgb --version exit 0)
8. リリースタグ push は user 決裁 (5.c と同じ)。canary は v0.1.1 で実施

## 完結条件

全 pytest green + push CI green + setup script 実機 E2E 成功 (両 OS 系統のうち本機で可能な範囲 = ps1 実行 + Git Bash で sh 実行)。
