## なにこれ

Bluesky用フィードリーダーです。  

## 使い方

実行環境については省略  

1. Blueskyでアプリパスワードを発行 
2. .env.sample をコピーして .env ファイルを作成 
    - アカウント名と1で発行したパスワードに変更
    - 必要に応じて各オプションを書き換え
3. 後述の「チェック対象フィード」を参考にチェックしたいフィードを設定
4. feedreader.py を実行

### チェック対象フィード

config.json.sampleを参考にconfig.jsonを作成してください。  
check_feedsおよびurlの階層が変わらなければ、別項目が含まれていても問題ありません。  
（nameなどを加えて整形して表示できるよう改変してもOK）  

#### ローカルに設定を持つ場合

1. .envのTARGET_FEEDSを空欄にする
2. ローカルのconfig.jsonを編集

#### リモート（Webサイト等）に設定を持つ場合

1. config.jsonを自サイトにアップロード
2. .envに1のURLを設定

### crontab設定例

現在運用している環境のcrontab設定です。  

```
*/5 0-1,4-23 * * * /home/pi/ssd/user/bsky-feedreader-bot/run.sh
10 1 * * * sudo reboot
```

どうも長時間起動しているとプログラム以外の箇所で不安定になるようなので、毎日深夜に再起動  

## 注意

- 利用は自己責任です
- 日付の書式の想定は、私が個人的に利用するフィードを網羅してるだけなので足りない可能性があります

## 運用ハードウェア環境

sqliteのDB書き換え処理が頻繁に走るため、  
Raspberry Piなどで動かす場合はSDカード内で処理せずUSB接続のSSDなどを推奨  

- 本番環境
    - Raspberry Pi Zero 2W
        - SSDで実運用中
