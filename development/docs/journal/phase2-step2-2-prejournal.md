# Phase 2 Step 2.2 着手前判断記録 (prejournal)

作成: 2026-06-05
状態: Step 2.2 (patch substrate) 着手前、Codex 計画レビュー受領後、思想憲章照合済、案 X 採用確定

このドキュメントは Step 2.2 の **着手前構造修正** を記録する。Phase 1 で確立した「計画 Codex 相談 → 着手前構造修正 → 実装 → 統合レビュー」サイクルの第 2 段階を Step 2.2 でも踏むため、本体実装に入る前に判断経緯を確定させる目的。

完結ジャーナル (`journal/phase2-step2-2.md`) は Step 2.2 完結時に別途作成し、実装内容 / 段 1〜5 レビュー / 補修 / 受け入れ条件達成を記録する。

---

## 1. Step 2.2 のシステム上の位置づけ

Phase 1 で完成した検証装置 (`qgb validate` / `validate-policy` / `run`) は「**読む側 = 壊れていないことを確認する側**」。Phase 2 で「**書く側**」を載せる:

```
Step 2.1 schema baseline       ← 検証の刃を強化 (Phase 2 全体の前提)
Step 2.2 patch substrate       ← 「書く」ための共通基盤 ★本ジャーナル★
Step 2.3 add-waiver/add-knowledge ← 業務 CLI、内部で patch を呼ぶ
Step 2.4 qgb check/dev         ← 書かずに検証 (patch を試すだけ)
Step 2.5 Pattern B (proposal/adopt) ← LLM 提案を patch に変換して当てる
```

Step 2.2 は **「user / LLM / 業務 CLI のいずれが書き換え提案を出してきても、validate-policy という関門を必ず通る蛇口」** の役割。Step 2.3 / 2.4 / 2.5 はすべてこの蛇口を通す前提で作られる。

### 想定 user × LLM フロー (Phase 2 完成後)

新しい REQ を 1 個追加するシナリオで蛇口がどこで握られるか:

| 段階 | 呼び出し元 | 何をする | 書き込むか |
|---|---|---|---|
| 段 1: user → Claude Code 課題提示 | (qgb 不関与) | LLM が context を読んで提案を考える | — |
| 段 2: Claude Code が proposal.patch.json を生成 | (qgb 不関与) | 構造化 JSON 提案 | — |
| 段 3: `qgb check --proposal-patch proposal.patch.json` (Step 2.4) | patch substrate (Step 2.2) | proposal を memory 適用 + validate-policy で安全性確認 | **書かない** (.qgb/tmp/ に揮発出力のみ) |
| 段 4: 修正ループ (check → 修正 → check → ALLOW) | patch substrate | 同上 | **書かない** |
| 段 5: `qgb design-stages adopt proposal.patch.json` (Step 2.5) | patch substrate | proposal を memory 適用 + validate-policy + atomic swap | **書く** (`.quality-system/` 配下) |
| 段 6: `qgb run REQ-API-005` (Phase 1 経路) | Phase 1 既存 | 通常実行 | gate.json 出力 |
| 段 7: `qgb add-waiver REQ-API-005 S6 --reason ...` (Step 2.3) | patch substrate | 単純な patch を memory 適用 + validate-policy + atomic swap | **書く** |

Step 2.2 の蛇口は **「書く前に必ず validate-policy を通す」** という共通契約を提供する。書く / 書かないの違いは呼び出し元 (2.3 / 2.4 / 2.5) が決めるが、**「memory で当てて validate-policy にかける」** ロジックは全部 Step 2.2 のもの。

---

## 2. Codex 計画レビュー結果 (2026-06-05、skill 経由)

context file: `codex_ctx_p2_step22_plan_20260605-075307.txt` (TEMP 揮発台帳)
経路: 当初は wrapper 直接呼び (`Bash powershell ... codex-wrapper.ps1`)、後に `/ask-codex-with-context` skill 経由に切り替え (Phase 2 規律)

### 18 指摘の優先度別

