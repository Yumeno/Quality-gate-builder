# 公開チェックリスト (2026-07-05 準備完了、実行待ち)

Codex (gpt-5.6-terra) レビュー反映済みの公開手順。**手順 1〜2 が済んだら手順 3 以降を上から実行する。** 実行後は本ファイルの各項目に日付を入れ、全完了したら本ファイルを journal へ移動 (`journal/publication-2026-07.md` に改名) して記録化する。

## 完了済み (private 段階、2026-07-05)

- ✅ 秘密情報監査: working tree + 全履歴・全 ref を実フォーマット regex で検査、ゼロ
- ✅ commit email (`vz7a-kwkm@nifty.com`) の露出: user 許容判断済み (履歴書き換えは不実施)
- ✅ v0.1.3 タグ未発行の事実訂正 (ドキュメント 6 箇所)
- ✅ repo メタデータ: description / homepage (releases/latest) / topics 10 件 / projects off / delete_branch_on_merge
- ✅ Actions 制限: `allowed_actions=selected` + patterns = **pin 済み SHA 2 つのみ** + `sha_pinning_required=true` (CI 全 job green で実地検証済み、run 29115748275)。pin 更新時は SECURITY.md "How To Update" 3b を忘れない
- ✅ README Acknowledgements (wakabadou さん、文言はご本人の希望で調整可)
- ✅ default_workflow_permissions=read / can_approve_pull_request_reviews=false (既定のまま確認済み)

## 手順 1: wakabadou さんの確認 (user)

- [ ] 公開への同意 (お名前が `wakaba-talk-summary.md` / README Acknowledgements 等に載って世界公開される)
- [ ] Acknowledgements の文言・名義の希望確認
- [ ] write 権限の扱い: **ruleset ではタグ作成は制限できるが、write 権限者は Release の作成・編集・asset 差し替えが可能** (Codex 指摘)。信頼ベースで write 維持を推奨、その場合この受容を本チェックリストに明記した時点で決着
- [ ] 公開作業中〜ruleset 適用完了までタグ操作を控えてもらう旨の連絡

## 手順 2: 公開 (user、GitHub UI)

- [ ] Settings → General → Danger Zone → Change visibility → Public

## 手順 3: 公開直後の設定 (agent が gh api で実行、公開前は 403 で不可)

```bash
# 3-1. branch ruleset: main の force-push / 削除禁止 (bypass: repo admin)
gh api -X POST repos/Yumeno/Quality-gate-builder/rulesets --input - <<'JSON'
{"name":"protect-main","target":"branch","enforcement":"active",
 "conditions":{"ref_name":{"include":["refs/heads/main"],"exclude":[]}},
 "rules":[{"type":"non_fast_forward"},{"type":"deletion"}],
 "bypass_actors":[{"actor_id":5,"actor_type":"RepositoryRole","bypass_mode":"always"}]}
JSON

# 3-2. tag ruleset: skill-v* の作成/更新/削除を制限 (bypass: repo admin = owner のみタグを切れる)
gh api -X POST repos/Yumeno/Quality-gate-builder/rulesets --input - <<'JSON'
{"name":"protect-release-tags","target":"tag","enforcement":"active",
 "conditions":{"ref_name":{"include":["refs/tags/skill-v*"],"exclude":[]}},
 "rules":[{"type":"creation"},{"type":"update"},{"type":"deletion"}],
 "bypass_actors":[{"actor_id":5,"actor_type":"RepositoryRole","bypass_mode":"always"}]}
JSON

# 3-3. secret scanning + push protection + private vulnerability reporting
gh api -X PATCH repos/Yumeno/Quality-gate-builder -f security_and_analysis[secret_scanning][status]=enabled -f security_and_analysis[secret_scanning_push_protection][status]=enabled
gh api -X PUT repos/Yumeno/Quality-gate-builder/private-vulnerability-reporting

# 3-4. Dependabot alerts のみ有効 (自動 PR = security updates は SECURITY.md 方針どおり無効のまま)
gh api -X PUT repos/Yumeno/Quality-gate-builder/vulnerability-alerts

# 3-5. fork PR は全外部者の承認必須
gh api -X PUT repos/Yumeno/Quality-gate-builder/actions/permissions/fork-pr-workflows-private-repos 2>/dev/null || true
# ↑ 該当 API が変わっている場合は Settings → Actions → Fork pull request workflows from outside collaborators
#   を "Require approval for all outside collaborators" に (UI)
```

## 手順 4: 確認 (agent)

- [ ] ruleset 2 本が active (`gh api repos/.../rulesets`)
- [ ] README badge / Releases 5 本 / Issues が公開視認できる
- [ ] タグ作成が owner の bypass で通ることの実地確認は次回リリース (v0.1.6 以降) 時でよい
- [ ] dependabot_security_updates が disabled のままであること (`gh api repos/... --jq .security_and_analysis`)

## 留意 (Codex 指摘の受容事項)

- 公開により全履歴・過去の Actions ログ / artifacts・Releases・Issues が露出する — 監査済み・受容
- write 権限者は Release 編集が可能 — 手順 1 で決着させる
- 公開〜手順 3 完了の間は ruleset 無しの短い無保護区間 — 手順 1 の事前連絡でカバー
