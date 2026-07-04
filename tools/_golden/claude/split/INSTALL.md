<!--
  GENERATED FILE - DO NOT EDIT.
  これは生成物。skills/source/body.md を編集すること。
  skill_version: 0.1.3
  converter_version: 0.1.1
  build_input_digest: 8297056c361259ee
-->
# qgb skill インストールガイド (claude / split)

## 配置先 (このスキル自身)

- 個人全プロジェクト共通: `~/.claude/skills/qgb/`
- プロジェクト単位: `.claude/skills/qgb/`

## コピーするファイル

- `SKILL.md` (本体。helper の位置に `@see <helper-path>` の参照行が入る)
- helper files (`workflow.md` / `references.md` / `prompts/*.md` 等、SKILL.md と同じディレクトリに配置)

## qgb 本体のインストール (対象プロジェクトへ)

スキル自体の配置とは別に、`qgb` CLI 本体を**対象プロジェクト側**にインストールする必要があります。以下 (A) 推奨手順を優先し、うまくいかない場合のみ (B) 手動手順を使ってください。

### (A) 推奨: 同梱 setup script を実行

このディレクトリに同梱されている `setup-qgb.ps1` / `setup-qgb.sh` を対象プロジェクトのルートにコピーし、実行してください。`.venv` を作成 (既存の `.venv` があれば温存) し、タグ固定 (`skill-v0.1.3` -- このスキルと同じバージョンにビルドされたタグ) で `git+` install した後、`qgb --version` で動作確認まで行います。

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File setup-qgb.ps1
```

POSIX (bash):

```bash
bash setup-qgb.sh
```

オフライン環境 / 開発中でローカル clone から入れたい場合は `-FromPath <ローカル clone のパス>` (PowerShell) / `--from-path <ローカル clone のパス>` (bash) を指定してください (editable install、`pip install -e <path>`)。

### (B) 手動 (venv 手順)

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install "git+https://github.com/Yumeno/Quality-gate-builder.git@skill-v0.1.3"
```

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "git+https://github.com/Yumeno/Quality-gate-builder.git@skill-v0.1.3"
```

`skill-v0.1.3` はこのスキルの build と同じバージョン (`metadata.yaml#version`) から機械的に導出されたタグです。別バージョンのスキルを使う場合はそのスキルの INSTALL.md が焼き込む別タグを使ってください。

**信頼境界の注記**: `git+` install は指定タグの repo をclone して実行するのと同等の信頼を要求します (pip install 中に任意コードが実行され得る)。`--require-hashes` はこの install 経路には使えません (NF-011)。

**注 (分かっている人向け、非推奨)**: venv を使わずグローバルに `pip install` することも技術的には可能ですが、他プロジェクトの依存関係と衝突するリスクがあるため推奨しません。また `pip install quality-gate-builder` は**実行しないでください** (PyPI 未公開のため、同名パッケージが存在した場合それは qgb ではありません。将来 PyPI 公開された場合は本節を更新します)。

## hooks (任意, opt-in)

`hooks/` 配下に hook テンプレと `README.md` を同梱しています。利用する場合は `hooks/README.md` の手順に従って opt-in / dry-run / validate / 非破壊の後で既存設定へ merge してください。

## lint (verification_type=command 契約作成時)

`lint/` 配下に `check-command-contract.py` / `check-command-contract.ps1` を同梱しています。skill agent は `verification_type=command` の contract を起草・編集した直後にこの lint を実行し、fix-required の finding がないことを確認してから `qgb design-stages adopt` へ進むこと。詳細は `lint/README.md` を参照。

## Windows についての注意

Windows native 環境では symlink race 防御 (`O_NOFOLLOW` 相当) が POSIX より弱いことがあります。clean build + exclusive create の防御は有効ですが、信頼できない共有環境での build は推奨しません (詳細: `development/docs/journal/phase5-step5-a-2.md` §6.3 item 5)。