**着手前構造修正必須 (Major):**
1. JSON Patch の `add` の **配列 semantics** 明文化 (`/-` append、index 挿入、root path `""`)
2. JSON Pointer decode の **invalid escape** を必ず reject (`~2` や末尾 `~`)
3. `patch.schema.json` で op ごとの **required/forbidden** 厳密化 (`add`/`replace`/`test` に `value` required、`from` は Phase 2 では forbidden)
5. **apply 後 validation の対象が "target 単体" と "project 全体" で混ざる** リスク
6. **`validate_policy_preflight` が in-memory doc を受け取れるか** — Step 2.2 最大の確認事項
8. **`--force` は no-op flag になりがちなので削除推奨**
9. **`--dry-run` は skeleton でなく swap 直前まで完全実行する仕様** にする (Step 2.4 への基盤)
12. **`PatchError` に reason code を持たせる** (`invalid_patch_document` / `unsupported_op` / `invalid_pointer` 等)
13. **`qgb/core/json_pointer.py` に encode/decode を集約** (P9、Step 2.1 の `_json_pointer_escape` / `_to_pointer` も移動)
17. **`$ref allowlist` patch 経由 regression テスト** (Step 2.1 の価値が patch substrate 経由でも守られることを示す)

**テスト網羅追加 (Medium):**
14. `apply_patch(doc, patch)` 後の元 doc 不変を op 別にテスト (deepcopy だけでは保証不十分)
18. 完了条件 **20-25 件 → 30 件前後** (pointer escape / array bounds / `/-` append / contract $ref allowlist regression / dry-run / CLI absolute path reject 等)

**CLI 仕様化 (Medium):**
7. `qgb patch` の atomic は「target file の atomicity」であって「quality-system 全体の transaction」ではないと CLI help / docs / tests で明記 (思想 P7 整合)
10. `qgb patch <target> <patch.json>` で OK、ただし target は project-relative のみ、絶対 path / `.quality-system/{policy,contract,req-meta}` 以外は reject
11. exit code 1=DENY / 2=NOT_READY の分類を `--json` で machine-readable reason 付きで返す (Step 2.5 が消費)
16. `--json` に warnings を構造化して返す、text でも "applied with warnings" を出す

**判断 OK (Step 2.2 では追加不要):**
- `move` / `copy` Phase 3 送り (Pattern B は add/replace/remove/test で足りる、並べ替えは remove+add で表現可能)
- `patch.schema.json` の配置先 `qgb/schemas/patch.schema.json` 妥当
- multi-file patch / multi-file lock は Phase 3 送り

### Codex の結論

> 着手前に次の 5 点だけ修正した方がいいです:
> 1. JSON Pointer / array / root path semantics を明文化する
> 2. `patch.schema.json` で op ごとの required/forbidden を厳密化する
> 3. **in-memory patch 後 doc を `validate_policy_preflight` が本当に検査できるか確認する**
> 4. `--force` を外し、`--dry-run` は swap 直前まで実行する仕様にする
> 5. `$ref allowlist`、invalid pointer、atomic original-preserve を完了条件に追加する

---

## 3. 最大の構造リスク (指摘 5 + 6): validate-policy の in-memory doc 受け入れ

実コード確認結果:

- `qgb/core/preflight.py:791` の `validate_policy_preflight(project_root, req_id=None)` は project_root を受け取り、内部で `load_policy(project_root)` / `load_req_meta(project_root, req_id)` を呼ぶ **file-system 読込前提** の実装
- in-memory doc を受け取るインターフェースは **存在しない**

これは Codex の予測通り「**Step 2.2 最大の確認事項**」が現実化した状態。「**蛇口の手前で水質チェックする装置 (validate-policy) が、現状ファイル経由でしか動かない**」。

### 取りうる 2 案

#### 案 X: validate-policy に in-memory override seam を入れる

> 「蛇口の手前で水質チェックする装置に、サンプル水を直接渡す口を新設する」

