# Fable 5 プロジェクト横断レビュー記録

- 実施日: 2026-07-02
- レビュアー: Claude Fable 5 (claude-fable-5)
- 経緯: Opus 4.7 で進行中だった Phase 5 Step 5.a-2-4 の完結処理直前、Fable 5 の利用可能期間が限られている事情により、通常の開発プロセスに割り込んで全体レビューを実施した (user 依頼)。
- 本書の目的: Fable 5 が残留できなくなった後でも、レビュー内容と**根拠**を別のモデル / 将来のセッション / 人間が独立に評価・実行できるように記録する。結論だけでなく「なぜそう判断したか」を残す。

## 0. レビューの方法と範囲 (何を読み、何を読んでいないか)

**Fable 5 自身が全文精読したもの:**

- `development/docs/philosophy.md` (思想憲章 v1.0 全文)
- `development/docs/framework-shape.md` (v1.0 全文)
- `development/docs/stage-design.md` (v1.0 全文)
- `development/docs/requirements_and_development.md` (v0.3 全文)
- `skills/source/body.md` (Phase 5 スキル正本 全文)
- `qgb/core/decision.py` (判定コア 全文)

**検証 subagent (Explore) に委任して機械検証したもの:**

- Agent A: CLAUDE.md 公称の 10 不変条件のコード実装検証 (file:line 証跡付き、§3 に転記)
- Agent B: tests / examples / skills tree / CI / 撤回機構残置の実態調査 (§4 に転記)

**読んでいないもの (本レビューの限界):**

- `development/docs/detailed-design.md` (1514 行) — 構成のみ把握、精読せず
- `qgb/core/` の decision.py 以外のモジュール本文 — agent の検証結果に依拠
- `qgb/cli.py` (2051 行)
- 過去の journal 群の全文 — 要約された文脈 (直前セッションの記憶) に依拠
- テストは実行していない (レビュー時点の CI 緑を信頼)

この限界により、detailed-design.md 内部の矛盾や、decision.py 以外のコードの品質問題は本レビューの検出範囲外である。

---

## Part A: 思想憲章 (philosophy.md) そのものへの評価

### A-1. 総評: 「原則が機能をベトーした実績」が憲章の資格を実証している

ほとんどのプロジェクトの開発原則は何も却下しない。この repo では憲章が実装の欲求に繰り返し勝った実績がある:

- adapter 層の全面撤回 (2026-06-21): 検出結果が ALLOW の根拠にならない = P6/P7 から導出
- `qgb verify` (軽量入口) の不採用: P3 (コード不変を前提にしない) との緊張
- Phase 4 JUnit XML 出力の WONTFIX: P11 (ALLOW 比較不可能性) との緊張
- `decision.py` が「全段階 waived」を ALLOW にしない: P1/P5

これは文書の出来ではなく**運用の実績**であり、本憲章の最大の美点。

### A-2. 強いと評価した部分 (根拠付き)

1. **P2 (探索装置/決定装置の区別)**: LLM を「不完全な決定装置」と見なす主流の欠陥フレーミングを退けている。P5 の「落とせるから何度でも生成できる、通せるから根拠を持って採用できる」は品質ゲートを生成的揺らぎの**抑圧装置ではなく活用装置**として再定義しており、これが憲章の哲学的核。
2. **P3 (ボルトの比喩、成立すべき状態への転換)**: コードが安価に再生成される時代への正しい応答。spec 駆動・契約ベース検証という業界の方向を先取り。
3. **P11 (ALLOW 比較不可能性)**: 品質フレームワークの認証・マーケティングへの漂流を憲章レベルで先回りして禁止。異例の自己認識。
4. **§5「憲章違反の検出」**: 機械検出可能な違反と人間判断すべき違反の分離列挙。各原則が機械的強制 (P6→manual_check NOT_READY、P9→validate-policy) に配線されており「vibes ではなく仕様」。

### A-3. 緊張・盲点 (重要度順、改訂提案付き)

#### A-3-1.【最重要】verification と validation の非対称が明示されていない

- **問題**: P1 は外部化された REQ を要求するが、**REQ そのものの品質を統制する原則がない**。空虚な REQ・自明に弱い REQ を書けば、全原則に完全準拠したまま権威的に見える ALLOW が量産できる。validate-policy が検査するのは構造 (単一責任・DAG・段階数) であって実質ではない。
- **性質**: 修正可能な欠陥ではなく**本質的な限界**。qgb は verification (仕様どおり作られたか) の装置であり、validation (正しい仕様か) は原理的に担えない。
- **提案**: P5 と同じ強度で「要求の妥当性は人間の責務であり、qgb はその床 (floor) を提供しない」を一項目 (P12 候補) として明示する。利用者の最大の誤用 (弱い REQ での ALLOW ロンダリング) への予防線になる。11 不易への追加はメジャー改訂 (§6 手続き)。

