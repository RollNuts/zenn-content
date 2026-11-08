# Tauriの文字列契約をグラフで見る、小さな再現例

独立して作ったRust/TypeScriptの4ケースを、公開Veripsa Coreの
コミット d22d44f12112784d34d5ea7ba20755ca995adad2 で静的解析します。
実製品やprivate archiveのコードは使っていません。Tauri本体、Rustビルド、npm installは不要です。

## 準備

GitとPython 3.12を用意し、このREADMEのディレクトリで実行します。

~~~sh
git clone https://github.com/RollNuts/veripsa.git core
git -C core checkout d22d44f12112784d34d5ea7ba20755ca995adad2
python3.12 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: --no-deps -r requirements.txt
.venv/bin/python verify.py --core core --report observations.json
~~~

上記はPOSIXのパス表記です。Windowsでは仮想環境の Scripts 内を指定します。
cloneとpackage installはネットワークを使います。検証ドライバー自身はローカルのGitメタデータ、
固定したCoreソース、合成fixtureだけを読み、DBやホスト版へ接続しません。
この例の最小依存はCore全体のruntime依存を満たすものではありません。

verify.py は、解析前に次を確認します。

- CoreのGit HEADが指定コミットと完全一致すること。
- 抽出パイプラインの24ファイルが core-source-lock.json のGit blob SHAと一致すること。
  無関係な evaluate.py などのworking-tree変更は拒否理由にしません。
- tree-sitter本体とJS/TS/TSX/Rust grammar、PyYAMLを実際にimport・parseできること。
  依存不足はfixtureの結果と混ぜず、解析前に停止します。

Gitの実行ファイルを選ぶ場合は --git /path/to/git を追加できます。
requirements.txt はCoreのABI互換範囲に合わせた最小依存です。
今回の実行に使った正確な依存版は observations.json に記録します。

## 4ケースと期待値

共通のコマンド名は receipt_label、resource IDは tauri_command::receipt_label です。

| ケース | Rust/TypeScriptの違い | alters | queries | edgeのreference_status | documentのanalysis_status |
| --- | --- | ---: | ---: | --- | --- |
| official-literal | #[tauri::command] と公式module由来の invoke("receipt_label") | 1 | 1 | null ×2 | null ×2 |
| local-invoke | 公式importがなく、自分の同名関数 invoke を呼ぶ | 1 | 0 | null ×1 | null ×2 |
| dynamic-name | 公式invokeだが、引数は文字列リテラルでなく変数 | 1 | 0 | null ×1 | null ×2 |
| duplicate-command | 同じコマンドをRust 2ファイルで定義し、公式invokeで呼ぶ | 2 | 1 | ambiguous ×3 | ambiguous ×3 |

すべて app_command nodeは1個です。最後のケースだけnodeのprovenanceも
ambiguousになります。定義からresourceへの辺が alters、呼出し側からresourceへの辺が
queries です。これらはグラフ上の役割名であり、実際のデータread/writeを示しません。
ここでの null はstatus markerが付かない通常状態を表します。

動的引数のケースでは、consumerの queries 辺は抽出されません。
「unresolvedという辺が出る」「そのコードは安全」「実際には依存がない」という意味ではありません。
最後のケースでは、曖昧な候補を消さずに記録することまで確認します。
このドライバーはSQLの実効隣接やPR判定を実行しません。

検証は辺の数だけでなく、定義・参照のファイル、status、node identityも照合します。
Rust関数の説明用body markerが返却graphへ混ざらないことも、この入力について確認します。
秘密情報全般の除去を保証するテストではありません。

## 出力

標準出力は各ケースの辺数とstatus、最後に 4/4 synthetic cases passed を表示します。
--report observations.json は依存版、検証したCore blob、fixture SHA-256、
各ケースの辺・document statusをJSONへ保存します。ソース本文や一時ディレクトリの絶対パスは含めません。

入力は fixtures/、期待値は expectations.json にあります。
driverはfixtureを一時コピーし、そのコピーだけへ build_graph を適用します。
Core checkoutや元のfixtureを書き換えません。版を変える場合は、期待値とblob lockを
再検証して更新してください。

これは小さい静的抽出の教材です。Tauriアプリとしてのbuild、handler登録、
IPC実行、型チェック、任意の動的呼出しの解決、PRの正しさ・merge安全性、
ホスト版の現在稼働は検証しません。Veripsaのホスト版は停止中です。

