# design-notes (examples/go-cli)

このノートは `examples/go-cli/` がなぜ現在の 3 段階構成になっているかを記録する。

## 対象系の特徴

Go の小さな CLI ツール。`go test` と `go vet` がビルトインのテスト・
静的解析ツールとして機能する。外部依存はゼロ (stdlib のみ)。

- **実装の正しさ** — `go test ./...` が通ること。
- **静的解析** — `go vet ./...` が通ること (型ミス・未使用変数等の検知)。
- **利用者向け文書** — README.md に Usage が記載されていること。

## 段階数の決定根拠

stage-design.md §9 の推奨レンジ **3〜7** の下限。Go は `go test` と
`go vet` が言語標準なので、この 2 つを分けるのが自然。文書品質を独立
stage にして 3 段階。

## 採用した段階と理由

| stage | verification_type | 単一責務 | なぜ |
|---|---|---|---|
| S1 | `command` | `go test ./...` が exit 0 | テストの回帰検知 |
| S2 | `command` | `go vet ./...` が exit 0 | 静的解析。テストが通っても vet が警告する問題を別軸で検知 |
| S3 | `substring_match` | README に "Usage" を含む | 利用者 onboarding の独立保証 |

S1 と S2 を分けるのは Go エコシステムの慣習に合致する: `go test` は
テストコードの実行、`go vet` は静的解析で、別の種類の問題を検知する。

## 採用しなかった段階と理由

- **go build** — ビルドが通ることの確認。`go test` が暗黙にコンパイルを
  含むので S1 でカバーされる。独立 stage にするとビルド成功の重複検査になる。
- **golangci-lint** — サードパーティ lint aggregator。Phase 1 は
  言語標準ツールのみで構成する方針。
- **go mod tidy / verify** — 依存の整合性検査。本 example は外部依存ゼロ
  なので検査対象がない。

## 思想憲章のどの項目が特に効くか

- **P9 (単一責任)** — test と vet の分離。
- **NF-010 (依存最小化)** — Go の標準ツールチェーンのみで完結。
- **P7 (再現可能証跡)** — command の exit code が log に記録される。

## 段階間の依存関係

```
S1 (go test)     S2 (go vet)     S3 (substring_match)
   独立            独立             独立
```

3 stage すべて独立。vet はテスト実行に依存しない。

## 既知の限界

- Go がインストールされていない環境では S1/S2 が command not found で
  DENY になる (qgb は Go のインストールを管理しない)。
- クロスプラットフォームビルド (`GOOS=linux` 等) はテストしていない。
- ベンチマーク (`go test -bench=.`) は scope 外。
