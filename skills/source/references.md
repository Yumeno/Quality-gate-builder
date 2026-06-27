# qgb 参照文書 (split モード helper、正本は body.md §7)

このファイルは Phase 5 Step 5.a-2-2 (A1' 6 段階手順) の **中間状態**。

A1' (skills/source/ は body.md 単一正本、helper はすべて include marker 経由) への移行過渡。最終的にはこのファイル自体は削除され、`dist/skills/split/{claude,codex}/references.md` は body.md §7 の include marker (`<!-- split:helper_start references.md -->` ... `<!-- split:helper_end -->`) から converter (`tools/build_skill.py`、5.b で実装) が生成する。

**内容の正本は `skills/source/body.md` §7 (参照集) を参照すること**。本ファイルは段階 5 で物理削除予定。

参照: `development/docs/journal/phase5-step5-a-2-progress.md` §7 (A1' 6 段階手順)
