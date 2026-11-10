---
title: "CIは成功したのに本番が変わらないとき、どこを確かめるか"
emoji: "🚦"
type: "tech"
topics: ["githubactions", "cloudflare", "python", "個人開発"]
published: true
---

CIの画面は緑なのに、公開URLを開いても変更が見えない。こういうときは、キャッシュ削除から始める前に「何が成功したのか」を分けて確認すると、調べる場所を絞れます。

まず確認する順番は、**期待する版 → デプロイ先の環境 → 公開URLの応答 → 代表コンテンツ**です。HTTP 200だけでは、意図した版が配信されているかまでは分かりません。

この記事では、WebサイトをCI/CDで公開するときの切り分け方を、手元で再現できる3状態と、個人開発の公開確認ログで説明します。具体例はGitHub ActionsからCloudflare Workers Static Assetsへ配信する静的サイト、再現コードはPython 3.12の標準ライブラリです。

## 最初に「成功」の範囲を分ける

1. **CIの成功**：そのworkflowに何の手順が入っているか。テストまでか、成果物の生成・デプロイ・公開確認まで含むかを、jobとstepのログで確認する。
2. **デプロイ処理の成功**：意図した成果物を、意図した環境へ渡したか。対象のbranch、commit、環境、デプロイ履歴を確認する。
3. **公開応答の確認**：読者が使うURLが、期待した版と必要なコンテンツを返しているか。配信先の応答を取得して確かめる。

GitHub Actionsでも、[環境・デプロイ履歴・workflow runの監視](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)は別々に扱います。どれか1つの成功を、ほかの確認の代用にはしません。

ここでは、期待する新版をB、旧版をAとします。最初にこの3状態を見分けるのが目標です。

| 配信状態 | 版を示すmarker | 代表ページ | 確認結果 | 次に確認するもの |
| --- | --- | --- | --- | --- |
| 旧版のまま | A | A | 期待するBとは不一致 | デプロイ先・成果物・実行ログ・応答header |
| 一部だけ更新 | B | A | markerだけなら見落とす | 配信した成果物の組、HTML・assetの参照先と応答 |
| 両方を更新 | B | B | この2点では一致 | その変更で必要な残りのページ・asset・操作 |

この表だけで原因を確定するものではありません。たとえばA/Aでも、デプロイ待ち、対象環境の取り違え、失敗、キャッシュなど複数の可能性があります。

## 公開確認で固定するもの

確認対象を「mainの最新」だけで表すと、処理の途中でmainが進んだ際に期待値も動いてしまいます。最初に次の組を決めます。

| 項目 | 例 | 確認したいこと |
| --- | --- | --- |
| 期待する版 | 今回のmain pushの完全なコミットSHA | 何を届ける予定だったか |
| 対象環境 | 本番の公開URL | どこへ届ける予定だったか |
| 観測した版 | 公開URLから取得したmarkerの本文 | そのURLが何を返したか |
| 代表ページ | 変更したページの本文やasset | 読者に必要な変更が届いたか |

今回扱う公開repoはSHA-1のGit object formatなので、SHAは省略せず40桁で比較しています。短いSHAはログを読みやすくする表示用です。

## markerはビルドした成果物に含める

ビルドに使ったcheckoutで`git rev-parse HEAD`を実行し、その値を`build-revision.txt`へ書き出します。検証中にリモートのmainを取得して、markerだけを新しいSHAへ更新する手順にはしません。

```sh
# クリーンなcheckoutで、サイト生成に成功した後に実行する例
git rev-parse HEAD > dist/build-revision.txt
```

このファイルもHTMLや画像と同じ成果物として配信します。自分のサイトの実装では、生成スクリプトがcheckoutのSHAを読み取り、生成先へ書いています。SHAを取得できない場合は`unknown`となり、公開確認の完全一致を通過しません。

コミットSHAのstampは、成果物全体の暗号学的な証明ではありません。未commitの変更、ビルド時に取得する外部データ、環境変数や依存関係まで同一だとは保証しないため、ビルドの前提も別に揃える必要があります。

## 実際の反映待ちをログで見る