`validate_policy_preflight(project_root, *, policy_override=None, contract_overrides=None, req_meta_override=None)` のような新引数で、memory 上の dict をそのまま検査に渡せるようにする。default 経路 (override = None) は file 読込で完全互換。

**preflight モジュールに新しい「読み口」を 1 つ増やす変更**。Phase 1 で確立した validate-policy のロジック本体には触らず、入口だけ拡張。

- 規模 1.2 → 1.5 に上振れ
- Step 2.4 (`qgb check` / `qgb dev`) / Step 2.5 (proposal/adopt) で **同じ seam を再利用** できる
- disk 痕跡ゼロ、Windows rename 競合なし

#### 案 Y: sibling tmp 経由で実 file を一瞬差し替えて検証

> 「蛇口を一回ひねって少しだけ流し、味見してダメなら元に戻す」

patch を memory で当てる → sibling tmp に書く → 元 target を待避 → tmp を本 path に rename → validate-policy 実行 → 失敗なら元に戻す → 成功なら待避ファイルを破棄。

**validate-policy には触らず、file system の入れ替えタイミングで担保する変更**。preflight モジュールは無傷。

- 規模 1.2 維持
- ただし「validate-policy が走っている間、現実の `.quality-system/` は一時的に未確定状態」窓ができる
- 並行 access (`qgb run` 同時実行) リスク、Windows での rename 競合リスク

### フロー上で出る差

| 場面 | 案 X | 案 Y |
|---|---|---|
| `qgb check` 実行中に他のターミナルで `qgb run` を起動 | disk を触らないので問題なし | 「一瞬だけ書き換わった `.quality-system/`」を他プロセスが読む可能性、競合 |
| Windows でターゲットファイルが他プロセスに開かれている | `os.replace` 1 回 (失敗時は原本不変) | `os.replace` 2 回 (Windows handle 競合で失敗するリスクが倍) |
| 段 5 (adopt) が validate-policy で reject されたとき | disk に何も書いていないので「ロールバック」概念が存在しない | tmp と入れ替えを戻す処理が必要、戻し中にクラッシュで orphan tmp + 不整合 |
| 段 3 (check) が頻繁に走るとき (Step 2.4 想定) | disk IO ゼロ | 1 回の check で IO 4 回 (tmp 書き + 入れ替え 2 + 戻し 2) |

---

## 4. 思想憲章照合

| 思想 | 案 X | 案 Y |
|---|---|---|
| P3 (コード不変仮定の禁止) | ◎ — disk を触らないので「観測されない一瞬」自体が存在しない | △ — 「一瞬」を安全と仮定する前提に依存、Phase 1 `verify` 撤回と同じ罠 |
| P7 (再現可能証跡) | ◎ — 失敗時に disk に痕跡が一切残らない、記録すべき状態が 1 種類 | △ — 「tmp と入れ替えた瞬間にクラッシュ」と「validate 失敗で戻した」で痕跡が違う |
| P9 (単一責任、表面) | ○ — preflight の引数面積が増える | ◎ — preflight 無変更 |
| P9 (単一責任、本質) | ◎ — 検出ロジック 1 個、読み口を 2 つ持たせるだけ | △ — patch_apply / check / dev / adopt の 4 箇所で tmp 入れ替えロジックを再発明 |
| P11 (project-local) | ◎ | ◎ |
| NF-004 (Windows first-class) | ◎ — `os.replace` 1 回のみ | △ — `os.replace` 2 回連鎖で Windows 固有失敗確率が倍 |

P9 の **表面** だけ案 Y、それ以外はすべて案 X。

### Phase 1 先例との一貫性

Phase 1 で類似の判断が 2 回あり、いずれも **「先払いして seam を作る」を選んだ**:

1. **Step 6a の `iter_issues(severity)`**: Step 6a 単独なら `ready()` 1 個で足りたが、Step 6b 以降の再利用を見越して severity filter を主 API にした
2. **Step 6b の `qgb verify` 撤回**: 「部分検証で時間短縮できる」設計を、P3 違反の温床になるという理由で **規模を縮める方ではなく、思想を守る方** に倒した

