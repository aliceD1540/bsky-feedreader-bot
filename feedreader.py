import os
import feedparser
import json
from datetime import datetime
import pytz
import requests
from dotenv import load_dotenv

load_dotenv('.env')

new_data = []

# フィード解析用宣言
DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
FEED_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S %z",
    "%Y-%m-%dT%H:%M:%S%z"
]
JST = pytz.timezone('Asia/Tokyo')

# BlueSky セッションの作成
url = 'https://bsky.social/xrpc/com.atproto.server.createSession'
data = {'identifier': os.getenv('BSKY_USER_NAME'), 'password': os.getenv('BSKY_APP_PASS')}
headers = {'content-type': 'application/json'}
response = requests.post(url, data=json.dumps(data), headers=headers).json()
accessJwt = response['accessJwt']
did = response['did']

def load_config():
    '''config.json読み込み'''
    with open("config.json", "r") as config_file:
        global config
        config = json.load(config_file)

def post_bsky(entry, feed_name):
    url = 'https://bsky.social/xrpc/com.atproto.repo.createRecord'
    now = datetime.utcnow().isoformat() + 'Z'
    data = {
        'repo': did,
        'collection': 'app.bsky.feed.post',
        'record': {
            'text': feed_name,
            'createdAt': now,
            'type': 'app.bsky.feed.post',
            'embed': {
                '$type': 'app.bsky.embed.external',
                'external': {
                    'uri': entry.link,
                    'title': entry.title,
                    'description': ''
                }
            }
        }
    }
    headers = {
        'Authorization': 'Bearer ' + accessJwt,
        'content-type': 'application/json'
    }

    response = requests.post(url, data=json.dumps(data), headers=headers)


def try_parse_date(date_string):
    '''複数の書式で日付文字列のパースを試みる'''
    for format in FEED_DATE_FORMATS:
        try:
            ans = datetime.strptime(date_string, format)
            return ans
        except:
            continue
    # 想定外の書式だった場合、エラーを出しつつ暫定的に現在時刻を返す
    print('failed to parse : ' + date_string)
    return datetime.now(JST).strftime(DATE_FORMAT)

def check_new_feeds(timestamp, feed):
    '''新着判定'''
    # 更新なしならそのままtimestampを返して処理終了
    if feed.updated == timestamp['updated']:
        print('no update : ' + feed.feed.title)
        return timestamp
    
    # 更新日時が違うなら前回のタイムスタンプより未来の記事を抽出
    for entry in feed.entries:
        if (try_parse_date(entry.updated)) > JST.fromutc(datetime.strptime(timestamp['updated'], DATE_FORMAT)):
            # 出力
            # print(entry.title)
            # print(entry.link)
            post_bsky(entry, feed.feed.title)
    timestamp['updated'] = feed.updated
    return timestamp

def main():
    # 最終読み取り時間を元に更新チェック
    with open("last.json", "r") as last_data:
        data = json.load(last_data)
        for check_feeds in config['check_feeds']:
            tmp = [d for d in data if d['href'] == check_feeds['url']]
            if len(tmp) == 0:
                timestamp = {
                    'href' : check_feeds['url'],
                    'updated' : datetime.now(JST).strftime(DATE_FORMAT)
                }
            else:
                timestamp = tmp[0]

            feed = feedparser.parse(check_feeds['url'])
            # bozo=1だったらパースに失敗（URLが死んでるなど？）
            timestamp = check_new_feeds(timestamp, feed)

            new_data.append(timestamp)

    # 最終読み取り時間を更新
    with open("last.json", "w") as last_data:
        json.dump(new_data, last_data)

if __name__ == "__main__":
    load_config()
    main()



