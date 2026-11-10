---
title: "Webhookを再試行してよい？COMMITの応答が消えたときの3つの分岐"
emoji: "🔁"
type: "tech"
topics: ["python", "webhook", "postgresql", "testing"]
published: false
---

WebhookのハンドラーがDBを更新し、COMMITを送ったところで接続エラーになった。同じ処理をもう一度実行してよいでしょうか。

**応答が届かなかったことから、DBの変更が確定しなかったとは判断できません。** 確定済みなら再実行による重複が問題になり、未確定なら成功扱いにできません。さらに、確認中に別の実行へ処理する権限が移っている場合も考える必要があります。

この記事では、自作の[Veripsa Core](https://github.com/RollNuts/veripsa)の公開テストを題材に、呼び出し側の判断を3つに分けます。DBやWebhookの送信先を用意せず、接続と確認結果をfakeへ置き換えて動かします。

## 例外・完了状態・権限を分ける

題材の実装は、本体の更新と配信の完了記録を同じトランザクションへ載せます。完了記録の準備後にCOMMIT周辺で例外が出た場合、その例外を保持して確認処理へ進みます。[トランザクションの終端処理はこちらです。](https://github.com/RollNuts/veripsa/blob/b924add83e77972b6d09268f4eaab87e5b65b103/github-app/event_processor.py#L355-L396)

確認結果を受け取るラッパーの分岐は次のとおりです。

| fakeで与える確認結果 | ラッパーの応答 | ラッパーによる追加のfinish／release |
| --- | --- | --- |
| `committed` | 正常に戻る | 呼ばない |
| `queued` | 元のCOMMIT例外を再送出 | 呼ばない |
| `ownership_lost` | 元のCOMMIT例外を再送出 | 呼ばない |

これは特定実装の分岐表です。**`FakeStore`は確認結果をあらかじめ指定した値で返します。** このテストだけで、本物のDBからその状態を正しく判定できるとは言えません。[fakeの定義](https://github.com/RollNuts/veripsa/blob/b924add83e77972b6d09268f4eaab87e5b65b103/tests/test_atomic_delivery_finalize.py#L62-L158)と[ラッパーの分岐](https://github.com/RollNuts/veripsa/blob/b924add83e77972b6d09268f4eaab87e5b65b103/github-app/delivery_queue.py#L1444-L1468)を分けて読みます。

### 1. committed：応答を失っただけなら成功へ戻す

`FakeConnection`が「確定したが応答を失った」状況を模し、確認結果に`committed`を与えます。この条件では、ラッパーは正常に戻ります。

テストではキューの`processed`が1、`failed`と`retried`が0になります。例外が出たという理由だけで、この処理を再び未完了扱いにしない分岐です。

ただし、ハンドラーの呼び出し数の検査は「1回以上」です。処理全体が必ず1回しか実行されない、という証明には使えません。

### 2. queued：完了の準備を、確定した証拠にしない

次は確定前の失敗を模し、確認結果に`queued`を与えます。完了記録がトランザクション内に準備されていても、成功とは扱いません。

元の例外を再送出し、テストはメッセージの一致だけでなく、例外が同じオブジェクトであることを`is`で確認します。ここで照会エラーなどへ置き換えると、最初に何が失敗したかが分かりにくくなります。

このケースが確かめるのはラッパーの応答です。将来キューから再試行されるか、いつ再試行してよいかは別の条件です。「queuedなら今すぐ安全に再実行できる」とも、「今後は一切再試行しない」とも結論づけません。

### 3. ownership_lost：仕事の一致と、操作する権限を分ける

同じ配信キーでも、今の実行が状態を変更してよいとは限りません。処理権限を失った古い実行が後始末すると、別の実行を妨げる可能性があります。

テストは世代番号19を渡し、確認結果に`ownership_lost`を与えます。確認へその世代が渡り、ラッパーから追加の`finish`や`release`を呼ばず、元の例外を保つことを確認します。

世代番号の偽造防止、世代交代の競合、DB側の排他処理を再現したテストではありません。**権限を失ったという結果を受け取った側が、成功扱いや追加の変更へ進まないこと**を確かめています。

## DBなしで4チェックを動かす

POSIXのシェル、Git、Python 3.12が前提です。検証に使った環境はmacOS、Python 3.12.13、`psycopg2-binary` 2.9.13です。標準ライブラリだけでは動きません。次の公開commitへ固定します。

```sh
git clone https://github.com/RollNuts/veripsa.git veripsa-commit-demo
cd veripsa-commit-demo
git checkout --detach b924add83e77972b6d09268f4eaab87e5b65b103
python3.12 -m venv .venv
.venv/bin/python -m pip install psycopg2-binary==2.9.13
```

cloneと依存の取得には通信を使います。検証には既存のインストール済み環境を使っており、この新規インストール手順自体は今回再実行していません。以下の演習にはDBやAPIキーは不要です。

Coreのcheckoutルートで、既存テストの2関数だけを呼びます。実接続用の2つの入口を拒否し、失敗カウンターも検査します。

```sh
.venv/bin/python -B - <<'PY'
import runpy
import socket
import psycopg2

attempts = []

def deny(*args, **kwargs):
    attempts.append(True)
    raise AssertionError("real connection is outside this fake-only test")

psycopg2.connect = socket.create_connection = deny
m = runpy.run_path("tests/test_atomic_delivery_finalize.py")
h = m["Harness"]()
h.install()
try:
    m["test_ack_loss_is_processed"](h)
    m["test_uncommitted_and_aba_preserve_original"](h)
finally:
    h.restore()

assert not attempts
assert m["check"].__globals__["FAIL"] == 0
PY
```

`runpy`の返却辞書にある`FAIL`ではなく、`check`関数が実際に更新するグローバル変数を見ます。テストは失敗を表示してもその場で例外を投げないため、この検査が必要です。

3ケースに加え、確認処理自体が失敗しても元の例外を保つチェックがあります。既存環境でネットワークを無効にして実行した結果は、**4件PASS、実際の失敗カウンター0、上でガードした実接続呼び出し0件**でした。[実行した2関数の全文はこちらです。](https://github.com/RollNuts/veripsa/blob/b924add83e77972b6d09268f4eaab87e5b65b103/tests/test_atomic_delivery_finalize.py#L278-L362)

なお、別ファイルの`tests/test_delivery_commit_resolution.py`は実DBを初期化・削除する統合検証です。この演習では実行しません。接続入口の差し替えも、任意のPythonコードを隔離するネットワークsandboxではありません。

## この結果を実装レビューへ持ち帰る

再試行を考えるときは、「どこで例外が出たか」「何を根拠に完了を確認するか」「どの実行が状態を変更してよいか」を別々に書いてみます。今回なら、COMMIT周辺の例外、fakeが返す確認結果、配信キーと世代、という3点です。

今回確認したのは呼び出し側の分岐です。実DBの永続化、確認SQLの正しさ、外部APIへの副作用、処理全体のexactly-onceや実運用の障害回避を証明していません。ホスト型GitHub Appの稼働を報告するものでもありません。

CoreはBSL 1.1のsource-availableです。コードの再利用条件は[固定版のLICENSE](https://github.com/RollNuts/veripsa/blob/b924add83e77972b6d09268f4eaab87e5b65b103/LICENSE)を確認してください。本記事の作成にはAIを使い、説明を公開ソースと実行記録に照合しています。

---

再現コードや公開中の個人開発は、[RollNutsのGitHub](https://github.com/RollNuts)から辿れます。記事が役立ったら、有料バッジで今後の検証を応援してもらえると嬉しいです。
