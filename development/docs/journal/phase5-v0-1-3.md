# Phase 5 v0.1.3: 配布物ヘッダに skill_version 追加 (canary #2 設営中の実害修正)

- 実施日: 2026-07-04 / 発見者: user (canary #2 設営中)
- 症状: v0.1.2 を install したのに受験 LLM がスキル版を「0.1.0」と認識

## 1. 根本原因

配布 SKILL.md に**スキル自体のバージョン表記が存在しなかった**。frontmatter は name / description / allowed-tools のみ。生成ヘッダの唯一のバージョン風文字列は `converter_version: 0.1.0` (変換ツール build_skill.py 自体の版)。タグが焼き込まれた INSTALL.md / setup script は canary 漏洩対策で削除する運用のため、受験 LLM が読める版情報は converter_version だけになり、誤認は必然だった。converter の版とスキルの版という**2 つの異なるバージョン空間があるのに、片方しか出力していなかった**設計欠落。

## 2. 修正

- `build_generator_header` / `build_generator_header_hash` (`#` 版) の両方に keyword-only 引数 `skill_version` を追加し、`converter_version` 行の直前に `skill_version: <metadata.yaml の version>` を出力 (全生成物 48 files に一貫)
- ヘッダ形式変更 = converter 挙動変更のため `CONVERTER_VERSION` 0.1.0 → **0.1.1**
- skill は **0.1.3** として再リリース (metadata.yaml)
- テスト: ヘッダ 2 変種それぞれに skill_version の存在 + converter_version 直前という順序のアサーション追加 (844 → 846)

## 3. 検証

- 846 passed, 3 skipped。digest `a9597890ff883282` → `8297056c361259ee`、py -3.10 / 3.13 決定論一致
- 既知の別件: `test_no_false_positive_timeout_when_child_exits_near_deadline` (timing 依存の subprocess supervisor テスト) が full run 1 回目のみ fail、単独 / 再 run では green — 本変更と無関係の既存 flaky として記録 (5.e or backlog で再現条件を見る)

## 4. 教訓

「生成物に何のバージョンを刻むか」は配布物設計の一部。多層のバージョン (skill / converter / build input digest) を持つシステムでは、**利用側が最初に知りたい版 (成果物自身の版) を先頭に置く**。canary の運用 (INSTALL.md 削除) のような下流の取り回しで消えない場所 (SKILL.md ヘッダ) に置くこと。
