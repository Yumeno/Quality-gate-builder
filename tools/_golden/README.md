# tools/_golden/ -- build_skill.py の golden fixture

`tools/build_skill.py` (Phase 5 skill converter) の出力が変わっていないことを byte 単位で
検証するための期待生成物一式。`tests/test_build_skill_golden.py` がこのディレクトリと
実際の build 出力を比較する。

## layout

```
tools/_golden/
  README.md          <- このファイル (regen 対象外)
  claude/
    full/             <- SKILL.md + INSTALL.md + hooks/ + lint/ (8 files)
    split/            <- SKILL.md + helper files + INSTALL.md + hooks/ + lint/ (12 files)
  codex/
    full/             (8 files)
    split/            (12 files)
```

配置は `development/docs/skill-converter/acceptance-matrix.md` の表記 `<agent>/<mode>` に
合わせている。**`tools/build_skill.py --dist-dir` の実際の出力は `<mode>/<agent>` 順**
(`dist/skills/full/claude/` 等) なので、golden と build 出力は directory 階層が転置の
関係にある。この対応付けは `tools/regen_golden.py` と `tests/test_build_skill_golden.py`
の両方に実装済みで、利用者が手で気にする必要はない。

## 再生成手順

```powershell
python tools/regen_golden.py
```

- `SOURCE_DATE_EPOCH` が環境変数に設定されている場合は exit code 2 で拒否する
  (golden は SOURCE_DATE_EPOCH **未設定系統のみ**を対象とする。
  `development/docs/skill-converter/acceptance-matrix.md` 「deterministic build 契約」参照)。
- `claude/` `codex/` の下だけを削除して再生成する。このファイル (`README.md`) は
  wipe 対象に含まれない。
- 生成後、ファイル数サマリを標準出力に表示する (現在: 合計 40 files)。

## 更新規律

golden は **build_input_digest の 8 カテゴリいずれかが変わったら、同一 commit 内で
再生成 + commit しなければならない**:

1. `skills/source/metadata.yaml`
2. `skills/source/metadata.schema.json`
3. `source_files` (`skills/source/body.md` 等、authored source)
4. 同梱 hook files (`skills/source/hooks/**`)
5. 同梱 lint files (`skills/source/lint/**`)
6. agent docs (`development/docs/skill-converter/agent-*.md`)
7. `tools/build_skill.py` 自身
8. `SOURCE_DATE_EPOCH` の契約 (この変数の扱い方を変えるコード変更)

上記 8 カテゴリ以外の変更 (journal 追記、テストコード変更、CI 設定変更等) は
golden に影響しない。

## 備考

- `tools/regen_golden.py` はビルドの digest 入力ではない (`build_input_digest` の
  8 カテゴリに含まれない)。golden の生成レイアウトを変えるだけで build 内容には
  影響しないため。
