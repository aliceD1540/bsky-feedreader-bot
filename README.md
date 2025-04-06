## なにこれ

Bluesky用フィードリーダーです。 

## 使い方

実行環境については省略

1. Blueskyでアプリパスワードを発行 
2. .env.sample をコピーして .env ファイルを作成 
    - アカウント名と1で発行したパスワードに変更
    - 必要に応じて各オプションを書き換え
3. config.json.sample をコピーして config.json ファイルを作成
    - チェックしたいフィードのURLを設定
4. feedreader.py を実行

### crontab設定例

現在運用している環境のcrontab設定です。
毎月1日の0時のみオプション付きで起動し、DB上の旧データ削除＆VACUUMを行います。

```
1-59/10 * * * * /home/pi/ssd/bsky-feedreader-bot/run.sh
0 1-23 * * * /home/pi/ssd/bsky-feedreader-bot/run.sh
0 0 2-31 * * /home/pi/ssd/bsky-feedreader-bot/run.sh
0 0 1 * * /home/pi/ssd/bsky-feedreader-bot/run.sh vacuum
```

2024-09-10 Rate Limitに引っかかったので実行間隔を5分→10分に変更

## 注意

- 利用は自己責任です
- 日付の書式の想定は、私が個人的に利用するフィードを網羅してるだけなので足りない可能性があります

## 運用ハードウェア環境

sqliteのDB書き換え処理が頻繁に走るため、\
Raspberry Piなどで動かす場合はSDカード内で処理せず外付けストレージ推奨

- 本番環境
    - Raspberry Pi Zero 2W
        - SSDで実運用中
