# 同期すると、誰が本文を預かるのか

架空の一人分のメモで、保存先と削除の範囲を観測する小教材です。端末だけの保存に同期を足すと、運営者側のDBにも本文が増えます。その後live側の本文を削除しても、先に作ったバックアップと端末のメモには残ります。

## 実行する

Python 3.12と標準ライブラリだけを使います。リポジトリのルートから実行してください。

```sh
python3.12 -B examples/minimal-custody/demo.py
python3.12 -B -m unittest discover -s examples/minimal-custody -p 'test_*.py' -v
```

追加パッケージ、アカウント、外部通信、モデルやAPIは不要です。入力はコード中の架空fixtureだけで、利用者のファイルを指定・読み込む機能はありません。fixtureには固有markerと架空のemail・token表記を含め、ログへ混ざらないことも確認します。実際の認証情報ではありません。

端末・サーバー・バックアップの各役は、**同じ一時ディレクトリ内の別ファイル**で模擬します。ネットワーク同期は行いません。実行中にファイルを作成して観測し、DBを閉じてから一時ディレクトリを削除します。JSONの観測結果は標準出力に出ます。常駐サービスや永続的な保存基盤ではありません。

## 期待する出力

`demo.py`は次の結果をJSONで出力します。

| 段階 | キーと期待値 | 実際に確認すること |
| --- | --- | --- |
| 端末だけ | `local_only.device_body_matches: true` | 端末ファイルを読み直すと元の本文と一致 |
| 運営者側に未保存 | `local_only.operator_database_exists: false` | サーバー役DBはまだ存在しない |
| 同期を追加 | `after_sync.server_body_matches: true` | DBから本人の本文を読み出せる |
| 暗号化なし | `after_sync.plaintext_marker_in_server_file: true` | SQLiteファイルのbytesにも固有markerがある |
| 別利用者 | `owner_checks.other_read_unavailable: true` | 他人の本文を返さない |
| 別利用者による削除 | `owner_checks.other_delete_refused: true` | 削除は0行、本人は引き続き読める |
| 本人によるlive削除後 | `after_live_delete.live_read_unavailable: true` | liveのSQL読出しでは本文を得られない |
| backupと端末 | `after_live_delete.backup_body_matches: true`、`device_body_matches: true` | 削除前のbackupと端末には本文が残る |
| 操作ログ | `fixed_fields_only: true`、`body_marker_present/email_present/token_present: false` | 固定の操作名・結果だけを記録 |
| 終了時 | `temporary_directory_removed: true` | 一時ディレクトリのパスがなくなった |

`operation_log.entries`は8件です。`sync/read/delete`と`ok/unavailable`だけを出力します。存在しないメモと他人のメモは、同じ`unavailable`として扱います。ログのないことを処理成功の証拠にせず、この例ではSQL結果と別に確認します。

## 所有者の条件と、その限界

`trusted_owner_id`は、信頼済みsessionから得たIDを**模した引数**です。readとdeleteのSQLは、対象メモのIDと所有者IDの両方を条件にします。値はSQLiteのプレースホルダーへ渡し、SQL文字列に連結しません。

**このコードにはログインもsession検証もありません。** 呼び出し側が任意のowner IDを渡せるため、本番の認証・権限管理を実装したことにはなりません。DBの認可条件の一部を切り出した教材で、直接DBを読む管理者や他の処理からのアクセスも制御していません。

ログ関数は本文を受け取らず、項目だけでなく値も固定候補に限ります。ただし、実サービスのフレームワーク、例外、リバースプロキシなど、別経路のログに本文が残らないことは検証していません。永続的な監査証跡や、DB更新とログ書込の原子性も対象外です。

## この実験で証明しないこと

- 本文・DB・バックアップは暗号化していません。端末とサーバーの役を分けたことは機密性の証明ではありません。
- liveのSQL読出し不可と、ディスクからの物理消去は別です。SQLiteの空き領域、ジャーナル、OSやディスクの複製・復元可能性は調べていません。
- 終了後に一時ディレクトリがなくなることも、完全消去の証明ではありません。本文の残存は**実行中の観測**です。
- ネットワーク、実ユーザー、同時更新、認証、暗号化、バックアップの期限管理・全複製削除、本番環境の安全性は検証していません。

8件のテストは、コピーの増加、本人read、他者read/delete拒否、backup残存、固定ログ、自由記述log拒否、SQL値の扱い、一時領域の終了時削除を確認します。