Step 2.2 の case は **1 と同型** (再利用先払い)。Phase 1 が `iter_issues` 先払いで成功したのと同じパターンが効く。

---

## 5. 採用結論: 案 X

思想憲章で読むと案 X が筋。Phase 1 の先例と一貫し、P3 / P7 / NF-004 すべてで構造的に強い。P9 の表面的なきれいさは譲るが、本質 (同じロジックを分散させない) では案 X が勝つ。

規模 1.2 → 1.5 の上振れは、Phase 2 全体規模 6.2〜10.0 の上限内に十分収まる。Step 6a の severity 先払いと同じ「Step 単独で 0.3 払って Phase 全体を軽くする」前借りで、Phase 1 で実証済みのパターン。

**user 判断**: 2026-06-05、user により案 X 採用確定。本ジャーナル作成。

---

## 6. Step 2.2 着手前構造修正の全リスト (案 X 採用後)

Codex 5 着手前修正要件 + 案 X 採用に伴う追加事項を統合:

### 6.1 validate-policy override seam (案 X 採用、最大の構造修正)

- `qgb/core/preflight.py` の `validate_policy_preflight(project_root, req_id=None, *, policy_override=None, contract_overrides=None, req_meta_override=None)` に拡張
- default (override = None) は file 読込で Phase 1 完全互換、既存テスト 487 件全緑のまま
- `policy_override`: dict、`load_policy(project_root)` の代わりに使う
- `contract_overrides`: dict mapping contract_ref → contract dict、`load_contract` の代わりに使う
- `req_meta_override`: dict、`load_req_meta(project_root, req_id)` の代わりに使う
- `run_preflight` (run 用) にも同じ seam を追加するかは Step 2.4 設計時に判断。Step 2.2 では `validate_policy_preflight` だけ拡張
- 思想 P9 の本質 (検出ロジック 1 個) は守る — load 経路だけ override で分岐

### 6.2 JSON Pointer / array / root path semantics 明文化 (Codex 指摘 1, 2)

- `qgb/core/json_pointer.py` 新設 (Codex 指摘 13 採用、P9)
- `encode(tokens) -> str`、`decode(pointer) -> list[str | int]` を提供
- 既存 `_json_pointer_escape` / `_to_pointer` (schema.py) を移植、schema.py 側から re-export
- decode の invalid escape は **必ず `PointerError` で reject**:
  - path が `""` または `/...` 以外
  - `~` の後続が `0` / `1` 以外
  - array index が整数でない
  - array index の leading zero (0001 など)
  - object に対する `/-`
  - list に対する non-index token
- patch 側の semantics (RFC 6902 寄り):
  - `add` object: 既存 key は **replace 相当として許す**
  - `add` array: `0..len` 挿入と `/-` append を許す
  - `remove` root path `""`: 許す (apply 後 schema/validate で落ちる前提、低レベル patch として許容)

### 6.3 patch.schema.json の厳密化 (Codex 指摘 3)

- `qgb/schemas/patch.schema.json` 新設
- 配列、各要素が op object
- `op` enum で `add` / `replace` / `remove` / `test` のみ (move/copy は Phase 3、`from` 自体 forbidden)
- `add` / `replace` / `test`: `value` required
- `remove`: `value` forbidden
- `additionalProperties: false`
- path は JSON Pointer pattern (Step 2.1 で確立した RFC 6901 規則)

### 6.4 PatchError 構造化 (Codex 指摘 12)

- `qgb/core/patch.py` で `PatchError` クラスに `reason: str` フィールド
- reason enum:
  - `invalid_patch_document`
  - `unsupported_op`
  - `invalid_pointer`
  - `missing_path`
  - `missing_value`
  - `path_not_found`
  - `test_failed`
  - `validation_failed`
- Step 2.5 (Pattern B) で proposal/adopt 経路の安定判定に使う

### 6.5 CLI 仕様 (Codex 指摘 7, 8, 9, 10, 11, 16)

