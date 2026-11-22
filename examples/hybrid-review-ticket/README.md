# 版を固定したレビュー票の受け渡し

「古い版への返事は採らない」「送信が許可されなければ端末で保留する」「手元で次の検査を決められればクラウドを呼ばない」を、モデルなしで試す教材です。

Python 3.12と標準ライブラリだけを使います。リポジトリのルートから実行してください。

```sh
python3.12 examples/hybrid-review-ticket/demo.py
python3.12 -m unittest discover -s examples/hybrid-review-ticket -p 'test_*.py' -v
```

`demo.py`の1ファイルだけでも動きます。追加パッケージ・アカウントは不要です。外部通信、LLM呼び出し、Git操作、テストやモデル返信中のコマンドの自動実行は行いません。ファイルも保存しません。

## 入出力

入力はコード中に手で書いた辞書です。`B0`、`A1`、`B1`、`A2`は架空の版ラベルで、コミットSHAではありません。`E-static`と`E-history`も説明用IDであり、Coreの抽出結果を読み込んだものではありません。モデル返信も手書きです。

票は対象ID、baseと二つのhead、根拠の観測状態、手元で決めた検査ID、明示的な送信可否を持ちます。`route()`は次の作業を選び、`accept_reply()`は現在の票と返信のID・版・許可した項目を照合します。

| ケース | `outcome` | 意味 |
| --- | --- | --- |
| `local_evidence_sufficient` | `local_test_plan` | 次の既知テストを手元で選べる。安全・マージ可という意味ではない |
| `dynamic_question` | `cloud_question_prepared` | 追加の検査案を相談できる状態。送信はしない |
| `sending_denied` | `hold_local` | 外部へ送らず、端末内の調査や人の判断へ保留する |
| `no_relationship_observed` | `needs_local_observation` | 候補が出ないことを安全と扱わず、追加の観測を要する |
| `current_reply` | `inspection_plan_accepted` | 版・ID・形式が一致した検査案。内容の人による確認と実行はまだ必要 |
| `stale_reply_after_A2` | `rejected` | A2へ更新した票に、A1の返事は採らない |
| `missing_base` | `rejected` | baseが欠ける返信は採らない |
| `different_base` | `rejected` | baseが異なる返信は採らない |
| `unknown_evidence` | `rejected` | 票にない根拠IDを採らない |
| `executable_field` | `rejected` | 許可した項目以外を採らない |

検査IDは`CHECKS`にある三つに限ります。動的参照の手書き返信は、まず参照先と引数を観測する案、次に固定版の組合せでテストする案を返します。プログラムは案を表示するだけです。任意のコードやコマンド文字列を受け取って実行する機能はありません。

返信は対象ID、完全なbase/headの組、既知の根拠ID、既知の検査IDをすべて満たす場合だけ採ります。余分なJSON項目、未知ID、欠落や不一致の版は拒否します。返信を待つ間に送信許可が取り消された場合も、この例では返信を採りません。

## 確かめられることと、まだ確かめられないこと

この教材で検証するのは、**手で与えた版と根拠を取り違えない決定的な受け渡し処理**です。LLMによる意味理解、良い検査の提案、Coreの検出精度、レビュー時間や費用の削減は測りません。根拠IDが実在しても、返信がその根拠を正しく解釈した保証にはなりません。

また、架空の版ラベルを比較するだけなので、実リポジトリの現在版との一致は確認できません。未コミットの変更、作業ツリーの変化、読み取りと実行の間の更新、権限管理、送信内容の機密性は対象外です。本物の連携には、版を取得する仕組みと実行直前の再確認が別途必要です。

この例では「手元で次の検査を選べるか」と「外部へ送ってよいか」を入力として手で指定しています。それらの判断をモデルやCoreが行った実績ではありません。出力にはマージ許可や安全判定を設けず、検査計画・保留・拒否だけを扱います。

## 固定Coreの動的参照を追加観測する

別ファイルの`observe_core_fixture.py`は、手書きの票とは別の再現実験です。信頼できる固定Coreの`dynamic_lookup`合成fixtureを実行し、実際に取得された関数と三つの状態の結果を観測します。POSIX環境のGitとPython 3.12を使います。Windowsは未確認です。

このリポジトリのルートから、次を実行します。記事の手順などで同じ固定版Coreを取得済みなら、cloneとcheckoutを繰り返さず、`--core-repo`にそのルートを指定してください。

```sh
git clone https://github.com/RollNuts/veripsa.git ../veripsa-hybrid-demo
git -C ../veripsa-hybrid-demo checkout --detach 2c6850617bacaaa5cd31e34a490983597a18086d
python3.12 -I -B examples/hybrid-review-ticket/observe_core_fixture.py \
  --core-repo ../veripsa-hybrid-demo
```

clone時だけネットワークを使います。観測時はモデル・通信・追加パッケージ不要です。Gitは`PATH`から選びます。補助プログラムは指定先のHEADが上の版と一致すること、tracked変更と未追跡ファイルがないことを実行前後に確かめます。Coreのソースを読み込み、そこで定義された合成Gitリポジトリを一時ディレクトリに作って実行します。Coreのチェックアウトは編集せず、bytecodeも保存しません。

| 状態 | `resolved_target.signature` | `literal_call_arguments` | `execution` |
| --- | --- | --- | --- |
| `change_a` | `(amount, *, fee=5)` | positional `[100]`、keyword `{fee: 5}` | passed、105 |
| `change_b` | `(amount, fee=5)` | positional `[100, 5]`、keyword `{}` | passed、105 |
| `integrated` | `(amount, *, fee=5)` | positional `[100, 5]`、keyword `{}` | failed、TypeError |

三つとも実際の`calculator`の実体は、module=`billing.pricing`、name=`calculate_total`です。情報の取得方法は分けて読みます。

- `resolved_target`は、実行中の`checkout()`をtrace hookで観測した関数実体と、その`inspect.signature()`です。
- `literal_call_arguments`は、合成ソースのASTから読んだ引数リテラルです。任意の式の実行時引数を追跡する仕組みではありません。
- `execution`は実際にその合成入力で実行した結果です。元のCoreデモが実行した結果と一致することも照合します。
- `demo.py`の検査案は手書きです。この観測結果やクラウドの出力を自動で取り込んではいません。

これは本稿用に追加した補助観測であり、Coreの既存JSON出力やLLMの検出機能ではありません。HEADと作業状態の確認は完全な入力隔離や原子的なスナップショットではなく、ignoredファイル・Gitの特殊なindex flag・確認の合間の変更などは検証対象外です。**信頼済みの固定ソースを読むための補助であり、任意のリポジトリを安全に実行できるsandboxではありません。** 新しい専用cloneを使い、実行中は変更しないでください。
