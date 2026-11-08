---
title: "創作上の2031年をRSSに流さない――静的サイトで3つの日時を分ける"
emoji: "📰"
type: "tech"
topics: ["python", "rss", "静的サイト"]
published: true
---

創作サイトの画面には、現実と違う日時を載せたくなることがあります。その表示日時をRSSや検索向けのメタデータにも使うと、作品内の演出が実際の公開日時として流れてしまいます。

未発生新聞は「5年後の小さな珍事」を新聞として読むサイトです。この実装では、日時を用途別に持ち、ページの見た目と外部配信で使い分けています。この記事では、その境界だけを取り出します。静的サイトや架空世界の作品ページを作る人向けです。

## 1つの記事に3つの日時を持たせる

- `published_at`: 実際に記事を初めて公開した日時
- `fiction_at`: 紙面上で演出する架空の日時
- `source.published_at`: 着想元の資料が公開された日時

たとえば、実公開が2026年11月8日、着想元の資料が11月7日、紙面上の年が2031年という記事です。この3つは意味が違うため、一方を残りの代用にしません。

新しい記事では3フィールドを必須にし、fiction_atが実公開の月日・時刻・タイムゾーンを保って5年先になっていることも読み込み時に検査しています。日付を変換できないケースは、表示する側で都合よく補正するのではなく、データ側のルールとして判断する必要があります。

## RSSには実公開の日時を渡す

記事の並び順とRSSのpubDateにはpublished_atを使います。fiction_atは紙面の表示用です。source.published_atは資料の来歴として記事に残します。

考え方を小さいコードにすると、次のようになります。これは説明用の独立した例で、リポジトリの関数をそのまま転載したものではありません。

```python
from datetime import datetime
from email.utils import format_datetime, parsedate_to_datetime

article = {
    "published_at": "2026-11-08T09:00:00+09:00",
    "fiction_at": "2031-11-08T09:00:00+09:00",
}
pub_date = format_datetime(datetime.fromisoformat(article["published_at"]))

assert parsedate_to_datetime(pub_date).isoformat() == article["published_at"]
assert "2031" not in pub_date
```

この例で検査しているのは「日付文字列が作れたこと」だけではありません。外部へ渡す値が、実公開日時へ戻せることを確かめています。

## HTMLとRSSを別々に検査する

未発生新聞のテストでは、RSSのpubDateを再び日時として解析して、記事の実公開日時と比較しています。架空の年がpubDateへ混ざっていないことも確認します。ページ側の構造化データのdatePublishedも、fiction_atと区別しています。

生成前のJSONを見ただけでは、テンプレートやRSS生成器の取り違えまでは分かりません。生成物を読む検査があると、画面の演出を変えた際に外部向けの日時まで変えてしまうのを見つけやすくなります。

## 自分のサイトへ持ち帰るなら

先に「読者に見せる日時」「実際に公開した日時」「参照元の日時」を書き出し、それぞれの出力先を決めます。そのうえで、RSS・サイトマップ・構造化データの生成物を再解析して、意図した日時が入ることを検査します。未来設定の作品に限らず、再掲記事や資料紹介でも用途が分かれる箇所です。

実装の参照先:

- [サイト生成の実装（build.py）](https://github.com/RollNuts/mihassei-news/blob/3b701248b99608bd273bac3564abcfebf24b2baa/scripts/build.py)
- [生成物のテスト（test_site.py）](https://github.com/RollNuts/mihassei-news/blob/3b701248b99608bd273bac3564abcfebf24b2baa/tests/test_site.py)
- [技術構成（ARCHITECTURE.md）](https://github.com/RollNuts/mihassei-news/blob/3b701248b99608bd273bac3564abcfebf24b2baa/docs/ARCHITECTURE.md)

この記事の下書き作成と、記載した手順・コードの再現確認にはコーディングエージェントを利用しています。

---

未発生新聞のコードと構成を公開しています。実装を後で見返したい方はGitHubのStarで保存できます。ソフトウェアの再利用ライセンスは未設定です。

[未発生新聞のGitHubリポジトリ](https://github.com/RollNuts/mihassei-news)

同じrepoの運用記録: [git branch --mergedに出ない取り込み済みブランチを見分ける――556本を整理した実例](https://zenn.dev/veripsa/articles/github-branch-cleanup-squash-556)