- `qgb patch <target> <patch.json>` 採用 (project-relative target のみ、絶対 path / `.quality-system/{policy,contract,req-meta}` 以外は reject)
- `--force` は **入れない** (no-op flag の罠回避)
- `--dry-run` は **swap 直前まで完全実行** (patch schema 検証 → patch 適用 → target schema 検証 → validate-policy 走らせる → tmp 作らない → `--json` に `would_write: true`)
- exit code: 0 = OK、1 = DENY (validate-policy 失敗)、2 = NOT_READY (schema/path 不正)
- `--json` 出力に machine-readable reason (PatchError.reason 由来) と warnings を構造化して返す
- CLI help / docs に「target file の atomicity であって quality-system 全体の transaction ではない」を明記 (P7 整合)

### 6.6 完了条件 (Codex 指摘 17, 18 — 30 件前後)

- 4 op (add/replace/remove/test) × 3 ケース (正常 / 境界 / reject) = 12 件
- JSON Pointer escape: `~0` / `~1` / invalid (`~2`, 末尾 `~`) = 3 件
- root path `""` / array append `/-` / array bounds = 3 件
- atomic 保証: schema reject 時原本不変、validate-policy reject 時原本不変、tmp が残らない、cross-device error = 4 件
- dry-run: `would_write: true`、原本不変、tmp 不変 = 2 件
- CLI 経路: absolute path reject、`.quality-system/` 外 target reject、warnings 構造化 = 3 件
- **Step 2.1 `$ref` allowlist regression**: contract patch で `allow_internal_ref: true` を追加 → internal `$ref` accept、external `$ref` reject 経路で原本不変 = 2 件
- **`validate_policy_preflight` override seam の Phase 1 互換**: default 経路で既存 487 件全緑、override 経路で新規テスト = (既存維持 + 新規 3-5 件)
- **元 doc 非 mutate** op 別テスト (Codex 指摘 14) = 4 件
- 合計: **約 30 件**

---

## 7. 規模感 (Step 2.2 着手前見積もり、案 X 採用後)

| 内訳 | 規模 (Phase 1 Step 5 = 1.0) | 主要リスク |
|---|---:|---|
| `json_pointer.py` 新設 + Step 2.1 関数移植 | 0.2 | encode/decode 双方向の RFC 6901 完全準拠 |
| `patch.py` (4 op + PatchError 構造化) | 0.3 | array semantics / root path 境界 |
| `patch.schema.json` 新設 | 0.1 | op 別 required/forbidden の if-then |
| `patch_apply.py` (atomic + override seam 呼び出し) | 0.3 | swap タイミング、cross-device error |
| `preflight.py` override seam 追加 (案 X) | 0.3 | default 経路の Phase 1 互換維持 |
| `cli.py` に `qgb patch` 追加 | 0.2 | `--dry-run` の swap 直前まで完全実行 |
| テスト 30 件 | 0.3 | regression テスト網羅 |
| **合計** | **1.7** | (補修込みの上限) |

Codex 当初見積もり 1.2 + 案 X 上振れ 0.3 + Codex 5 着手前修正要件 0.2 = **1.7**。Phase 2 全体規模感 6.2〜10.0 の上限内に収まる。

---

## 8. Step 2.4 / 2.5 への前借り効果

案 X で seam を作ると、Step 2.4 / 2.5 で再利用できる:

### Step 2.4 (qgb check / qgb dev)

- `qgb check --proposal-patch proposal.patch.json` が **Step 2.2 の patch_apply.py + override seam をそのまま呼ぶ**
- disk 一切触らずに validate-policy 結果を `.qgb/tmp/check/<timestamp>/gate.json` に出力
- Step 2.4 で新規実装する disk 操作は curated `evidence/latest/` 不変保証のみ
- Step 2.4 規模感: Codex 計画レビュー 2026-06-01 で 1.0 想定、案 X 採用で **0.8 程度に下振れ** 見込み

### Step 2.5 (Pattern B propose-context / adopt)

