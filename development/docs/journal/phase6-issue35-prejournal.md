# Issue #35 prejournal: Windows の .cmd shim と command not found

- 作成: 2026-10-22 / 仕様: [Issue #35](https://github.com/Yumeno/Quality-gate-builder/issues/35)
- 由来: Issue #33 (PR #34) の動作確認で、`examples/node-cli-vitest` の S1 (`["npx", "vitest", "run"]`) が Windows で `command not found: [WinError 2]` になることが判明。PR #34 で example は `["node", "node_modules/vitest/vitest.mjs", "run"]` に変更済み

## 事実

- Windows の `npx` / `npm` / `yarn` / `pnpm` 等は `.cmd` shim (+ `.ps1`、POSIX 用の拡張子なし sh script)
- qgb の command runner は `shell=False` で `CreateProcess` を呼ぶ。拡張子なしの argv[0] には `.exe` しか補われず、PATHEXT 解決は起きない
- PowerShell / cmd どちらから qgb を起動しても同じ (シェルを経由しないため)

## 方針 (Codex セカンドオピニオン済み、user 合意)

**A (qgb 本体で argv[0] を PATHEXT 解決して起動) は採らない**。理由:

- 「contract の argv をそのまま実行する」という runner の責務が「OS ごとに argv[0] を補完・変換する」へ拡張される (P9、adapter 撤回方針との不整合)
- `.cmd` に解決されると起動経路が cmd.exe 経由に変わる
- 探索順が PATHEXT / cwd / Python version / `NoDefaultCurrentDirectoryInExePath` に依存し、untrusted repo 内の同名 shim を拾う PATH hijacking の監査面が悪化する
- NF-004 (Windows first-class) は「曖昧な command を暗黙補正する」ではなく「example・skill・診断が Windows で正しく導く」と解釈する

**採るもの**:

- **B2 (skill 文言)**: §6.x command contract 生成 protocol の argv 生成 step と Node.js checklist に、Windows の shim 注意と推奨順 (① OS 共通の実行ファイル + CLI エントリ ② Windows 専用 contract なら `.cmd` 明示 ③ 拡張子なし shim 名は避ける) を追加。version lockstep 0.1.8
- **B3 (qgb 本体、診断のみ)**: `FileNotFoundError` 時に、Windows で argv[0] が bare name (ディレクトリ成分なし・拡張子なし) かつ PATH 上に `<name>.cmd` / `<name>.bat` が存在する場合だけ、stage log に `hint:` 行を 1 行出す

## B3 の固定事項

- **判定は変えない**: `result: failed (command not found)`、exit_code=None、gate の DENY はそのまま。gate.json schema / `stages[].reason` enum も変えない (log_text のみ)
- **起動しない・解決しない**: hint は存在の事実を伝えるだけ。qgb が `.cmd` を起動する経路は作らない
- **探索は自前で決定論的に**: `shutil.which` は使わない (cwd 探索・PATHEXT・Python version 依存を持ち込まないため)。子プロセスに渡す env の `PATH` を `os.pathsep` で分割し、各ディレクトリで `<name>.cmd` / `<name>.bat` の存在のみ確認。最初の一致を報告
- **例外を漏らさない**: 探索中の `OSError` 等は握りつぶして hint なし (診断が本来の failed 経路を壊さない)
- **POSIX では何もしない**
- log の行順: `command not found: ...` → `hint: ...` → `result: failed (command not found)` (result 行が最後という既存慣行を維持)

## 範囲外

- skill lint (`check-command-contract`) で bare shim 名を検出する案 — 機械検査として有効だが、本 Issue は文言 + 診断に限定。必要なら別 Issue
- examples の実行検証 → Issue #36