#### A-3-2.【将来耐性】P6 の根拠を「揺らぎ」から「監査可能性 (P7)」に置き直す

- **問題**: P6 (LLM 単独 ALLOW 禁止) の現在の根拠は「LLM の主観評価は揺らぐ・IID 保証がない」という経験的性質が前面。この論拠はモデルの進歩とともに弱くなる (「99.9% 正確なモデルでもダメなのか」という将来の挑戦に揺らぎ論では守りきれない)。
- **強い方の論拠は既に憲章内にある**: P7。LLM の判定はどれほど正確でも**再現可能な証跡ではない** (モデルは版が変わり、プロンプトは漂流する)。また人間の attestation には説明責任の宛先があるが、LLM の attestation には執行可能な宛先がない。
- **提案**: P6 の根拠節を P7 (再現可能性・監査座標系) からの導出に書き換える。文言調整なのでマイナー改訂で可能。モデル進歩に対して不変な原則になる。

#### A-3-3.【実務上最も突きやすい穴】waiver の時効不在 (P3 との緊張)

- **問題**: F-007 により waived 段階は contract や対象コードが変わっても再評価されない (spec 自身が「P3 と外見上緊張する」と認めている)。憲章は LLM 由来の ALLOW に極めて厳格な一方、**人間由来の除外が古びることに寛容**。
- **提案**: Phase 2 で先送りされた waiver expiry / contract-hash 変更検知を Phase 5 実需の中で優先度昇格する。「機械が守る不易」の網で唯一時間軸に無防備な箇所。

#### A-3-4. `human_reviewed: true` は 1 bit — P8 の防壁は最弱の人間承認と同じ強さ

- **問題**: 二重 LLM 構造 (補佐 Agent → json → skill LLM → proposal → 人間承認 → adopt) は監査経路として良いが、人間承認の記録は boolean 1 個で、深いレビューとゴム印クリックを区別する情報がない。human-in-the-loop の既知の失敗モード (承認疲れ) に対する記録上の防御がない。
- **提案**: 承認時に「人間に何が提示されたか」(proposal digest 等) を証跡に残す。修正でなく既知の限界の明示でも可。

#### A-3-5. 「不易」と「ヒューリスティック」の混在

- **問題**: P10 の「推奨段階数 3〜7」は世紀を超える不易ではなく現時点の実務的な人間工学。憲章に置くとヒューリスティック調整に重い改訂手続きが必要になる。
- **提案**: 3〜7 レンジは stage-design.md に降ろす。P10 の不易の核 (「固定階層を持たない + P9/P5/P7/P6 の制約は守る」) は既に書かれている。

#### A-3-6. 細部

- P11 の番号位置: 群 B の中で P8 の次に P11、群 C が P9/P10 — 通し番号と群構成のずれで初読者がつまずく。
- P1 の ISO 帰属: 「超過も品質ではない」は ISO 9000 定義文そのものからは出ない (gold-plating 批判としての自分の立場)。「ISO の定義に従い、さらに本憲章は超過も品質としない立場を取る」と書く方が誠実。

### A-4. メタ観察: 憲章のテーゼが qgb 自身の開発で実証された

Step 5.a-2-4 で **Codex 机上レビュー 6 ラウンド (K=2) が見逃した lint 欠陥を、実機 fixture 1 回が複数捕捉** (commit `b29ceef`)。これは P6/P7 のテーゼ (LLM 評価は揺らぎ、再現可能な機械的検査だけが根拠) の開発工程内での実演。同時に、開発プロセス自身が LLM レビューに憲章が許す以上の重みを置いていた軽い皮肉を含む。

**派生提言**: qgb 自身を qgb でゲートする (完全 dogfooding)。`.quality-system/` を qgb repo に張り、「lint fixture 7/7 PASS」等を REQ-QGB-XXX の contract にする。憲章の一貫性の最終試験であり、Phase 5 スキルへの最良の few-shot 教材。

---

## Part B: 要件・設計文書の理念準拠

**評価: 高い準拠度。文書体系そのものが「不易の外部化」の実演。**

