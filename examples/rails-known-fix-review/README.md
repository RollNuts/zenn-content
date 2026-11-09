# 公開済みのRails修正を、Coreの監査索引でどこまで追えるか

Chatwootの公開済み修正を知ったうえで、修正前と修正後の**ソース索引**を比較する再現例です。対象アプリを起動せず、攻撃・PoC・未発見の脆弱性探索も行いません。非公開のHunt実装や調査記録は使いません。

問いは「索引から、人が確認すべき場所と、未解決の情報を取り出せるか」です。索引が同じことを、コードの安全性が同じだとは解釈しません。

## 対象と、先に知っている情報

- [Chatwootの公式advisory](https://github.com/chatwoot/chatwoot/security/advisories/GHSA-x288-jh8j-348c)は、書き換え可能な`account_id`によるアカウント間のリソース移動を説明しています。
- [公開fix commit](https://github.com/chatwoot/chatwoot/commit/86da3f7c069f8ed6dce2576e1a760ca72b6f40fd)の説明と4つのcontrollerが同じ問題に対応します。advisoryがこのSHAを直接参照しているわけではなく、ソースとの対応付けです。
- 対象は`automation_rules_controller.rb`の1経路に絞ります。修正はstrong parametersの許可項目から`account_id`を取り除きます。
- Coreは`fcb633eadd9b205a82ed605384def4a9f6189f9d`、Chatwootはfixとそのfirst parentへ固定します。対応関係は[case.json](case.json)に記録しています。

これは既知の修正に誘導された振り返り調査です。盲検評価、脆弱性の再発見、一般的な検出精度の測定ではありません。Git履歴は2commitの取得なので、Co-changeの評価にも使いません。

## 観測できたこと

| 確認対象 | 固定版Coreでの観測 |
| --- | --- |
| 対象controllerと`automation_rules_permit` | グラフにファイルと定義位置がある。前後のファイルblobも識別できる。 |
| 親controllerの`authorize(model)` | 認可呼び出しは1件あるが、動的・曖昧として未解決。引数の意味や認可の十分性は分からない。 |
| 対象のRails route | `resources`内のmodule scopeを合成できず、`config/routes.rb`の49行に未解決のcontextが残る。対象routeを完全な経路にできていない。 |
| 修正前後の認可・route・実行経路・Sidekiq・warning索引 | この範囲では5つのJSONがそれぞれbyte一致する。修正が不要という意味ではない。 |

ファイルや呼び出しの場所を得ることと、書き込み可能な属性やtenant境界の正しさを判断することは別です。callbackの継承、policyの意味、paramsから更新処理へのdata flowは、この索引の判定範囲ではありません。`resolved`も安全性を意味しません。

実際の小さい投影結果は[expected-summary.json](expected-summary.json)に置きます。全graphやraw reportは転載しません。CLIのraw出力には絶対パスや、短いreceiver・argument式が含まれるためです。

## 再現する

POSIXシェル、Git、Python 3.12を使います。macOS / Python 3.12.13の新規venvで、指定した2パッケージだけを追加して確認しました。初回のGit・PyPI取得には通信が必要ですが、解析にはモデル・アカウント・DB・対象アプリの起動は不要です。

このディレクトリへ移動してから、独立した一時ディレクトリを作ります。

```sh
RAILS_REVIEW_EXAMPLE="$PWD"
RAILS_REVIEW_ROOT="$(mktemp -d)"

git clone --no-checkout https://github.com/RollNuts/veripsa.git "$RAILS_REVIEW_ROOT/core"
git -C "$RAILS_REVIEW_ROOT/core" checkout --detach fcb633eadd9b205a82ed605384def4a9f6189f9d
python3.12 -m venv "$RAILS_REVIEW_ROOT/.venv"
"$RAILS_REVIEW_ROOT/.venv/bin/python" -m pip install --only-binary=:all: --no-deps -r "$RAILS_REVIEW_EXAMPLE/requirements-extract.txt"

git init --bare "$RAILS_REVIEW_ROOT/source.git"
git -C "$RAILS_REVIEW_ROOT/source.git" remote add origin https://github.com/chatwoot/chatwoot.git
git -C "$RAILS_REVIEW_ROOT/source.git" fetch --depth=2 --no-tags origin 86da3f7c069f8ed6dce2576e1a760ca72b6f40fd
git -C "$RAILS_REVIEW_ROOT/source.git" worktree add --detach "$RAILS_REVIEW_ROOT/before" c22a31c19878eec7bfd23c6c859aa9a8a508689c
git -C "$RAILS_REVIEW_ROOT/source.git" worktree add --detach "$RAILS_REVIEW_ROOT/after" 86da3f7c069f8ed6dce2576e1a760ca72b6f40fd
```

両方とも完全なworktreeを使います。include指定は監査索引の対象を限定するもので、graph buildとRuby definition scanは全体へ行われます。必要な定義を除外したまま、完全な解析とは説明できません。

```sh
for RAILS_REVIEW_STAGE in before after; do
  (
    cd "$RAILS_REVIEW_ROOT/core"
    PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
      "$RAILS_REVIEW_ROOT/.venv/bin/python" -B -m tools.hunt \
      --target "$RAILS_REVIEW_ROOT/$RAILS_REVIEW_STAGE" \
      --output "$RAILS_REVIEW_ROOT/output-$RAILS_REVIEW_STAGE" \
      --include-pattern 'config/routes.rb' \
      --include-pattern 'app/controllers/api/v1/accounts/automation_rules_controller.rb' \
      --include-pattern 'app/controllers/api/v1/accounts/base_controller.rb' \
      --include-pattern 'app/controllers/api/base_controller.rb' \
      --include-pattern 'app/controllers/application_controller.rb' \
      --include-pattern 'app/controllers/concerns/*' \
      --include-pattern 'app/policies/automation_rule_policy.rb' \
      --include-pattern 'app/models/automation_rule.rb'
  ) || break
done

"$RAILS_REVIEW_ROOT/.venv/bin/python" -B "$RAILS_REVIEW_EXAMPLE/compare_indexes.py" \
  --before "$RAILS_REVIEW_ROOT/output-before" \
  --after "$RAILS_REVIEW_ROOT/output-after" > "$RAILS_REVIEW_ROOT/summary.json"
diff -u "$RAILS_REVIEW_EXAMPLE/expected-summary.json" "$RAILS_REVIEW_ROOT/summary.json"
```

比較器はmanifestのCore/target版・clean状態・parser・対象patternと、対象ファイルのGit blobを照合します。公開用出力はこのcaseの固定した相対パス・行・状態などに限定し、raw expressionやローカルの絶対パスは写しません。manifestは署名された証明ではないので、この照合だけで出力の真正性やfilesystemの原子的snapshotを保証するものではありません。

Ruby以外のoptional parserがある環境では、全graphの件数は変わり得ます。全graph件数・時間・メモリは固定の性能目標にせず、選んだ観測結果と制限を比較します。

## 比較器のテスト

このディレクトリで実行します。比較器自身の6テストは標準ライブラリだけで動き、対象アプリやCoreの起動は不要です。SHA逆転、dirty状態、parser・patternの不一致、blob不一致を拒否し、差分を隠さず、rawの非公開情報を結果へ転記しないことを検査します。

```sh
python3.12 -B -m unittest discover -s . -p 'test_compare_indexes.py' -v
```

## Python cacheに関する既知の制約

固定版のbare `python -m tools.hunt`は、module本体がbytecode生成を止めるより先に、自身の`.pyc`を書き出し得ます。今回、既存のindex gateは9件成功、CLI gateは14件成功・この条件の1件失敗でした。失敗を消したり成功へ読み替えたりしていません。

上の手順は`-B`と`PYTHONDONTWRITEBYTECODE=1`を明示します。別の合成診断では、両方式それぞれで9成果物・入力不変・pycacheゼロを確認しました。bare起動の問題が修正済みという意味ではありません。

## 次に改善できる小さい対象

まず、`resources`内のmodule scopeを、合成例と負例付きで解決できるかが具体的な課題です。その改善後も、認可の十分性やstrong parametersの意味を解析できることにはなりません。結果を見てラベルの意味を変えず、既存の負例も残して比較します。

この例は公開済みのソースをローカルで索引化するものです。実サービスへの検証や脆弱性報告の権限を付与するものではありません。未知の疑いを他プロジェクトの公開Issueへ投稿しないでください。

Coreは[BSL 1.1](https://github.com/RollNuts/veripsa/blob/fcb633eadd9b205a82ed605384def4a9f6189f9d/LICENSE)です。Chatwootの対象コミュニティファイルは固定版の[MITライセンス](https://github.com/chatwoot/chatwoot/blob/86da3f7c069f8ed6dce2576e1a760ca72b6f40fd/LICENSE)を参照できますが、enterprise等の別条件を一律にMITとは扱いません。この例にupstreamソースはvendorしていません。取得したソースの著作権・許諾表示は保持してください。
