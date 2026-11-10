# 「実行が通る修正」は、仕様も守っているか？

二つの修正案がどちらも同じ値を返したとき、何を根拠に選びますか。
この無料実習では、先に要求を記録し、実行結果と照らして修正をレビューします。
Coreの[既存デモ](https://github.com/RollNuts/veripsa/tree/2c6850617bacaaa5cd31e34a490983597a18086d/examples/structural-overlap)を再利用し、
合成のPythonコードだけを一時ディレクトリで実行します。自分のアプリの修正や実行は行いません。

## 先に判断を書いておく

題材は、別ファイルにある関数と呼び出し側です。

```python
# 元の関数と呼び出し
def calculate_total(amount, fee=5):
    return amount + fee

calculate_total(100, fee=5)
```

変更Aは関数を `calculate_total(amount, *, fee=5)` にし、`fee` をキーワード専用にします。
変更Bは呼び出しを `calculate_total(100, 5)` にします。
各変更は単独では動き、Gitも異なるファイルをcleanにマージしますが、組合せは `TypeError` です。
ここまでが既存デモの観測です。

**今回の演習では、修正前に次の要求を置きます。** 実サービスで合意された要件という意味ではありません。

1. `checkout()` は105を返す。
2. 新しいAPIでは `fee` をキーワード専用にする。
3. `calculate_total(100, 5)` のような位置引数は拒否する。

レビューする修正案は二つです。

- **案A：呼ばれる関数を戻す。** `*` を外し、位置引数も受け付ける。
- **案B：呼び出し側を合わせる。** `calculate_total(100, fee=5)` とキーワードで渡す。

出力を見る前に、次の欄を自分の言葉で埋めてください。

| 記入すること | 案A | 案B |
| --- | --- | --- |
| `checkout()` は成功するか。値は何か | | |
| 三つの要求のうち、満たさないものはあるか | | |
| 確認したいコードと、追加したいテストは何か | | |

「どちらも動く」「候補が出た」という一文だけでは、二つの案を選ぶ根拠が残りません。

## 実行する

POSIX環境、Git、Python 3.12を使います。追加パッケージ、DB、AI契約は不要です。
信頼できるCoreの**固定版コードを実行する**実習であり、任意のcheckoutを安全に実行するsandboxではありません。
新しい作業用ディレクトリから、次のブロック全体を実行します。
途中でコマンドが失敗したら、括弧の中の処理を終了します。

```sh
(
set -eu
git clone https://github.com/RollNuts/veripsa.git veripsa-review-lab
git -C veripsa-review-lab checkout --detach 2c6850617bacaaa5cd31e34a490983597a18086d
git clone https://github.com/RollNuts/zenn-content.git zenn-review-lab
python3.12 -B zenn-review-lab/examples/repair-review/lab.py --core veripsa-review-lab
)
```

既に両方を取得済みなら、最後のPythonコマンドのパスだけを合わせます。
Coreは指定版・cleanなcheckoutが必要です。版を変更するのは、この実習用cloneだけにしてください。
Gitを明示する場合は `--git /path/to/git` を追加できます。

`lab.py` は固定版demoの内部ヘルパーを使います。安定したCore公開APIとは位置付けません。
CoreのGit HEADとstatusを前後に確認しますが、これはsandboxや原子的なsnapshotの保証ではありません。
Core自身のコードを書き換えず、生成した合成コードの変更・実行は一時ディレクトリ内で完結します。

## 出力を使って答え合わせする

`runtime` と `requirements` を別々に読みます。
`stated_requirements_met` は**この演習で列挙した三条件のAND**であり、一般的な正しさやマージの承認ではありません。

| 状態 | `runtime` | 105を返す | キーワード専用 | 位置引数を拒否 | 三条件を満たす |
| --- | --- | --- | --- | --- | --- |
| 修正前 | failed / TypeError | false | true | true | false |
| 案A | passed / 105 | true | false | false | false |
| 案B | passed / 105 | true | true | true | true |

この表は固定版で実際に実行した結果です。保存した[JSON](expected-output.json)と、
次の検証スクリプトでも確認できます。

```sh
python3.12 -B zenn-review-lab/examples/repair-review/verify.py --core veripsa-review-lab
```

### なぜ「105が出た」だけでは足りないか

案Aも案Bも、通常の呼び出しで105を返します。値だけを確認するテストでは両方が通ります。
違いは、先に残すと決めたAPIの扱いです。案Aは位置引数を再び許すため、要求2・3を満たしません。
案Bは呼び出し側を新APIに合わせるため、今回の三条件を満たします。

実習は実際の呼び出しに加え、`inspect.signature` による引数種別と、位置引数での呼び出しの拒否を確認します。
テストの数を増やすことが目的ではなく、値だけのテストが扱っていなかった要求を記録します。
要求が「古い位置引数も引き続き許す」なら判断は変わります。先に要求の根拠を確認してください。

### Coreが示す根拠と、選ばない判断

修正前の `original_evidence` は、Gitがclean、静的関係が `observed`、履歴関係が `not_observed` です。
静的な関係は二つのファイルを一緒に読む理由になります。関数のAPIを戻すべきか、呼び出し側を直すべきかは選びません。
Coreが `TypeError` や修正案の合否を予測したのでもありません。別の合成実行がそれらを観測しています。

この実習ではAIの見落とし率、時間短縮、一般のバグ検出精度を測っていません。
GitHub Appのホスト動作や自動マージも使いません。

## 自己採点と、自分の変更への引継ぎ

次の四つを、自分の記入欄とJSONで説明できれば、この演習の到達点です。

- 二案とも105を返すが、今回の三条件では案Bだけが通る。
- 案Aの問題を「危険だから」ではなく、要求2・3のどちらを破るかで説明できる。
- コードの関係・実行結果・要求の合否を、それぞれ別の根拠として引用できる。
- 三条件以外の境界値、他の呼出元、実サービスへの適合は、この実習では確認していないと言える。

自分の変更をレビューするときは、次の小さな記録へ置き換えます。

```text
変更の目的：
保持する要求と、その根拠：
関連先を読む理由：
試した入力・組合せ・版：
結果と、まだ確認していないこと：
この結果だけでは決められない判断：
```

実行が非ゼロ終了、JSONが不成立、版違い、Coreがdirty、Git読取り失敗なら、成功データとして採点しません。
設定や検査を弱めて通さず、実習用cloneと前提を確認します。配布されたコードの信頼性と実行権限も先に確認してください。

## 追加実習：解析の時点と、履歴の基準を変える

同じ環境で、次の二つの対比も試せます。新しい解析エンジンではなく、固定Coreの既存CLIと履歴計算を使います。

```sh
python3.12 -B zenn-review-lab/examples/repair-review/evidence_lab.py --core veripsa-review-lab
python3.12 -B zenn-review-lab/examples/repair-review/verify_evidence.py --core veripsa-review-lab
```

実行前に、次を予想してください。

1. 対象の`billing/pricing.py`とHEADを変えず、相手の呼出元だけを未コミットで動的importへ変えたら、静的候補と履歴候補はどうなるか。
2. 二つのファイルのコメントだけを8回追加で共変更したら、共変更回数が増えた分、既定の履歴候補に残りやすくなるか。

実測した[JSON](evidence-output.json)では、次の結果でした。

- **解析の時点：** 実行値105と履歴section・HEADは不変ですが、静的候補から呼出元が消えました。実装した動的参照をこの投影が見落とす例で、無関係になったという意味ではありません。provenanceで変わったのは`dirty`と`status_sha256`です。対象ファイルのhashだけでは、相手ファイルの編集を説明できません。
- **履歴の基準：** 共変更6回/14commit、lift2.33から、14回/22commit、lift1.57へ変化し、既定の最小lift2を下回って履歴候補から外れました。二つのPython AST、静的section、今回の実行値105は不変です。回数だけで信号の強さや因果関係を結論づけません。

これらも合成した履歴・入力だけの対比です。一般的な意味同値、未知のrepoでの精度、バグ予測を証明しません。
検証器は要約フラグと元のJSONを照合し、数値・HEAD・hash・候補の意図的な不一致も拒否します。
`python3.12 -B -O .../verify_evidence.py --core ...`のように最適化しても検査は無効になりません。

再利用するCoreのライセンスは[Business Source License 1.1](https://github.com/RollNuts/veripsa/blob/2c6850617bacaaa5cd31e34a490983597a18086d/LICENSE)です。
この実習はその条件やCoreの機能を変更しません。