- F/NF/C 系要件が P 番号へ明示配線され、それが実際の改訂判断 (verify 撤回、Phase 4 廃止、adapter 撤回) に使われた形跡が文書内に残る。
- **撤回の記録様式が優秀**: 撤回した受け入れ条件を打ち消し線で残して番号保持 (外部参照を壊さない)、撤回理由を 3 点構造で反復記録。「かつて正しかったこと」の保存は P7 を文書自身に適用した形。
- framework-shape §7.4 のドメイン依存性前置き (責務分離を他ドメインに普遍適用するなという警告) は設計文書として珍しい知的誠実さ。
- **残課題**: stage-design §13 の `human_attestation` 型が「Phase 2 以降で設計」と約束されたまま未着手。manual_check の受け皿がなく「機械化できない検査は REQ から追い出すしかない」状態が継続。Phase 5 実需で優先度再評価を推奨。

---

## Part C: 実装の理念・設計準拠 (機械検証結果)

検証 subagent により 10 不変条件すべて VERIFIED (2026-07-02 時点、commit `17b5adc`):

| # | 不変条件 | 結果 | 証跡 |
|---|---|---|---|
| 1 | 判定フロー順序 (§6.4.2) | ✅ | `qgb/core/decision.py:154-187` |
| 2 | `basis[]` は REQ/POLICY/CONTRACT/WAIVER のみ | ✅ | `qgb/core/evidence.py:146-163` (project-context 混入なし) |
| 3 | ALLOW 限定意味の verbatim 記録 | ✅ | `qgb/core/decision.py:99` |
| 4 | read 全経路 utf-8-sig / write は BOM なし utf-8 | ✅ | `loader.py:54`, `evidence.py:442-446`, `check.py:210-216` |
| 5 | manual_check → NOT_READY | ✅ | `preflight.py:678-691` (waived は先に除外) |
| 6 | shell=True / os.system 不在 | ✅ | `command.py:408` で `shell: False` 固定 |
| 7 | `qgb check` は curated / knowledge.jsonl 不変更 | ✅ | `check.py:162-220` + docstring 契約 |
| 8 | runtime 依存 jsonschema のみ | ✅ | `pyproject.toml:27-29` |
| 9 | qgb は LLM/network を呼ばない | ✅ | http client import ゼロ、schema remote URI 拒否 |
| 10 | waiver は reason + decided_by 必須 | ✅ | `knowledge.py:211-236` (run 自動記録と add-waiver が builder 共有) |

**decision.py 精読での質的所見** (Fable 5 直接確認):

- 「全段階 waived → ALLOW にせず DENY、かつ `failed_stage` は空」— waived 段階を失敗犯人に見せない判断 (Step 7 補修 Codex 5)
- `meaning` を F-016 verbatim に保ち P11 の局所性注記を別フィールド `scope` に分離 — exact-match consumer を壊さない (Codex RA2)
- ALLOW 事後条件 assert (judgement_passed > 0) — schema 側と in-process の二重防御

いずれも二次消費者への影響まで考えられており、憲章が末端の分岐に届いている。

---

## Part D: 発見した問題 (実害あり得る順)

### D-1.【5.b 前必須】body.md §10.1 の `pip install quality-gate-builder` — 供給網リスク

- **事実**: `skills/source/body.md` §10.1 (トラブルシューティング) が `pip install quality-gate-builder` を第一の導入手段として案内。しかし qgb は PyPI 未公開 (Phase 1 で明示的に配布対象外、Phase 2+ でも未実施)。
- **リスク**: スキル dist 後、利用者環境の agent がこのコマンドを実行する。失敗で済めばよいが、**この名前を第三者が PyPI に squat していた場合、悪意あるパッケージを掴む**。NF-011 (PyPI は untrusted infrastructure) と自己矛盾する唯一の箇所。
- **対処案**: (a) git clone + editable install への書き換え (最小)、(b) PyPI 名の防衛的確保 (併用推奨)。

### D-2.【5.b 前必須】実機 fixture runner が lint の Python 実装しか検査していない