- `qgb design-stages adopt proposal.patch.json` が **Step 2.2 の patch_apply.py + override seam をそのまま呼ぶ**
- proposal の validate を memory 上で済ませてから atomic swap
- Step 2.5 で新規実装するのは proposal.schema.json (構造化 input) と adopt CLI 経路のみ
- Step 2.5 規模感: Codex 計画レビュー 2026-06-01 で 1.5 想定、案 X 採用で **1.2 程度に下振れ** 見込み

### Phase 2 全体規模感の再計算

| Step | 当初 | 案 X 採用後 | 差分 |
|---|---:|---:|---:|
| 2.1 schema baseline (完結) | 0.8 | 0.8 | 0 |
| 2.2 patch substrate | 1.2 | **1.7** | +0.5 |
| 2.3 domain edit commands | 1.0 | 0.9 (PatchError 構造化を 2.2 で完了) | -0.1 |
| 2.4 daily verification channel | 1.0 | **0.8** | -0.2 |
| 2.5 Pattern B external-LLM | 1.5 | **1.2** | -0.3 |
| 2.6 example packs | 1.5 | 1.5 | 0 |
| 2.7 strictness review | 0.5 | 0.5 | 0 |
| **合計** | **7.5** | **7.4** | -0.1 |

Phase 2 全体規模はほぼ変わらず (7.5 → 7.4)、Step 2.2 で 0.5 払って Step 2.3 / 2.4 / 2.5 で 0.6 回収する **前借りパターン** が成立する。

---

## 9. Step 2.2 実装着手前のチェックリスト

着手前に確定済の事項:

- [x] Codex 計画レビュー 18 指摘 受領
- [x] 5 着手前修正要件 確定
- [x] 案 X / 案 Y 検討 (思想憲章照合 + 想定 user × LLM フロー)
- [x] 案 X 採用 (user 判断 2026-06-05)
- [x] override seam 設計の docstring 案 固定
- [x] `json_pointer.py` / `patch.py` / `patch.schema.json` / `patch_apply.py` のモジュール分割確定
- [x] PatchError reason code enum 確定
- [x] `qgb patch` CLI 仕様 (`--dry-run` あり、`--force` なし) 確定
- [x] 完了条件 30 件前後 確定
- [x] Phase 2 全体規模感 (7.5 → 7.4) 再計算
- [x] 本 prejournal 作成

実装段階で確定すること:

- [ ] `validate_policy_preflight` の override 引数の正確なシグネチャ (`contract_overrides` を mapping にするか dict にするか)
- [ ] `patch.py` の各 op の例外境界 (path_not_found vs missing_path の使い分け)
- [ ] `patch_apply.py` の output format (`--json` の schema)

---

## 10. 改訂履歴への反映予定

Step 2.2 完結時に `detailed-design.md` 改訂履歴に以下を追記予定:

```
| 0.18 | 2026-06-XX | Phase 2 Step 2.2 着手前判断 (本 prejournal で確定): 案 X 採用 (validate-policy override seam)、Codex 計画レビュー 18 指摘 + 5 着手前修正要件吸収、規模 1.2 → 1.7 に上振れ (Step 2.3/2.4/2.5 で 0.6 回収する前借り) ... |
| 0.19 | 2026-06-XX | Phase 2 Step 2.2 完結: ... |
```

---

## 11. 次のアクション

1. 本 prejournal を commit + push
2. Step 2.2 実装着手 (`json_pointer.py` → `patch.py` → `patch.schema.json` → `patch_apply.py` → `preflight.py` override seam → `cli.py` `qgb patch` の順)
3. 段 1〜5 レビュー (memory `review-process` + memory `parallel-strategy` テンプレ v3 厳守)
4. 補修 + 収束 + 完結ジャーナル作成

---

**本 prejournal の目的**: Step 2.2 規模感の上振れと前借り判断を **着手前に書面化** して、後から「なぜ Step 2.2 が 1.7 まで膨らんだか」を Phase 2 完結時 / Phase 3 計画時 / Phase 4 以降の Step 2.2 改造時に再構成できるようにする。
