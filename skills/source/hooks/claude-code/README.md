# qgb skill hook for Claude Code (任意)

Phase 5 prejournal v4 §3.5 trigger / hook 戦略の **(γ) agent 別 hook** 実装。利用者が **opt-in** で設定する hook テンプレ。Claude Code の harness レベル機構で qgb skill の trigger 発火を補強する。

## 概要

`settings.example.json` は **`UserPromptSubmit` イベント**で利用者の prompt に qgb 関連キーワード (`qgb` / `REQ-XXX-NNN` / `gate.json` / `ALLOW` / `DENY` / `NOT_READY` / `契約段階` / `品質ゲート`) が含まれたとき、Claude に「qgb skill が関連する可能性」を `additionalContext` で示唆する hook。

hook 自体は **stdout JSON で nudge を返すだけ** — qgb skill 本体の起動有無、何をするかは Claude の判断に委ねる (skill の trigger 表が最終判断者)。

## acceptance (4 原則、Phase 5 v4 / Codex r0 code fix #3 反映)

### 1. opt-in (デフォルトは有効化されない)

- 本 hook は **自動配置されない**。利用者が install ガイドの「Claude Code hook を有効化する (任意)」セクションを読んで、明示的に merge した場合のみ有効
- skill 本体 (`SKILL.md` + helpers) だけを `~/.claude/skills/qgb/` に置けば skill 機能はすべて使える、本 hook がなくても動作する
- 本 hook は trigger 発火率を上げる「補強策」であり、必須ではない

### 2. dry-run (有効化前に「何が起こるか」を確認できる)

有効化前に以下を確認できる:

1. `settings.example.json` を読んで matcher / command を理解
2. matcher 正規表現を実 prompt サンプルで試す (例: `echo "qgb 入れて" | grep -E '<matcher 正規表現>'` で match 確認)
3. command を直接実行して stdout を観察:

   ```bash
   echo '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"qgb skill may be relevant..."}}'
   ```

   → JSON が出力されるだけ、副作用なし

### 3. validate (設定が壊れていないことを確認できる)

merge 後、以下で検証:

1. `python -c "import json; json.load(open('<path to your merged settings.json>'))"` で JSON parse 成功確認
2. Claude Code の `claude config validate` または同等のコマンドがあれば使用 (公式 docs で確認)
3. 動作確認: Claude Code を起動して qgb 関連 prompt (例: `REQ-APP-001 の段階設計をして`) を投げ、Claude が qgb skill を起動するか観察

### 4. 非破壊 (既存 `settings.json` を破壊しない)

`settings.example.json` を **`~/.claude/settings.json` に上書きコピーしてはいけない**。以下のように **merge** する:

1. 既存の `~/.claude/settings.json` をバックアップ:

   ```bash
   cp ~/.claude/settings.json ~/.claude/settings.json.bak.$(date +%Y%m%d-%H%M%S)
   ```

2. `settings.example.json` の **`hooks.UserPromptSubmit` エントリだけ**を既存の `hooks.UserPromptSubmit` 配列に append (既存に同 matcher の entry がなければそのまま追加、あれば衝突として手動 review)
3. JSON top-level の `$comment_top` キーは Claude Code が無視するので残しても害はないが、merge 時は省略して構わない
4. 既存 hook の他のイベント (`SessionStart`, `PreToolUse` 等) は変更しない

## 利用者向け簡易手順 (Phase 5 install ガイドで使用予定)

```text
# 1. バックアップ
cp ~/.claude/settings.json ~/.claude/settings.json.bak.20260628-160000

# 2. 既存 settings の hooks.UserPromptSubmit セクションを Read
#    なければ空配列として用意

# 3. settings.example.json の hooks.UserPromptSubmit エントリ 1 件を手動 append
#    (Edit tool または vi/code で JSON merge)

# 4. JSON parse 検証
python -c "import json; json.load(open('~/.claude/settings.json'))"

# 5. Claude Code 起動して qgb 関連 prompt で skill が自動起動することを確認
```

## アンチパターン (やってはいけないこと)

1. **`~/.claude/settings.json` を `settings.example.json` で完全置換**: 既存 hook / setting がすべて消える。**非破壊原則違反**
2. **matcher をすべての prompt にマッチする `.*` に拡張**: token cost が爆発、Claude のレスポンスに qgb 関連でない context が混ざる、user 体験悪化
3. **hook の command を qgb 本体の機械検査 (gate.json への ALLOW 書き込み等) に使う**: hook は **advisory 補強**、ALLOW 判定は qgb 本体 + 機械検査が決める (philosophy P6)
4. **複数 source (`~/.claude/settings.json` と `.claude/settings.json` 両方) で同 matcher を重複設定**: hook が二重発火、token 倍消費。一つに統合
5. **本 hook を「qgb skill 起動の必要条件」として利用者に説明**: hook なしでも skill は trigger 表で動作する。hook は trigger 発火率の補強

## 将来の拡張余地 (Phase 5+ で判断)

- `PreToolUse` (matcher: `Bash(python -m qgb *)`): qgb CLI 呼び出し前に project-context 等の準備
- `PostToolUse` (matcher: `Bash(python -m qgb *)`): qgb CLI 結果を解析して context 注入
- `SessionStart`: qgb 関連 dir (`.quality-system/`) が working dir 配下にある場合、skill を初期 active 化

これらは Phase 5 dogfooding (5.d / 5.e) の結果次第で `settings.example.json` に追加判断。

## 関連

- `development/docs/skill-converter/agent-claude.md` — Claude Code skill / hook 仕様
- `development/docs/journal/phase5-prejournal.md` v4 §3.5 — trigger / hook 戦略 (α) + (γ)
- `skills/source/body.md` §2 — trigger 表 (α 層、hook と独立に機能)
- `skills/source/hooks/codex/` — Codex CLI 用の対応物