- **事実**: `tests/fixtures/lint_command_contract/run-tests.ps1` は lint の Python 版のみを呼ぶ (「PowerShell sibling parity は別途検証済みと仮定」とコメント)。
- **根拠**: K=2 の歴史が示すとおり parity バグはこの二重実装の主要欠陥クラス (r2 fix #1 = PS 空配列 collapse、r3 fix #3 = Python casing 非対称)。仮定でなく機械検証にすべき。
- **対処案**: run-tests.ps1 を拡張し、各 fixture を Python 版と PS 版の両方に流して exit code + finding 種別の一致まで assert する。

### D-3.【軽微】body.md line 713 typo `chcek` — dist 前に修正。

### D-4.【低優先】テストファイルの歴史物語ベース命名

- `test_step6d_codex_fixes.py` 等 6 ファイル。「挙動 X はどこでテストされているか」の探索性を下げる。機能ベース名への統合を 5.b 以降の低優先タスクとして提案。

### D-5.【低優先】full モード SKILL.md のサイズ

- body.md は 63K (≈16k tokens)。オンデマンド読込とはいえ発火ごとのコストが大きく、split モードが実質推奨になる見込み。dist 時の利用者ガイドで明示を。

---

## Part E: 開発プロセスのメタ評価

- **journal 文化は本物の資産**。prejournal → 実装 → 完結 journal → compact 跨ぎ journal の層は「なぜ」の保存という点で仕様書の届かない範囲を正しくカバー。途中参加したモデル (Fable 5) が短時間で全文脈を復元できたこと自体が実証。
- **K=2 (Codex 机上レビュー収束) の構造的限界が観測された**: 5.a-2-4 の finding 系列は 5→5→4→1→2→2 で収束せず、実機 fixture 1 回が机上 6 ラウンドの見逃しを複数捕捉。
- **一般化した教訓**: 仕様整合・文書ドリフトには K=2 が有効。**OS/runtime の挙動に依存するコードでは、実機 fixture を最初のレビューラウンドの前に置くべき**。→ auto-memory `review-process` の改訂に値する (本レビュー後に反映予定)。
- 5.a-2-4 を「K=2 達成」でなく「実機証跡による運用基準達成」で閉じる判断は憲章に忠実 (LLM レビューの収束より機械的証跡を上位に置く)。

---

## Part F: 推奨アクション一覧 (優先順・実行先付き)

| # | アクション | 優先度 | 実行先 | 由来 |
|---|---|---|---|---|
| 1 | body.md §10.1 の pip install 記述修正 (+ PyPI 名防衛確保の検討) | 5.b 前必須 | `skills/source/body.md` | D-1 |
| 2 | 実機 fixture を lint PS 実装にも適用、両実装の結果一致を assert | 5.b 前必須 | `tests/fixtures/lint_command_contract/run-tests.ps1` | D-2 |
| 3 | body.md typo 修正 (line 713 `chcek`) | 5.b 前 | `skills/source/body.md` | D-3 |
| 4 | review-process memory の改訂 (実機 fixture 先行の原則) | 早期 | auto-memory | Part E |
| 5 | 憲章改訂検討: validation 限界の明示 (P12 候補、メジャー) | Phase 5 中 | `philosophy.md` + §6 手続き | A-3-1 |
| 6 | 憲章改訂検討: P6 根拠を P7 に付け替え (マイナー) | Phase 5 中 | `philosophy.md` | A-3-2 |
| 7 | waiver expiry / contract-hash 変更検知の優先度昇格 | Phase 5 実需 | Phase 3 Step 3.3 バックログ | A-3-3 |
| 8 | `human_attestation` 型の再優先度付け | Phase 5 実需 | stage-design §13 バックログ | Part B |
| 9 | human_reviewed 承認時の提示内容 digest 記録 | Phase 5 実需 | proposal/adopt 経路 | A-3-4 |
| 10 | 3〜7 レンジを憲章から stage-design へ降格 | 任意 | `philosophy.md` / `stage-design.md` | A-3-5 |
| 11 | qgb 自身の dogfooding (REQ-QGB-XXX) | 構想 | Phase 5 後半以降 | A-4 |
| 12 | テストファイル命名の機能ベース化 | 低優先 | `tests/` | D-4 |
| 13 | full/split モードのコスト差を利用者ガイドに明示 | 5.b 中 | dist ガイド | D-5 |

**プロセス上の注意**: #5/#6/#10 は憲章改訂であり §6 の改訂手続き (Issue 起票 + 影響評価 + 版番号) を要する。#1-#3 は Step 5.a-2-4 完結処理と同じタイミングで拾える軽量 fix。#4 は memory 更新のみ。

---

## Part G: 本レビューの自己評価と限界

- 本レビューは 1 モデル (Fable 5) の 1 セッションによる読解であり、憲章 P2 に従えば**候補**である。特に Part A の憲章改訂提案 (#5/#6/#10) は哲学的判断を含むため、user 自身の判断と (必要なら) 別 LLM のセカンドオピニオンを経てから改訂手続きに入るべき。
- Part C の 10 不変条件検証は subagent の file:line 証跡付き報告に基づくが、Fable 5 自身が全行を目視したのは decision.py のみ。証跡の file:line は将来の検証者が独立に再確認できる。
- Part D の発見事実 (D-1, D-2, D-3) は客観的に検証可能であり、モデルの主観に依存しない。
