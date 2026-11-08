# 配信中のrevisionをHTTP応答で確認する最小例

Python 3.12の標準ライブラリだけで、期待したrevisionと公開応答を比較する教材です。
テストは`127.0.0.1`の一時ポートへだけ接続します。外部サイトや本番環境は変更しません。

## 試す

このディレクトリで実行します。

```sh
python3.12 test_check_release.py
python3.12 -m unittest -v test_check_release.py
```

最初のコマンドは、次の3状態をJSONで表示します。すべての取得応答はHTTP 200です。

| marker | 代表HTML | Bの公開確認 |
| --- | --- | --- |
| A | A | 失敗 |
| B | A | 失敗 |
| B | B | 成功 |

AとBは`a`と`b`を40個並べた架空のSHAです。GitやGitHubへの認証は不要です。
2番目のコマンドは、上の状態に加えて、見出し不一致、404、redirect、取得量上限、
不正な期待値、retry上限、途中での一致、CLIの終了コードを検査します。

## 検証先を指定する

```sh
python3.12 check_release.py https://example.invalid/ FULL_40_HEX_SHA 'Release B'
```

`example.invalid`は説明用のURLです。実サイトで使うときは、自分が確認する環境へ置き換えます。
対象サイトには次を同じビルドの成果物として用意します。

- `build-revision.txt`：完全なSHA1つと改行。
- トップページ：`<meta name="build-revision" content="完全なSHA">`と、期待する見出しの`h1`1つ。

期待値は実行中に変更しません。一致すれば終了コード0、確認できなければ1です。
HTTPSを使い、ローカル再現時だけloopbackのHTTPも受け付けます。redirectは追いません。

## この教材の範囲

- SHA-1形式のGit repoを想定し、40桁の小文字hexを完全一致で比較します。
- markerはビルド元のstampです。署名付きprovenanceや成果物全体の真正性の証明ではありません。
  クリーンなcheckoutをビルドし、markerだけを後から書き換えない前提です。
- 代表HTMLのmetaと、HTMLとして解析した`h1`の文字列だけを調べます。
  JavaScriptの実行、CSSによる表示、画面操作、全asset、全ページ、全CDN拠点は確認しません。
- `no-cache`の要求やquery追加は、キャッシュを必ず回避できた証拠にはしません。取得した値を比較します。
- 1回の取得timeoutは3秒、応答bodyは64 KiBまでです。標準で3試行、間隔1秒です。
  socketのtimeoutは厳密な全体の経過時間上限ではありません。
- 新しいmainの公開が旧版を置き換える場合の方針は、デプロイ元のworkflowで決めます。
  このスクリプトはmainを取得し直したり、デプロイの順序を制御したりしません。

元のサイトの実装は[未発生新聞](https://github.com/RollNuts/mihassei-news)で公開しています。
この教材は、そこで使うrevision照合の考え方を説明するために独立して作った小さい例です。
