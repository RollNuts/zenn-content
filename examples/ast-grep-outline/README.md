# ast-grep outlineの小さい再現例

公開記事用に独立して作ったTypeScript 3ファイルを、ast-grep 0.51.1で調べます。
私有プロジェクトのコードや実際の認証情報は使っていません。URLは`example.invalid`です。

Python 3.12と、対象OS向けのast-grep CLIが必要です。TypeScriptのビルドやnpm依存は不要です。

新しい作業ディレクトリで再現コードを取得し、検証対象のコミットへ固定します。

```sh
git clone https://github.com/RollNuts/zenn-content.git
cd zenn-content
git checkout --detach 11e8c3ae649d2775497b9e2dd6de75be9258fd12
cd examples/ast-grep-outline
```

このサンプルのディレクトリで次を実行します。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: ast-grep-cli==0.51.1
.venv/bin/ast-grep --version
.venv/bin/python verify.py --ast-grep .venv/bin/ast-grep
```

これはmacOS/Linux向けのパス表記です。Windowsでは仮想環境の`Scripts`内を指定します。
CLIの配布方法と対象OSは[公式Quick Start](https://ast-grep.github.io/guide/quick-start.html)で確認できます。

## 自分で出力を読む

```sh
.venv/bin/ast-grep outline src/catalog.ts
.venv/bin/ast-grep outline src
.venv/bin/ast-grep outline src/catalog.ts --items exports --view expanded --pub-members
.venv/bin/ast-grep outline src/label.ts --items imports
.venv/bin/ast-grep outline src/index.ts --items all --view expanded
```

ディレクトリを指定した場合、ファイルの表示順は実行ごとに変わることがあります。
記事のディレクトリ出力例は、比較しやすいようにファイルごとにパス順へ並べています。

`verify.py`は次を実CLIのJSON出力と照合し、7条件が通れば終了コード0で要約を表示します。
全観測を保存する場合は`--report observations.json`を追加します。

- ファイルの既定表示には、exportしていないローカル宣言も出る。
- ディレクトリの既定表示はexport要素に絞られる。
- `--pub-members`はprivateメンバーを隠すが、export定数の値は残る。
- import文は表示できる。
- 再export先のクラスメンバーを辿って展開するわけではない。
- `--match`はトップレベル要素を選び、メンバー名の検索にはならない。
- JSONの行番号は0始まりで、byte rangeは元のfixtureを指す。

`outline`は実験的機能です。版が変わったときは、失敗した条件と実出力を確認してください。
型や参照先、call graph、動的な読み込み先を解決するツールではありません。
出力にはパス、シンボル、宣言の値も含まれるので、共有前に実際の出力を確認します。
秘密情報を除去するフィルターとしては使いません。

今回の小さい入力で使い分けを確かめる教材です。大規模repoでの性能、token削減率、
AIのタスク成功率、ネットワーク動作の監査を行ったという意味はありません。

仕様の参照先: [Outline Code](https://ast-grep.github.io/guide/outline-code)
