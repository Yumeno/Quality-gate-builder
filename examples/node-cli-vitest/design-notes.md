# design-notes (examples/node-cli-vitest)

このノートは `examples/node-cli-vitest/` がなぜ現在の 3 段階構成になっているかを記録する。

## 対象系の特徴

Node.js の小さな CLI ツール + vitest テスト。`npm install` 後に
`npx vitest run` でテストが走る構成。Next.js ではなく Node CLI を選んだ
理由: Next.js は `npm install` が重い (数百 MB) ため、Phase 1 の軽量
example に不適。Node CLI + vitest なら依存が小さく、qgb の多言語対応
能力を示すのに十分。

- **実装の正しさ** — vitest でテストが通ること。
- **エントリポイントの存在** — `src/index.js` が存在すること。
- **利用者向け文書** — README.md に Usage が記載されていること。

## 段階数の決定根拠

stage-design.md §9 の推奨レンジ **3〜7** の下限。python-fastapi-pytest
と同じ構成 (command + file_exists + substring_match) で、言語が違うだけで
qgb の quality-system 構造は同じであることを示す。

## 採用した段階と理由

| stage | verification_type | 単一責務 | なぜ |
|---|---|---|---|
| S1 | `command` | `npx vitest run` が exit 0 | テスト回帰検知 |
| S2 | `file_exists` | `src/index.js` が存在 | エントリポイント保証。テストが import で動くのとファイル存在は別 |
| S3 | `substring_match` | README に "Usage" を含む | 利用者 onboarding |

## 採用しなかった段階と理由

- **ESLint** — サードパーティ lint。Phase 1 は外部ツール依存を増やさない。
- **TypeScript type-check** — 本 example は plain JS。TS 例は Phase 3。
- **npm audit** — 依存脆弱性。qgb は供給チェーン監査ツールではない。
- **Next.js build** — 計画段階で「Next.js は重い npm install を前提にしない」
  設計余地を検討した結果、Node CLI + vitest を選択。

## 思想憲章のどの項目が特に効くか

- **P9 (単一責任)** — test と file_exists の分離。
- **NF-010 (依存最小化)** — vitest 1 個のみ (devDependency)。
- **NF-004 (Windows first-class)** — npx / node は Windows でネイティブ動作。

## 段階間の依存関係

```
S1 (vitest)     S2 (file_exists)     S3 (substring_match)
   独立            独立                   独立
```

3 stage すべて独立。

## 既知の限界

- `npm install` が事前に必要 (node_modules 未作成だと S1 が失敗する)。
- ESM / CJS の混在問題は scope 外 (本 example は CJS)。
- vitest は Node.js 18+ を要求する。
