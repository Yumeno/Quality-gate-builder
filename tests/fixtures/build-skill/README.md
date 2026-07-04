# build-skill フィクスチャ一覧

`tests/test_build_skill.py` が使うテスト用フィクスチャ。各ディレクトリは `metadata.yaml` と `body.md` を含む。
スキーマは常に実物の `skills/source/metadata.schema.json` を参照し、フィクスチャ内にコピーしない。

## valid-minimal

正常系フィクスチャ。HTML ブロックコメント内のマーカー例示を除外しつつ、2 つの helper block (`helper-a.md`, `helper-b.md`) を正しく parse できることを確認する。コメント状態は行単位で追跡され「`-->` を含む最初の行」で閉じるため、ブロックコメントが隠せる行頭マーカー形の例示は 1 行だけ (その行自身の `-->` がコメントを閉じる)。これは実 HTML のコメント終端規則および body.md 冒頭コメント (例示行が行頭にない) と整合する。行頭に空白を持つマーカー形の行はコメント外でもマーカーにならないことも同時に検証する。

## duplicate-marker

`same-name.md` という同一名のマーカーを 2 か所定義したケース。重複名エラー (BuildError) を発生させる。

## unclosed-marker

`unclosed.md` のスタートマーカーに対応するエンドマーカーが存在しない。未閉鎖マーカーエラー (BuildError) を発生させる。

## nested-marker

外側の marker block が閉じられる前に内側の start marker が現れるケース。入れ子禁止ルール違反として BuildError を発生させる。

## path-traversal

`../evil.md` という `..` セグメントを含むマーカー名。パス安全性チェックに引っかかり BuildError を発生させる。

## case-collision

`Workflow.md` と `workflow.md` のように大文字・小文字だけが異なる名前を 2 回定義したケース。NFC + casefold 後の重複として BuildError を発生させる。

## source-output-collision

`body.md` という名前 (= `source_files` に列挙されているファイル) をマーカー名に使ったケース。ソース/出力衝突として BuildError を発生させる。

## empty-helper

スタートマーカーとエンドマーカーの間に 1 行もコンテンツがない空の helper block。空ヘルパーエラーとして BuildError を発生させる。
