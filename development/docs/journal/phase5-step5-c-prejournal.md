# Phase 5 Step 5.c Prejournal: release.yml (リリース直前まで)

- 作成日: 2026-07-04
- 作成者: Claude Fable 5 (指揮役。実装は sonnet subagent に委任)
- 前提: Step 5.b 完結 (`tools/build_skill.py` 本実装 + golden fixture)、Step 5.b-ci 完結 (`golden-integrity` job)
- 上位仕様: `development/docs/skill-converter/acceptance-matrix.md`「SOURCE_DATE_EPOCH と digest の関係」「利用者向け『どの commit で build されたか』」、`phase5-step5-b-prejournal.md` §3.3、F-019、C-008
- スコープ: 本 Step は **リリース直前まで**。実タグ push は user 決裁 (5.d 送り)。

## 決定事項

1. **タグパターンは `skill-v*`** (例: `skill-v0.1.0`)。plain `v*` は将来 qgb-core 本体 / PyPI リリースのために予約する。skill 成果物のバージョンは `metadata.yaml` の version フィールドで独立に管理され、qgb 本体のバージョニングと結合しない。

2. **release build の検証系統は 2 本立て**:
   - (a) `SOURCE_DATE_EPOCH` unset で build → 委員済み `tools/_golden/` と byte 一致 (= release はレビュー済み golden lineage に紐づく)。実装は手組み diff ではなく `pytest tests/test_build_skill_golden.py -q` をそのまま呼ぶ (5.b で確立済みの比較ロジックの再利用、二重実装を避ける)。
   - (b) release build 本体は `SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)` を設定し **2 回 build** → byte 一致 (self-check、5.b prejournal §3.3 が予告した「release lineage は golden 二重保守せず自己検証で担保する」の実装)。

3. **成果物は 4 zip、`qgb-skill-<ref>-<agent>-<mode>.zip`** (各 zip はそのセルのファイルを zip ルートに格納)。commit hash は成果物に埋め込まない — acceptance-matrix の規約通り、hash は release notes 側 (人間可読 metadata) に置く。

4. **`workflow_dispatch` は dry-run モード (デフォルト)**。GitHub Release 作成以外の全工程 (build + 両系統検証 + zip 生成 + 内容確認) を実行し、Release 作成のみスキップする。タグ push だけが実 release 経路。これにより実タグを切らずに CI 全体を検証できる (5.c 完結条件そのもの)。dry-run 用の追加 input は不要 — dispatch されたこと自体が dry-run の意味を持つ (tag push との trigger 種別で分岐)。

5. **permissions は job 単位で分離**: `build` job は `contents: read`、`release` job のみ `contents: write` (release job は tag push 時のみ実行、dry-run では走らない)。third-party action は追加しない (SECURITY.md の SHA pin 方針を維持。`actions/checkout` + `actions/setup-python` のみ、test.yml と同一 SHA pin)。`gh` CLI は runner にプリインストール済みで `GITHUB_TOKEN` を自動的に使う。

6. **2 job 構成 + release job は "rebuild"** (artifact 転送ではなく):
   `build` job (検証ゲート: 両系統確認 + zip 生成 + `sha256sum` ログ出力) と `release` job (`needs: build` + tag 条件 + rebuild + `gh release create`) を分離。job 間の受け渡しに `actions/upload-artifact` / `download-artifact` を使わない理由は「新規 action pin を増やしたくない」(third-party action surface を test.yml から変えない) だけでなく、**build の決定性そのものをドッグフーディングする** — 同じコマンド列を再実行すれば同じ zip バイト列が出るという主張を、実際に 2 回走らせて示す方が「artifact を右から左に運ぶ」より本 project の哲学 (P7 再現可能証跡) に合う。コストは release job 内でのビルド再実行 (数分) のみ。
   - dry-run では artifact 転送も不要 (Release を作らないため): 検証済みの zip は `ls -la` + `sha256sum` でログに残すだけで十分 (5.c acceptance は「CI が green になること」であり、成果物のダウンロード可能性は要求しない)。

## 5.c 完結条件

`workflow_dispatch` による dry-run 実行が CI 上で green になること: build (両系統検証 + zip 生成 + `sha256sum` ログ) が成功し、Release 作成ステップがスキップされる。実 release (タグ push 後の `gh release create` 実行) は 5.d で扱う — 本 Step はそこまで到達しない。

## ローカル検証 (push せずに可能な範囲)

- YAML 構文チェック (`yaml.safe_load`) — release.yml / test.yml 両方。
- lineage (b) のローカル再現: `SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)` で 2 回 build → `diff -r` で一致確認、生成 `SKILL.md` に `build_date_utc` 行が現れることを grep で確認。
- zip 命名ループのローカル再現 (4 zip 生成)。
- `pytest tests/test_build_skill_golden.py -q` (lineage (a) 相当) の green 確認。

いずれも本 prejournal 作成と同じ turn で実行し、結果を completion 記録側に残す。
