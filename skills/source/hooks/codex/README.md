# qgb skill hook for Codex CLI (任意、Windows native PowerShell)

Phase 5 prejournal v4 §3.5 trigger / hook 戦略の **(γ) agent 別 hook** 実装。利用者が **opt-in** で設定する hook テンプレ。Codex CLI の harness レベル機構で qgb skill の trigger 発火を補強する。

## 概要

`UserPromptSubmit` イベント発火時、`scripts/check-relevance.ps1` が stdin から Codex が渡す JSON envelope を受け取り、`.prompt` フィールドに qgb 関連キーワード (`qgb` / `REQ-XXX-NNN` / `gate.json` / `ALLOW` / `DENY` / `NOT_READY` / 「契約段階」 / 「品質ゲート」) が含まれるかを正規表現判定する。**match した場合のみ** plain text nudge を stdout に出す (Codex は match 時の stdout を当該 prompt の追加 context として注入する)。

非 match → stdout 空 + exit 0、stdin 空 → 同。

### なぜ script を内側で正規表現判定するか

Codex CLI の `UserPromptSubmit` event は **hook config 階層の `matcher` フィールドを silently 無視**する (公式 docs: https://developers.openai.com/codex 参照)。`hooks.example.json` の hook 階層に `matcher` を書いても prompt 本文での filtering にはならない。よって script 内部で stdin JSON を読み、`.prompt` を regex 照合する形を採る。

## acceptance (4 原則、Phase 5 v4 / Codex r0 code fix #3 反映)

### 1. opt-in (デフォルトは有効化されない)

- 本 hook は **自動配置されない**。利用者が以下「利用者向け簡易手順」を実行した場合のみ有効
- skill 本体 (`SKILL.md` + helpers) だけを `~/.agents/skills/qgb/` に置けば skill 機能はすべて使える、本 hook がなくても動作する
- 本 hook は trigger 発火率を上げる「補強策」であり、必須ではない

### 2. dry-run (有効化前に script を直接動かして「何が起こるか」確認できる)

#### 2.1 match ケース (qgb 関連 prompt)

```powershell
'{"prompt":"please scaffold REQ-APP-001"}' | powershell -ExecutionPolicy Bypass -NoProfile -File "<absolute path to scripts/check-relevance.ps1>"
```

期待出力 (plain text 1 行):

```text
qgb skill may be relevant for this prompt. Consider loading the qgb skill (~/.agents/skills/qgb/ or .agents/skills/qgb/) if it is not yet active. ...
```

#### 2.2 non-match ケース (qgb 無関係 prompt)

```powershell
'{"prompt":"weather today"}' | powershell -ExecutionPolicy Bypass -NoProfile -File "<absolute path to scripts/check-relevance.ps1>"
```

期待出力: 空 (stdout なし、exit 0)

#### 2.3 stdin 空ケース (誤起動)

```powershell
'' | powershell -ExecutionPolicy Bypass -NoProfile -File "<absolute path to scripts/check-relevance.ps1>"
```

期待出力: 空 (stdout なし、exit 0)

これら 3 ケースが期待通りなら、hook を有効化しても prompt 提出を block する事故は起きない (script は常に exit 0 を返す設計)。

### 3. validate (設定が壊れていないことを確認できる)

merge 後、以下で検証:

1. **JSON parse 検証**:

   ```powershell
   python -c "import json; json.load(open('<absolute path to your merged hooks.json>', encoding='utf-8')); print('valid')"
   ```

2. **Codex CLI の `/hooks` コマンドで hook の登録状態を確認** (公式機能、source / trust / enable 状態が表示される):

   ```text
   /hooks
   ```

   登録された `UserPromptSubmit` hook が一覧に出ること、source が `~/.codex/hooks.json` 等の期待 path であること、trust が許可済であることを確認

3. **動作確認**: Codex CLI を起動して qgb 関連 prompt (例: `REQ-APP-001 の段階設計をして`) を投げ、Codex が qgb skill を起動するか観察

### 4. 非破壊 (既存 `hooks.json` を破壊しない)

`hooks.example.json` を **`~/.codex/hooks.json` に上書きコピーしてはいけない**。以下のように **merge** する (詳細手順は次節)。

### Codex 固有: `hooks.json` と `[hooks]` table の重複回避

Codex CLI は `~/.codex/hooks.json` か `~/.codex/config.toml` の `[hooks]` table のどちらかで hook を設定できる。**両方に同時設定すると warn が出る**ため、片方に統一する:

- `hooks.json` を採用する場合: `config.toml` の `[hooks]` table は空にする
- `config.toml [hooks]` を採用する場合: 本テンプレを TOML 表現に変換 (utility script は Phase 5 dogfooding 中に提供判断)

## 利用者向け簡易手順 (Phase 5 install ガイドで使用予定)

```powershell
# 1. バックアップ (Windows PowerShell)
Copy-Item -Path "$env:USERPROFILE\.codex\hooks.json" -Destination "$env:USERPROFILE\.codex\hooks.json.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"

# 2. script を skill ディレクトリへコピー (skill 本体 install と同時に実施)
#    例: ~/.agents/skills/qgb/hooks/codex/scripts/check-relevance.ps1 へ
#    (skill 配布物の構造に従う、Phase 5 完結時の release ノートで明示)

# 3. hooks.example.json の {{QGB_SCRIPT_PATH}} placeholder を上記 script の絶対 path に置換
#    (Editor で手動置換 or PowerShell スクリプトで自動置換)
#    例: "C:\\Users\\<you>\\.agents\\skills\\qgb\\hooks\\codex\\scripts\\check-relevance.ps1"
#    (JSON 内なのでバックスラッシュは "\\" で escape)

# 4. 既存 hooks.json の hooks.UserPromptSubmit 配列に hooks.example.json の hook entry 1 件を append
#    (Edit tool または Editor で JSON merge、既存 hook の他イベントは変更しない)
#    既に同等 hook が存在する場合は衝突として手動 review

# 5. JSON parse 検証
python -c "import json; json.load(open('$env:USERPROFILE/.codex/hooks.json', encoding='utf-8')); print('valid')"

# 6. Codex CLI を起動して /hooks で登録確認 + qgb 関連 prompt で動作確認
```

## アンチパターン (やってはいけないこと)

1. **`~/.codex/hooks.json` を `hooks.example.json` で完全置換**: 既存 hook がすべて消える。**非破壊原則違反**
2. **`~/.codex/hooks.json` と `~/.codex/config.toml` の `[hooks]` table に同時設定**: warn が出る、運用混乱
3. **`{{QGB_SCRIPT_PATH}}` placeholder を置換せずに登録**: hook は match 時に PowerShell を起動できず error、ただし script 自体は exit 0 設計のため prompt 提出は block されない (warn が `/hooks` 表示で出る)
4. **`scripts/check-relevance.ps1` の `$Pattern` を `.*` 等の過剰一般に拡張**: 全 prompt で nudge が発火、token cost 爆発、Codex のレスポンスに qgb 関連でない context が混ざる
5. **hook の script を qgb 本体の機械検査 (gate.json への ALLOW 書き込み等) に拡張**: hook は **advisory 補強**、ALLOW 判定は qgb 本体 + 機械検査が決める (philosophy P6)
6. **複数 source (`~/.codex/hooks.json` と `<repo>/.codex/hooks.json` 両方) で同 hook を重複設定**: hook が二重発火、token 倍消費、script が 2 回起動
7. **本 hook を「qgb skill 起動の必要条件」として利用者に説明**: hook なしでも skill は trigger 表で動作する
8. **`scripts/check-relevance.ps1` を編集して日本語コメント / string literal を追加**: PowerShell 5 (Windows 標準) は BOM なし `.ps1` の日本語を cp932 として誤読し parse error になる。**script は pure ASCII を維持**し、JP keyword は Unicode escape (`[char]0x<codepoint>`) で構築するパターンを継承

## Codex CLI 固有の注意点 (5.b で実機検証予定)

`agent-codex.md` の `known_gaps` で記録した以下は 5.b の dogfooding 中に実機検証する想定:

- SKILL.md frontmatter の `allowed-tools` 相当の有無
- dynamic context injection (Claude Code の `!command` 相当) の有無
- AGENTS.md と Skills の優先関係 (両方ある場合)

これらの確認結果次第で、本 hook テンプレが Codex CLI 実装と整合するか追加調整が必要になる可能性がある。

## 関連

- `scripts/check-relevance.ps1` — script 本体 (pure ASCII + Unicode escape で JP keyword 構築、PowerShell 5/7 両対応)
- `development/docs/skill-converter/agent-codex.md` — Codex CLI skill / hook 仕様
- `development/docs/journal/phase5-prejournal.md` v4 §3.5 — trigger / hook 戦略 (α) + (γ)
- `skills/source/body.md` §2 — trigger 表 (α 層、hook と独立に機能)
- `skills/source/hooks/claude-code/` — Claude Code 用の対応物
