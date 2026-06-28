# qgb skill hook for Codex CLI (任意)

Phase 5 prejournal v4 §3.5 trigger / hook 戦略の **(γ) agent 別 hook** 実装。利用者が **opt-in** で設定する hook テンプレ。Codex CLI の harness レベル機構で qgb skill の trigger 発火を補強する。

## 概要

`hooks.example.json` は **`UserPromptSubmit` イベント**で利用者の prompt に qgb 関連キーワード (`qgb` / `REQ-XXX-NNN` / `gate.json` / `ALLOW` / `DENY` / `NOT_READY` / `契約段階` / `品質ゲート`) が含まれたとき、stdout でナッジを出す hook。Codex は hook の stdout を該当 prompt の追加 context として注入する想定。

hook 自体は **stdout で nudge を返すだけ** — qgb skill 本体の起動有無、何をするかは Codex の判断に委ねる (skill の trigger 表が最終判断者)。

## acceptance (4 原則、Phase 5 v4 / Codex r0 code fix #3 反映)

### 1. opt-in (デフォルトは有効化されない)

- 本 hook は **自動配置されない**。利用者が install ガイドの「Codex CLI hook を有効化する (任意)」セクションを読んで、明示的に merge した場合のみ有効
- skill 本体 (`SKILL.md` + helpers) だけを `~/.agents/skills/qgb/` に置けば skill 機能はすべて使える、本 hook がなくても動作する

### 2. dry-run (有効化前に「何が起こるか」を確認できる)

有効化前に以下を確認:

1. `hooks.example.json` を読んで matcher / command を理解
2. matcher 正規表現を実 prompt サンプルで試す
3. command を直接実行して stdout を観察:

   ```bash
   echo qgb skill may be relevant for this prompt. Consider loading the qgb skill if it is not yet active.
   ```

   → stdout に nudge メッセージが出力されるだけ、副作用なし

### 3. validate (設定が壊れていないことを確認できる)

merge 後、以下で検証:

1. `python -c "import json; json.load(open('<path to your merged hooks.json>'))"` で JSON parse 成功確認
2. Codex CLI の `codex config validate` または同等のコマンドがあれば使用 (公式 docs で確認、5.b で実機検証予定)
3. 動作確認: Codex CLI を起動して qgb 関連 prompt を投げ、Codex が qgb skill を起動するか観察

### 4. 非破壊 (既存 `hooks.json` を破壊しない)

`hooks.example.json` を **`~/.codex/hooks.json` に上書きコピーしてはいけない**。以下のように **merge** する:

1. 既存の `~/.codex/hooks.json` をバックアップ:

   ```bash
   cp ~/.codex/hooks.json ~/.codex/hooks.json.bak.$(date +%Y%m%d-%H%M%S)
   ```

2. `hooks.example.json` の **`hooks.UserPromptSubmit` エントリだけ**を既存の `hooks.UserPromptSubmit` 配列に append (既存に同 matcher の entry がなければそのまま追加、あれば衝突として手動 review)
3. `$comment_top` キーは Codex が無視するので残しても害はない (merge 時は省略して構わない)
4. 既存 hook の他のイベント (`SessionStart`, `PreToolUse` 等) は変更しない

### Codex 固有: `hooks.json` と `[hooks]` table の重複回避

Codex CLI は `~/.codex/hooks.json` か `~/.codex/config.toml` の `[hooks]` table のどちらかで hook を設定できる。**両方に同時設定すると warn が出る**ため、片方に統一する:

- `hooks.json` を採用する場合: `config.toml` の `[hooks]` table は空にする
- `config.toml [hooks]` を採用する場合: 本テンプレを TOML 表現に変換 (utility script は Phase 5 dogfooding 中に提供判断)

## 利用者向け簡易手順 (Phase 5 install ガイドで使用予定)

```text
# 1. バックアップ
cp ~/.codex/hooks.json ~/.codex/hooks.json.bak.20260628-160000

# 2. 既存 hooks の hooks.UserPromptSubmit セクションを Read
#    なければ空配列として用意

# 3. hooks.example.json の hooks.UserPromptSubmit エントリ 1 件を手動 append
#    (Edit tool または vi/code で JSON merge)

# 4. JSON parse 検証
python -c "import json; json.load(open('~/.codex/hooks.json'))"

# 5. Codex CLI 起動して qgb 関連 prompt で skill が自動起動することを確認
```

## アンチパターン (やってはいけないこと)

1. **`~/.codex/hooks.json` を `hooks.example.json` で完全置換**: 既存 hook がすべて消える。**非破壊原則違反**
2. **`~/.codex/hooks.json` と `~/.codex/config.toml` の `[hooks]` table に同時設定**: warn が出る、運用混乱
3. **matcher をすべての prompt にマッチする `.*` に拡張**: token cost が爆発、Codex のレスポンスに qgb 関連でない context が混ざる
4. **hook の command を qgb 本体の機械検査 (gate.json への ALLOW 書き込み等) に使う**: hook は **advisory 補強**、ALLOW 判定は qgb 本体 + 機械検査が決める (philosophy P6)
5. **複数 source (`~/.codex/hooks.json` と `<repo>/.codex/hooks.json` 両方) で同 matcher を重複設定**: hook が二重発火、token 倍消費
6. **本 hook を「qgb skill 起動の必要条件」として利用者に説明**: hook なしでも skill は trigger 表で動作する

## Codex CLI 固有の注意点 (5.b で実機検証予定)

`agent-codex.md` の `known_gaps` で記録した以下は 5.b の dogfooding 中に実機検証する想定:

- SKILL.md frontmatter の `allowed-tools` 相当の有無
- dynamic context injection (Claude Code の `!command` 相当) の有無
- AGENTS.md と Skills の優先関係 (両方ある場合)

これらの確認結果次第で、本 hook テンプレが Codex CLI 実装と整合するか追加調整が必要になる可能性がある。

## 関連

- `development/docs/skill-converter/agent-codex.md` — Codex CLI skill / hook 仕様
- `development/docs/journal/phase5-prejournal.md` v4 §3.5 — trigger / hook 戦略 (α) + (γ)
- `skills/source/body.md` §2 — trigger 表 (α 層、hook と独立に機能)
- `skills/source/hooks/claude-code/` — Claude Code 用の対応物
