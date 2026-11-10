# 実際の変更の前に、確認先を探せるか

Veripsa CoreのコードグラフとCo-changeを、Flaskの既存の小さな変更3件で確かめるローカル実験です。各変更の**直前のcommit**だけを解析し、ソースを読んで先に選んだ5つの確認先が候補に含まれるかを調べます。

例えば、テンプレートの拡張子判定を変更するとき、その判定関数をJinja環境へ渡すファイルも一緒に確認したくなります。変更コミットで同時に編集されたファイルだけを正解にすると、このような未変更の利用箇所を評価できません。この実験は、変更ファイル一覧と、実装上の確認理由を分けます。

これは小さい**確認先チェックリストの包含調査**です。一般的な精度、将来の障害予測、PRの安全性、作業時間短縮を測るベンチマークではありません。ホスト型GitHub Appは停止中で、今回も利用しません。

## 手元で再現する

Git、Python 3.12、POSIX環境（macOS／Linux）が必要です。追加のPythonパッケージ、Flaskのインストール、DB、モデルAPI、アカウント認証は不要です。Windowsは検証対象外です。

空のディレクトリで、履歴を省略しないfull cloneを用意します。

```sh
git clone https://github.com/RollNuts/veripsa.git
git clone https://github.com/pallets/flask.git
git clone https://github.com/RollNuts/zenn-content.git
python3.12 zenn-content/examples/core-change-review/review.py \
  --core veripsa --flask flask --check
```

cloneはGitHubへ接続します。解析コマンドはローカルのGitオブジェクトだけを読み、ネットワークを使いません。Coreは固定commitから一時ディレクトリへ取り出し、Flaskも一時コピーを解析します。元のcloneのHEAD、作業ファイル、設定を変更しません。Flaskのコードやテストを実行する処理もありません。

独自のGitが必要なら`--git /path/to/git`を指定します。`--check`は、測定された候補と保存済みの期待JSONが一致するかを検査します。確認先をすべて見つけることや、Flaskのテストが通ることを成功条件にはしていません。

## 固定した入力と確認理由