2026年11月8日の[公開確認run](https://github.com/RollNuts/mihassei-news/actions/runs/42476434759)には、次の記録が残っています。時刻はJST、SHAはこの表だけ省略表記です。

| 観測時刻 | 公開marker | 状態 |
| --- | --- | --- |
| 20:35:37 | `e1c91627…` | 旧版。1回目の確認 |
| 20:36:48 | `e1c91627…` | 旧版。15回目の確認 |
| 20:36:53 | `b53483c2…` | 今回の期待値と一致 |

最初の観測から一致まで約76秒あります。ただし、デプロイの開始や切り替わった瞬間を計測したものではないので、これをデプロイ所要時間とは呼んでいません。照合stepとrunは、一致を確認した後に成功しています。

これは公開確認のゲートが反映を待った記録です。「成功したと表示された後も古い版だった」という障害記録ではありません。どのチェックを通過したのかを分けて読む必要があります。

## HTTP 200でも失敗する例をローカルで作る

次の3状態を、外部サイトへアクセスしないHTTPサーバーで作ります。`a`と`b`を並べた40桁は説明用の架空のSHAです。

最初の表のA/A、B/A、B/Bを、ローカルの応答で確かめます。

どの状態でも、markerとページはHTTP 200を返します。markerだけを比較する検査では、2行目を見落とします。再現例では、代表ページへ埋め込んだrevisionと見出しも確認します。

完全な再現コードは[記事用repo](https://github.com/RollNuts/zenn-content/tree/2f51517aa4d7d29013146eb7e93e43c0c3d7b2c3/examples/deployment-revision)に置いています。次の手順で、この原稿で検証した版を実行できます。

```sh
git clone https://github.com/RollNuts/zenn-content.git
cd zenn-content
git checkout 2f51517aa4d7d29013146eb7e93e43c0c3d7b2c3
cd examples/deployment-revision
python3.12 test_check_release.py
python3.12 -m unittest -v test_check_release.py
```

照合するスクリプトは次のとおりです。期待するSHAを引数に取り、完全一致したmarkerと代表HTMLの両方を確認します。

:::details 照合スクリプトの全体（必要な場合に開く）

```python:check_release.py
"""Small read-only example: pin a revision and inspect public response bytes."""
import argparse
import re
import time
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ReleasePage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.revisions, self.headings, self.current = [], [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name") == "build-revision":
            self.revisions.append(attrs.get("content"))
        if tag == "h1":
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "h1" and self.current is not None:
            self.headings.append(" ".join("".join(self.current).split()))
            self.current = None


def fetch(url, content_type):
    request = Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "ReleaseDemo/1.0"})
    with build_opener(NoRedirect()).open(request, timeout=3) as response:
        if response.status != 200 or response.headers.get_content_type() != content_type:
            raise ValueError("Unexpected status or Content-Type: " + url)
        body = response.read(65537)
    if len(body) > 65536:
        raise ValueError("Response exceeds this example's 64 KiB limit")
    return body.decode("utf-8")


def check_release(base, expected, heading):
    parts = urlsplit(base)
    local = parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}
    if not parts.hostname or (parts.scheme != "https" and not local):
        raise ValueError("Use HTTPS, or HTTP on loopback for the local demo")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Base URL must have no credentials, query or fragment")
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise ValueError("This SHA-1 repository example requires a full lowercase 40-hex revision")
    base = base.rstrip("/") + "/"
    marker = fetch(urljoin(base, "build-revision.txt?release=" + expected), "text/plain").strip()
    if marker != expected:
        observed = marker if re.fullmatch(r"[0-9a-f]{40}", marker) else "<invalid marker>"
        raise ValueError(f"Revision marker mismatch: expected={expected} observed={observed}")
    page = ReleasePage()
    page.feed(fetch(urljoin(base, "?release=" + expected), "text/html"))
    if page.revisions != [expected] or page.headings != [heading]:
        raise ValueError("Representative HTML does not match the expected release")


def wait_for_release(base, expected, heading, attempts=3, delay=1):
    if not 1 <= attempts <= 30 or not 0 <= delay <= 30:
        raise ValueError("Use 1..30 attempts and 0..30 seconds between attempts")
    for attempt in range(1, attempts + 1):
        try:
            check_release(base, expected, heading)
            return attempt
        except (ValueError, URLError, TimeoutError, OSError) as error:
            print(f"Attempt {attempt}/{attempts}: {error}", flush=True)
            if attempt == attempts:
                raise
            time.sleep(delay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("expected")
    parser.add_argument("heading")
    args = parser.parse_args()
    try:
        wait_for_release(args.base, args.expected, args.heading)
    except (ValueError, URLError, TimeoutError, OSError) as error:
        parser.exit(1, f"Not verified: {error}\n")
    print("Verified revision marker and representative HTML")
```

:::



実行結果の要約です。実際のコマンドは、各GETのパスとHTTP statusもJSONで出力します。

```text
old release A: all HTTP 200 -> rejected
mixed marker B / HTML A: all HTTP 200 -> rejected
release B: all HTTP 200 -> accepted
```

追加のケースを含む13テストも通過しました。CLIでは、一致時の終了コード0、旧版や不正な期待値の終了コード1を検査しています。

ここで検査したのはmarkerと代表ページ1枚です。実際のサイトでは、変更内容に合わせて画像のdigest、CSS/JavaScriptの参照先、記事本文、RSSなども確認対象へ加えます。自分のサイトでも、markerの照合後に本文や配信assetを読む検査を続けています。

この教材を自分の環境へ持ち帰る場合は、markerに加えて、トップページにも次のようなmetaと見出しを用意します。これは架空のBの例です。実際にはビルド時のSHAと、その変更で期待する見出しへ置き換えます。

```html
<!doctype html>
<meta name="build-revision" content="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb">
<h1>Release B</h1>
```

照合の呼び出し方は次の形です。URLは自分が確認する環境へ置き換えます。

```sh
python3.12 check_release.py https://example.invalid/ bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 'Release B'
```

この小さいcheckerはmetaと`h1`がそれぞれ1つあるページに限定しています。複数の見出しを持つページや、JavaScriptで本文を生成するサイトでは、そのサイトに合う代表コンテンツの検査へ変更します。

## 反映待ちには上限を付ける

公開URLが旧版を返している理由は、デプロイ処理中、配信対象の設定違い、ビルド失敗、キャッシュなど複数あります。revisionの不一致だけで原因をキャッシュへ決めつけることはできません。

自分の公開workflowは、1回の取得timeout、試行回数、待機間隔を決め、上限まで一致しなければ失敗として終了します。最後に観測した値と期待値を残すと、後から「URLに届かなかった」のか「届いたが旧版だった」のかを切り分けやすくなります。

検証中に新しいmain pushが来た場合は、古い版を待つ検証を取り消し、新しい版の検証へ移ります。GitHub Actionsでは、この検証workflowに次の設定を置いています。

```yaml
on:
  push:
    branches: [main]

concurrency:
  group: verify-live-production-main
  cancel-in-progress: true
```

これは古い検証の取り消しを制御する設定です。別サービスのデプロイ順序や公開の原子性まで保証するものではありません。

期待値に使う`${{ github.sha }}`の意味は、workflowを起動したeventによって変わります。上の例はmainへのpushに限定しています。pull requestの検証用merge commitや、別refをcheckoutしたjobへ同じ前提を持ち込まないようにします。

## markerのキャッシュ設定も確認する

Workers Static Assetsでは、出力ディレクトリの`_headers`でmarkerの応答を指定できます。

```text:_headers
/build-revision.txt
  Cache-Control: no-store
```

`no-store`は応答を保存させない指定で、`no-cache`は再利用の前に再検証を求める指定です。どちらを指定したかだけで全経路の即時更新を保証したとは扱いません。確認時には実際の応答headerも読みます。

なお、`_headers`の設定はWorkerコード自身が生成する応答には適用されません。その経路でmarkerを返す場合は、Workerの応答側でheaderを設定します。

## どこまで確認できたかを残す

自分が公開完了と扱うときは、「どのURLで、いつ、どのSHAと、どの代表コンテンツを確認したか」を記録します。marker一致だけで、全ページ、全CDN拠点、ブラウザ内の状態、操作の成功まで確認したことにはしません。

ほかの配信基盤へ持ち帰るときも、期待値・対象環境・観測した版・代表コンテンツの組を固定する考え方は使えます。版の識別子や確認方法は、GitのSHA、コンテナimage digest、release versionなど、その仕組みに合わせて選びます。この記事の40桁SHAやCloudflare設定を、そのまま全環境へ適用するものではありません。

小さいサイトなら、まずはビルドしたcheckoutのSHAを書き出し、公開URLから完全一致を確認するところから始められます。そのうえで、その変更に必要な本文やassetの検査を一つずつ加えていきます。

公開repoの実装（この記事で確認したcommitに固定）:

- [ビルドしたHEADの取得](https://github.com/RollNuts/mihassei-news/blob/b53483c2b332ca47afef1a5e91fd8024e18e571c/scripts/build.py#L2118)
- [markerの生成](https://github.com/RollNuts/mihassei-news/blob/b53483c2b332ca47afef1a5e91fd8024e18e571c/scripts/build.py#L2194)
- [main pushのSHAと公開応答の照合](https://github.com/RollNuts/mihassei-news/blob/b53483c2b332ca47afef1a5e91fd8024e18e571c/.github/workflows/verify-public-photos.yml#L22)
- [marker照合後の実コンテンツ検査](https://github.com/RollNuts/mihassei-news/blob/b53483c2b332ca47afef1a5e91fd8024e18e571c/scripts/check_live.py#L570)

公式資料:

- [GitHub Actionsのcontexts reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts)
- [GitHub Actionsのconcurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [Cloudflare Workers Static AssetsのHeaders](https://developers.cloudflare.com/workers/static-assets/headers/)
- [Cloudflare Cache-Control](https://developers.cloudflare.com/cache/concepts/cache-control/)

関連記事: [創作上の2031年をRSSに流さない――静的サイトで3つの日時を分ける](https://zenn.dev/veripsa/articles/fiction-date-rss-static-site)

この記事の下書き作成と、コード・公開ログの確認にはコーディングエージェントを利用しています。
