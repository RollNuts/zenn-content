---
title: "テストは通る。でも、その修正を採っていい？Pythonの2案で考えるコードレビュー"
emoji: "🧪"
type: "tech"
topics: ["python", "test", "コードレビュー", "個人開発"]
published: false
---

エラーを直した。戻り値も期待どおり。テストも通った。

それでも、コードレビューで一つ確認したいことがあります。

**「今回の修正で、もともと守りたかった約束まで消していないか？」**

この記事では、戻り値だけを確かめる同じテストを通る二つの修正を、Pythonの小さな例で比べます。違いが出るのは計算結果ではなく、関数の呼び出し方です。

持ち帰れるのは、**値・許可する使い方・拒否する使い方を分けて、修正の採用条件を確かめる手順**です。Python 3.12の標準ライブラリだけで試せます。

:::message
以下の関数と要求は、違いを確かめるための架空の教材です。実際にAIが提案した修正や、実サービスで起きた障害を再現したものではありません。
:::

## エラーを消す方法は、二つある

金額と手数料を足す関数を考えます。`fee`をキーワード専用にしたところ、古い呼び出し方が残っていました。

```python
def total(amount, *, fee=5):
    return amount + fee

def checkout():
    return total(100, 5)  # TypeError
```

`*`より後ろの引数は、`fee=5`のように名前を付けて渡す必要があります。上の呼び出しは、その約束に合いません。[Python公式の説明](https://docs.python.org/ja/3.12/tutorial/controlflow.html#keyword-only-arguments)

ここで二つの修正案が出たとします。

**案A：関数から`*`を外す。**

```python
def total_rollback(amount, fee=5):
    return amount + fee

def checkout_rollback():
    return total_rollback(100, 5)
```

**案B：関数は変えず、呼び出し側に`fee=`を付ける。**

```python
def total_keyword(amount, *, fee=5):
    return amount + fee

def checkout_keyword():
    return total_keyword(100, fee=5)
```

どちらもエラーは消え、対応する`checkout`は105を返します。

もしテストが次の一つだけなら、どちらも合格です。ここでは、比較する案の関数を`checkout`として呼ぶものとします。

```python
self.assertEqual(checkout(), 105)
```

このテストは役目を果たしています。今回の入力で105になることを、二案とも確認できています。

では、どちらを採るべきでしょうか。

## 判断する前に、残したい約束を三つ書く

必要なのは、今回の変更で何を実現したかったかです。この演習では、要求を次の三つに固定します。

1. `checkout()`は105を返す。
2. `fee`はキーワード専用にする。
3. 位置引数による`fee`の指定は拒否する。

ここでいう**API契約**は、HTTP APIの仕様ではなく、Python関数の引数と呼び出し方についての約束です。

| 確認すること | 案A：関数を戻す | 案B：呼び出しを直す |
| --- | --- | --- |
| `checkout()`が105を返す | 満たす | 満たす |
| `fee`がキーワード専用 | 満たさない | 満たす |
| 位置引数の`fee`を拒否する | 満たさない | 満たす |

案Aは、今回守ると決めた呼び出し方の制約を取り除いています。案Bは、その制約を保って呼び出し側を合わせています。

**今回の要求なら、採るのは案Bです。** 戻り値だけのテストでは、この判断に必要な条件2・3をまだ検査していませんでした。

ただし、要求が「既存の位置引数による呼び出しを維持する」なら、判断は変わります。その方針に対してキーワード専用化が適切か、変更自体を見直す必要があります。

`*`を残すことに普遍的な正しさがあるわけではありません。どの呼び出し方を維持し、どの呼び出し方を意図的に拒否するかが、採用条件です。

## 要求を、四つのテストへ落とす

三つの要求に対して、今回は四つの検査を用意します。戻り値に加え、許可するキーワード呼び出しも正常に動くことを確かめます。

| テスト | 確かめること |
| --- | --- |
| `test_checkout_value` | `checkout()`が105を返す。 |
| `test_keyword_call` | `total(100, fee=5)`が105を返す。 |
| `test_fee_is_keyword_only` | 定義上、`fee`がキーワード専用である。 |
| `test_positional_fee_is_rejected` | `total(100, 5)`が`TypeError`になる。 |

以下は`unittest.TestCase`内の抜粋です。`total`と`checkout`には、選んだ案の関数を割り当てます。実行には次節で案内するファイル全体を使ってください。

```python
def test_checkout_value(self):
    self.assertEqual(checkout(), 105)

def test_keyword_call(self):
    self.assertEqual(total(100, fee=5), 105)

def test_fee_is_keyword_only(self):
    parameter = inspect.signature(total).parameters["fee"]
    self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

def test_positional_fee_is_rejected(self):
    with self.assertRaises(TypeError):
        total(100, 5)
```

`inspect.signature`は引数の種類を調べ、`assertRaises`は実際の呼び出しで例外が発生するかを調べます。定義の形と呼び出した結果を、別々に確認しています。[引数の種類の説明](https://docs.python.org/ja/3.12/library/inspect.html#inspect.Parameter.kind)・[例外の検査の説明](https://docs.python.org/ja/3.12/library/unittest.html#unittest.TestCase.assertRaises)

`inspect`を使うのは、今回は「定義上キーワード専用であること」まで要求しているためです。実装の形を固定する必要がないAPIなら、その検査をそのまま持ち込まず、利用者に必要な振る舞いから考えます。

また、`TypeError`を確認するだけでは、一般の関数内部で偶然起きた同じ例外と区別できません。この例の関数本体は数値の加算だけです。複雑な関数へ応用する場合は、例外が起きる理由も確認対象にします。

## ファイル一つで、結果を確かめる

[再現コードの全文](https://github.com/RollNuts/zenn-content/blob/a127a99bc240e13f981dbccaa1a1dd1fa7b4a552/examples/api-contract-repair/repair_review.py)を開き、GitHubの「Raw」からコード本文を表示して、`repair_review.py`という名前で保存してください。[コード本文への直接リンク](https://raw.githubusercontent.com/RollNuts/zenn-content/a127a99bc240e13f981dbccaa1a1dd1fa7b4a552/examples/api-contract-repair/repair_review.py)も使えます。コードはコミットへ固定しています。

Python 3.12がある環境で、保存したディレクトリから実行します。ファイル取得後の実行に、Git、Core、AIモデル、アカウント、ネットワーク接続、追加パッケージは不要です。

まず、戻り値だけを検査します。

```sh
python3.12 repair_review.py --repair rollback --value-only
python3.12 repair_review.py --repair keyword --value-only
```

どちらも1テストが成功し、終了コードは0です。

次に、四つの検査をすべて実行します。

```sh
python3.12 repair_review.py --repair rollback
python3.12 repair_review.py --repair keyword
```

同じファイルをPython 3.12で実行して確認した結果です。

| 修正案 | 戻り値だけ | 全検査 | 全検査の終了コード |
| --- | --- | --- | ---: |
| 案A：`rollback` | 1件成功 | 4件中2件失敗 | 1 |
| 案B：`keyword` | 1件成功 | 4件成功 | 0 |

案Aでは、出力に次の二つの失敗が現れます。

```text
test_fee_is_keyword_only ... FAIL
test_positional_fee_is_rejected ... FAIL
```

上は失敗するテスト名と状態を抜き出したものです。実際の出力にはクラス名や失敗内容も付きます。

この2件の`FAIL`は、**案Aが今回の採用条件を満たしていないことを検出した結果**です。テストを外して緑にすると、その違いを確かめる手段まで失います。

一方、ファイルが見つからない、`SyntaxError`で止まる、4件のテストが実行されないといった結果は、この教材が意図した失敗ではありません。実行したテスト名と失敗理由まで照合します。

## 実際のレビューでは、採用条件を差分の横に置く

この例は小さいので、`*`の有無を見れば違いに気づけます。実際の変更では、関数、呼び出し側、テストが別のファイルに分かれていることもあります。

レビュー時には、次のメモで変更の目的と確認方法を対応付けられます。

```text
変更の目的：feeをキーワード専用にする
維持する使い方：total(100, fee=5)
拒否する使い方：total(100, 5)
要求の根拠：この演習で指定した3条件
確認方法：値、正常な呼び出し、引数の種類、拒否する呼び出しの4テスト
未確認：ほかの呼び出し元、境界値、実サービスの移行要件
```

実際の修正なら「要求の根拠」には、合意済みの仕様、Issue、移行方針などを置きます。根拠が見つからなければ、勝手に採用条件を補う前に、何を維持するのかを確認します。

既存テストと新しい要求が食い違うこともあります。その場合は、要求を変えるのか、実装を変えるのか、古い要求を表すテストを更新するのかを、根拠と一緒に判断します。失敗したという理由だけでは、どれを変えるべきかは決まりません。

AIにレビューを依頼する場合にも、このメモを添えられます。

```text
次の修正案を、変更目的とAPIの採用条件に照らして比較してください。

各条件を確認するテストと、まだ確認していない条件を示してください。
テストの変更を提案する場合は、変更する要求とその根拠も示してください。
要件が不明なら、不明な点を挙げて判断を保留してください。
実行していない検査は、未実行と書いてください。
```

これは依頼文の例です。この指示によってAIのレビュー精度が上がるかは、この記事では測っていません。

## この題材を選んだ背景

私がVeripsaを作り始めたきっかけは、複数の開発作業でGitのコンフリクトが頻発し、それを改善したかったことです。その過程で、コードの構造や変更同士の関係を調べる仕組みを作ってきました。

Gitのテキスト上の競合と、この記事で扱った関数の呼び出し契約は、確認する対象が異なります。今回の例はGitの競合を再現したものでも、Veripsaの検出能力を評価したものでもありません。

ここでは、コードを直した後に何を確認すればよいかを、解析ツールなしで試せる大きさへ絞りました。二つの修正が同じ105を返しても、残したい約束を満たすかは違う。その差を、自分で実行して確かめられる教材として残しています。

手元のレビューでも、「テストが通った」の次に、**「変更で守ると決めた約束を、そのテストで確認したか」**と一度問い直してみてください。

---

検証範囲は、この架空の二案と三つの要求、四つのテストです。境界値、すべての呼び出し元、一般的な修正の正しさ、AIによるバグ防止効果は検証していません。本記事と再現コードの整備・実行検証にはAIを利用しています。

再現コードとほかの実行例は、[RollNutsのGitHub](https://github.com/RollNuts/zenn-content)に置いています。CIの成功後に確認する対象を考えるなら、[CIは成功したのに本番が変わらないとき、どこを確かめるか](https://zenn.dev/veripsa/articles/ci-success-deployed-revision)でも、配信された内容を確かめる小さな例を扱っています。