- Core：[`4236848`](https://github.com/RollNuts/veripsa/tree/4236848504c8cb2cc3c14db22408fb519b06f754)。既存の抽出器、オフラインの粗いfile-pair投影、`_cg_cochange.cochange_pairs`を再利用し、解析アルゴリズムやしきい値を変更しません。
- Flask：[`49943b5`](https://github.com/pallets/flask/tree/49943b5a94413a530761350f04e896f76e8d620e)に含まれる3変更。その先の履歴は測定に使いません。
- ケースと根拠：[`cases.json`](cases.json)。Graph／Co-changeの結果を見る前に、別のAI支援レビューで確認先を選定しました。独立した人間の正解ラベルとは呼びません。

| 変更 | 起点 | 変更前から存在する確認先 |
| --- | --- | --- |
| 拡張子の大文字小文字とautoescape | `src/flask/sansio/app.py` | 判定関数を環境へ渡す`src/flask/app.py` |
| IPv6とsession transaction | `src/flask/testing.py` | 既存のtransactionテスト、session保存の実装 |
| 呼び出しごとのrequest context copy | `src/flask/ctx.py` | 公開APIの再export、既存のdecorator利用テスト |

各ケースで`target`のfirst parentが`base`と一致することを検査します。グラフのソースもCo-changeの`HEAD`も`base`です。対象変更やその後の変更を、解析履歴へ混ぜません。変更後のソースや差分は、確認理由を読むための資料としてだけ使います。

候補範囲は、その`base`に存在する`src/flask/**/*.py`と`tests/**/*.py`です。全repoに対して既存producerを実行した**後**で範囲を絞ります。Co-changeの履歴800件、巨大commit除外、既定しきい値、順位と上限を、候補範囲に合わせて計算し直すことはありません。

## 結果を読む

2026-11-09、macOS・Python 3.12・第三者パッケージなしの環境で実測しました。[期待出力の全JSON](expected-output.json)には相対パスと解析メタデータだけを保存し、本文、diff、commitの作者、ローカル絶対パス、実行ログを含めません。

| 事前に選定した確認先 | Graph | Co-change | union | intersection |
| --- | --- | --- | --- | --- |
| autoescape → `src/flask/app.py` | 含む | 含まない | 含む | 含まない |
| session transaction → `tests/test_testing.py` | 含む | 含む | 含む | 含む |
| session transaction → `src/flask/sessions.py` | 含む | 含まない | 含む | 含まない |
| context copy → `src/flask/__init__.py` | 含む | 含まない | 含む | 含まない |
| context copy → `tests/test_reqctx.py` | 含む | 含まない | 含む | 含まない |

この5確認先はすべてGraphの候補に含まれ、Co-changeでは1件でした。**これは精度100%という結果ではありません。** 確認先以外にも、次の数の候補があります。各ケースの候補範囲は、起点を除いて64ファイルでした。

| 変更 | Graph候補数 | 履歴候補数 | union候補数 | intersection候補数 |
| --- | ---: | ---: | ---: | ---: |
| autoescape | 29 | 22 | 34 | 17 |
| session transaction | 15 | 10 | 22 | 3 |
| context copy | 22 | 10 | 24 | 8 |

今回のチェックリストでは、履歴を加えても新しい確認先は増えず、候補総数は増えました。両方にある候補だけへ絞ると、選定した5確認先のうち4件が外れます。「両方で見つかったから正しい」「履歴に無いから読む必要がない」とは判断できません。候補の全一覧を残しているので、なぜそのファイルが出たかを追加で調べられます。

3つの確認先（`app.py`、`sessions.py`、`__init__.py`）は対象変更で未編集です。これらを候補に含めたことは、変更ファイル一覧以外から確認先を探す具体例になります。ただし、確認先を編集する必要があった、バグを予測した、障害を回避した、という証明にはしません。

`graph`は既存の粗いオフライン投影に候補があること、`history`は既存Co-change producerの既定フィルタを通ったことを意味します。`union`はどちらか、`intersection`は両方に含まれる候補です。AppのSQLによるPR判定規則とは別の集合比較です。

## 検証方法

境界条件の9テストも標準ライブラリだけで実行できます。

```sh
python3.12 -B -m unittest discover \
  -s zenn-content/examples/core-change-review -p test_review.py -v
```

独自Gitを使うテストには`VERIPSA_REVIEW_GIT=/path/to/git`を指定します。テストでは、未来commitの混入拒否、危険なarchive、Gitの失敗・timeout、候補範囲、元cloneのdirtyファイル・設定の保持、ローカルの`git replace`で固定入力が差し替わらないことを確認します。

`--timings timings.json`を追加すると、その実行の一時clone・グラフ・履歴計算の経過秒を別ファイルへ保存できます。入力cloneの中への保存は拒否します。時間は期待JSONの一致条件に含めず、一般的な性能指標として扱いません。CoreやFlaskの履歴が足りない入力や、解析プロセスの失敗を「候補なし」の成功として扱わないことも、この実験の一部です。

## 言えること・まだ言えないこと

- 選定した確認先について、候補へ含まれたか、含まれなかったかを再現できます。未変更の確認先も対象です。
- チェックリスト以外の候補は**未評価**です。余分な候補を自動的に誤検出とせず、全候補数と一覧を出します。この実験からprecision／recallは算出しません。
- Flaskは以前のCo-changeしきい値やstoplistの調整にも使われています。今回を未見の独立test setとは扱いません。
- 履歴上の共変更は相関で、因果関係ではありません。候補が無いことを`Clear`、安全、依存なしと読みません。
- グラフに候補があっても、変更内容との意味的な関連が証明されたわけではありません。根拠リンクから定義・利用箇所を読み、必要なテストを選ぶのは次の作業です。
- ローカルの静的解析だけを実行します。Flaskのテスト、実際のPR検査、障害回避、hosted Appの稼働は検証しません。

既存の[Flask集計評価](https://github.com/RollNuts/veripsa/blob/4236848504c8cb2cc3c14db22408fb519b06f754/docs/OFFLINE_EXAMPLE.md)は「現在の構造と過去の同時変更の関連」という別の問いを調べます。その倍率をこのケース調査の精度として使いません。Gitのマージと統合後の実行も比較したい場合は、[Coreの4ケース合成デモ](https://github.com/RollNuts/veripsa/tree/4236848504c8cb2cc3c14db22408fb519b06f754/examples/structural-overlap)へ進めます。

## 追記：現行CLIと事前固定検索の比較

2026-11-10、[Core `b924add`](https://github.com/RollNuts/veripsa/tree/b924add83e77972b6d09268f4eaab87e5b65b103)で追加した`tools.review_file`を同じ3つの変更直前へ実行しました。元の`cases.json`、Core `4236848`の期待出力、既存の9テストは変更していません。旧producer調査と、この新しいCLIの確認を別に記録します。

新しい空ディレクトリで、session transactionの1例を試せます。

```sh
git clone https://github.com/RollNuts/veripsa.git veripsa-file-review
git -C veripsa-file-review checkout --detach b924add83e77972b6d09268f4eaab87e5b65b103
git clone https://github.com/pallets/flask.git flask-file-review
git -C flask-file-review checkout --detach 514fc6b3e8402e4c646d5284e97a4f0ab50a7c4b
cd veripsa-file-review
python3.12 -B -m tools.review_file ../flask-file-review src/flask/testing.py
```

これは新しく作ったcloneをcheckoutする手順です。既存の元cloneを変更しない先頭の`review.py`とは操作を区別してください。CLIは作業ツリーとHEADの祖先履歴を読み、対象のコードやテストを実行しません。測定には各baseの祖先だけを持つ完全なGit入力を作り、対象変更object自体も不在と確認しました。上の簡易full-clone手順では後のobjectも保存されますが、baseの作業ツリー・祖先履歴だけを解析します。

検索baselineは、今回のCLI出力を見る前に、各起点の関数名1つと次のコマンドを固定しました。測定にはripgrep 15.2.0、Git 2.53.0、Python 3.12.13を使用しました。ripgrepは検索比較用で、CLI自体の依存ではありません。

```sh
rg -l -w -F -g '*.py' -- session_transaction src/flask tests
```

| 変更 | 事前固定した検索語 | 検索候補数 | CLI静的候補数 | CLI履歴候補数 | 選定確認先の包含：検索／静的／履歴 |
| --- | --- | ---: | ---: | ---: | --- |
| autoescape | `select_jinja_autoescape` | 1 | 29 | 22 | 1/1・1/1・0/1 |
| session transaction | `session_transaction` | 2 | 15 | 10 | 1/2・2/2・1/2 |
| context copy | `copy_current_request_context` | 2 | 22 | 10 | 2/2・2/2・0/2 |

表は起点を除く同じ64ファイル範囲へ、全producerの計算後に投影した件数です。CLIの生の静的／履歴候補数は順に34/26、16/11、22/11でした。範囲に合わせて履歴の母数・閾値・順位を計算し直していません。CLIの投影後の全候補集合は、旧期待JSONと一致しました。これは入口の追加を検証した結果で、解析精度の改善ではありません。

[比較結果JSON](cli-comparison.json)に、各base・範囲・候補一覧・条件・5確認先の包含を保存しました。全件でCLIの静的側は`uncertain`、履歴側は`observed`でした。repo全体は85 parsed、0 failed、23 skipped、不完全な文書21件です。このcoverageは64ファイルだけの集計ではありません。

検索で唯一出なかった選定確認先は、session保存の`src/flask/sessions.py`です。一方、静的候補は15〜29件になり、読む範囲が広がりました。検索で出た`tests/test_signals.py`など未選定の候補を、誤検出とは分類していません。追加検索やLSPを含む効率・正確性の優劣は未測定です。通常のAI調査は次節の1ケースだけを追試しており、一般的な優劣を測ったものではありません。既存のFlask調査を知った状態の事前固定なので、盲検や未見repoの評価とも呼びません。

候補の関係をソースで確認し、関連するテストを選ぶための入口です。本文を返さないことは、コードを読む次の作業や、その権限管理を不要にする意味ではありません。

## 追試：通常のAI調査とCLIメタデータ

2026-11-10、IPv6の1ケースだけをCodex CLI 0.167.0から各1回調査しました。[全条件と回答のJSON](ai-comparison.json)には、共通prompt、schema、Cに追加したCLIの生メタデータ、両回答、採点対象、観測値を保存しています。元のfixture・期待出力・コード・9テストは変更していません。

| 方法 | 返したpeer数 | 選定2確認先の包含 | 完了したcommand_execution item数 | exec経過秒 |
| --- | ---: | ---: | ---: | ---: |
| B：通常のソース調査 | 8 | 1/2 | 4 | 39.673 |
| C：同じ依頼＋CLIメタデータ | 8 | 2/2 | 3 | 39.243 |

両方が`tests/test_testing.py`を選び、Cだけが`src/flask/sessions.py`も選びました。Cの理由は、`session_transaction`がsession interfaceのopen/saveを呼び、cookie処理へつながることです。他のpeerは未評価です。事前選定はAI支援の確認先で、網羅的な正解集合や独立した人間のground truthではありません。

### 入力・実行条件

- B/Cともbase `514fc6b3e8402e4c646d5284e97a4f0ab50a7c4b`、tree `c7ec5b743fd39ea74136f6504ddd65787c8a5eec`、完全な祖先5,548commitを持つ別々のGit入力。対象変更objectは不在、remote・privateなclone元の設定・reflogは除去しました。
- 共通依頼はファイル内の「IPv6ホスト処理」を挙げ、最大8peer、根拠、不確実性を要求。`FlaskClient.session_transaction`という関数名までは指定していません。採点用2パスや過去回答はmodelの入力・読取範囲へ含めません。Cには`cli_report`だけをinlineで加え、外側の採点済みcase JSONは渡しません。
- 既存のChatGPTログインと利用枠を使用し、APIキーへのfallback、追加課金サービス、インストール、グローバル設定の変更はありません。CLI default modelを要求し、reasoningはlow。JSONLから実際のmodel IDを確認できなかったため、解決後のモデル同一性は未検証です。
- B→Cの固定順序、独立したephemeralセッション、各180秒上限、再試行なし。user configを読み込まず、web/MCPを使いません。公開入力と必要なruntimeだけを読むread-only profileで、networkを禁止しました。非機密canaryで範囲外read・書込・ローカル接続が拒否され、Gitは使えることを先に確認しました。[Codexのprofileと適用範囲](https://learn.chatgpt.com/docs/permissions)に従い、profileを上書きする`--sandbox`は併用していません。
- 両方exit 0、入力ファイルの前後hash不変。traceは検索・ソース表示・ローカルGit履歴調査だけでした。対象アプリのコード・テスト実行や、範囲外read・network/web/MCPは観測していません。canaryはコマンドの範囲を確かめるもので、認証clientなどを含む全機能の隔離証明ではありません。raw traceは公開しません。

### 解釈の限界と追試の方法

Bは主にEnvironBuilderのURL構築と設定、Cはそれに加えてsessionのcookie処理を調べました。**依頼が関数を特定していないため、Bの未包含を確定したAIの誤りとは評価しません。** 候補によって確認先が変わった1試行であり、障害回避・変更の完全性・一般的な精度向上の証明ではありません。両回答は完全性・merge安全性をfalseとしましたが、promptにもそう求めており、自発的な安全判断の性能を測ったものではありません。

経過秒は親から観測したexecの壁時計時間で、入力準備やCLI report生成時間を含みません。1 tool itemには複数のshell操作が入ります。token値もcacheを含むCLIの報告値で、価格や作業全体の費用ではありません。1ケース・各1回・順序固定・Flaskの既知利用歴から、時間や費用の削減を主張しません。

第三者は、前節の固定baseとCore CLIからreportを作り、JSONの`common_prompt`と`answer_schema`を使って、ソースのみ／同じ依頼＋`C_report`を別セッションへ渡せます。観測時のreportそのものも保存しています。モデルやサービスの変動があるため、回答のbyte一致を要求する再現テストではありません。次は関数名を明示し、未使用repoで複数回比較することが必要です。今回、検証を好ましい結果へ寄せる追加試行は行っていません。

## この資産の使い方

AIや開発者が変更前に起点ファイルを指定し、候補から定義・利用・テストを調べる作業の、小さい確認材料です。RollNutsの既存解析を、再現条件と限界が追える形で残します。このサンプルを追加したことは、Core MCPの新機能やGitHub Appの再開を意味しません。

コードを転載せず、公開Gitオブジェクトとソース行へのリンクを使っています。CoreとFlaskの利用条件は、それぞれのリポジトリのLICENSEを確認してください。
