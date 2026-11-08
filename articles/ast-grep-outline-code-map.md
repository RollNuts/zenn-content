---
title: "AIに全文を渡す前に、ast-grep outlineでコードの目次を作る"
emoji: "🗺️"
type: "tech"
topics: ["ast", "typescript", "cli", "個人開発"]
published: true
---

知らないrepoをAIと読むとき、最初に知りたいのは「どのファイルの、どの部分を読むか」です。関数名やクラスの構成が分かれば、そこから本文を開けます。

GitHubの紹介候補を調べる中で、[ast-grep](https://github.com/ast-grep/ast-grep)の`outline`を試しました。自分で作ったTypeScript 3ファイルを使い、ファイルとディレクトリの既定値、公開要素への絞り込み、出力へ残る情報を確認します。

**検証した版はast-grep 0.51.1、Python 3.12、macOSです。** `outline`は公式にexperimentalとされる機能です。この記事のコマンドと結果はこの版に固定します。[公式ガイド](https://ast-grep.github.io/guide/outline-code)

## 3ファイルだけ用意する

サンプルは、商品型と検索用クラス、ラベル生成、再exportの入口を分けました。架空の小さいコードで、実際の製品コードや認証情報は含めていません。

```text
src/
  catalog.ts   商品型、クラス、内部関数、定数
  label.ts     型をimportしてラベルを作る
  index.ts     ほかのファイルから再exportする
```

`catalog.ts`の全文です。

```ts:src/catalog.ts
export interface Product {
  sku: string;
  price: number;
}

function normalizeSku(value: string): string {
  return value.trim().toUpperCase();
}

export class Catalog {
  private products: Product[];

  constructor(products: Product[]) {
    this.products = products;
  }

  lookup(sku: string): Product | undefined {
    const normalized = normalizeSku(sku);
    return this.products.find((product) => product.sku === normalized);
  }

  private isEmpty(): boolean {
    return this.products.length === 0;
  }
}

export const API_BASE = "https://example.invalid/catalog";

// export function commentOnly() { return "not a declaration"; }
const explanation = "export function stringOnly() {}";
```

ここでは、exportしていない関数、privateメンバー、export定数を意図的に混ぜています。末尾には宣言のように見えるコメントと文字列も置きました。

完全なサンプルと検証スクリプトは[記事用repoの再現コード](https://github.com/RollNuts/zenn-content/tree/11e8c3ae649d2775497b9e2dd6de75be9258fd12/examples/ast-grep-outline)に置いています。

## 隔離した環境へ版を固定して入れる

サンプルのディレクトリで実行します。以下はmacOS/Linuxのパス表記です。Windowsでは仮想環境の`Scripts`内を指定します。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: ast-grep-cli==0.51.1
.venv/bin/ast-grep --version
```

今回の出力は`ast-grep 0.51.1`でした。TypeScriptのコンパイルやnpm依存の導入は、このサンプルには不要です。CLIの別の導入方法は[公式Quick Start](https://ast-grep.github.io/guide/quick-start.html)にあります。

## ファイルとディレクトリで既定値が変わる

まず1ファイルを指定します。

```sh
.venv/bin/ast-grep outline src/catalog.ts
```

```text
src/catalog.ts
 1: export interface Product {
      field: sku, price
 6: function normalizeSku(value: string): string {
10: export class Catalog {
      method: lookup, isEmpty
      constructor: constructor
      field: products
27: export const API_BASE = "https://example.invalid/catalog";
30: explanation = "export function stringOnly() {}"
```

exportしていない`normalizeSku`や`explanation`も見えます。`commentOnly`と`stringOnly`が独立した関数として抽出されることはありません。ただし、文字列の中身が出力からすべて消えるわけでもありません。

同じコードをディレクトリ単位で見ると、次の出力になりました。

```sh
.venv/bin/ast-grep outline src
```

```text
src/catalog.ts
class: Catalog
interface: Product
constant: API_BASE

src/index.ts
module: "./catalog" ×2, "./label"

src/label.ts
function: productLabel
```

ディレクトリではexport要素の名前が中心になり、内部関数は見えなくなります。コードが消えたのではなく、見る範囲と表示の既定値が変わっています。今回の入力で確かめた使い分けは次のとおりです。

| 最初の目的 | コマンドの指定 |
| --- | --- |
| ファイル内部の構成を知る | `outline src/catalog.ts` |
| ディレクトリの公開要素を探す | `outline src --items exports` |
| import文を見る | `outline src/label.ts --items imports` |
| クラスの直接のメンバーを見る | `outline src/catalog.ts --match Catalog --view expanded` |

目次から候補を見つけた後は、その行の本文へ戻ります。たとえば`lookup`が見つかれば、そこで内部関数をどう呼んでいるかを読む、という順にできます。

## 公開メンバーに絞っても、定数の値は残る

次に、export要素と公開メンバーへ絞ります。

```sh
.venv/bin/ast-grep outline src/catalog.ts --items exports --view expanded --pub-members
```

```text
src/catalog.ts
 1: export interface Product {
 2:   sku: string
 3:   price: number
10: export class Catalog {
13:   constructor(products: Product[]) {
17:   lookup(sku: string): Product | undefined {
27: export const API_BASE = "https://example.invalid/catalog";
```

privateの`products`と`isEmpty`は消えました。一方、`API_BASE`のURLはそのままです。今回は説明用ドメインですが、自分のコードで共有用の出力を作るときに見落としたくない点です。

`--pub-members`が選ぶのは構文上のメンバーの公開範囲です。出力の秘匿化を行う指定ではないため、パス、シンボル、宣言の値も含めて、共有する実出力を確認します。「全文を出さない」ことと「機密情報を含まない」ことは別に確かめる必要があります。

## importと再exportは、構文の入口として読む

`label.ts`は次の型をimportしています。

```ts
import type { Product } from "./catalog";
```

`--items imports`でこの宣言を取り出せました。一方、`index.ts`の次の記述を`--items all --view expanded`で見ても、再export先の`Catalog`のメンバーまで展開されません。

```ts
export { Catalog } from "./catalog";
export type { Product } from "./catalog";
export { productLabel } from "./label";
```

出力にあるmoduleの行から対象ファイルを開き直せますが、型や実際の参照先、呼び出し関係が解決されたとは扱いません。この区別は、目次をAIへ渡す場合も同じです。

## 結果を7条件で確認する

見やすさだけの感想で終わらせず、この小さい入力で期待する出力を検査する`verify.py`も用意しました。

```sh
.venv/bin/python verify.py --ast-grep .venv/bin/ast-grep
```

今回、次の7条件が通り、終了コードは0でした。

1. ファイルの既定表示には内部宣言があり、コメント・文字列内の偽の関数名は独立した項目にならない。
2. ディレクトリの既定表示ではexport要素へ絞られる。
3. 公開メンバーに絞るとprivateメンバーが消え、export定数の値は残る。
4. 型のimport宣言が表示される。
5. 再export先のクラスメンバーへ展開されない。
6. `--match isEmpty`ではトップレベル要素が選ばれず、`--match Catalog --view expanded`でクラスのメンバーを見られる。
7. JSONの行番号は0始まりで、byte rangeが元のfixtureを指す。

全観測のJSONを保存する場合は`--report observations.json`を付けます。`verify.py`は版が違う場合に停止するので、将来の版で動かすときは実出力と条件を見直してください。

今回の確認はTypeScript 3ファイルの範囲です。大きいrepoでの速度や、token・費用の削減率、AIのタスク成功率は測っていません。自分のコードへ適用するときも、目次で読む場所を選び、本文や必要な解析ツールで確かめる順に使います。

[再現コードとREADME](https://github.com/RollNuts/zenn-content/tree/11e8c3ae649d2775497b9e2dd6de75be9258fd12/examples/ast-grep-outline)には、3ファイルと検証手順をまとめています。

この記事は、GitHub上の候補調査と独立したサンプルの実行をもとに、コーディングエージェントの補助で執筆・検証しています。
