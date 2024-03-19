import os
import feedparser
import json
from datetime import datetime
import pytz
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import fcntl
import sqlite3
import sys

load_dotenv('.env')

IMAGE_MIMETYPE = "image/webp"

# デバッグモード
DEBUG_MODE = os.getenv('DEBUG_MODE', True)
# サムネ有効設定（現時点では不具合が発生するため原則False）
THUMB_ENABLED = os.getenv('THUMB_ENABLED', False)

# DBファイル名
DB_FILE = 'post_log.sqlite'

new_data = []

# フィード解析用宣言
DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
FEED_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S %z",
    "%Y-%m-%dT%H:%M:%S%z"
]
JST = pytz.timezone('Asia/Tokyo')
nowDt = datetime.now(JST)
now = nowDt.strftime(DATE_FORMAT)
nowUtc = nowDt.isoformat() + 'Z'

AS_OLD_DATE = os.getenv('AS_OLD_DATE', 30)

def create_bsky_session():
    '''BlueSky セッションの作成'''
    url = 'https://bsky.social/xrpc/com.atproto.server.createSession'
    data = {'identifier': os.getenv('BSKY_USER_NAME'), 'password': os.getenv('BSKY_APP_PASS')}
    headers = {'content-type': 'application/json'}
    response = requests.post(url, data=json.dumps(data), headers=headers).json()
    global session
    session = {
        'accessJwt': response['accessJwt'],
        'did': response['did']
    }

def create_db_connection():
    '''DB セッションの作成'''
    # セッションの作成前にDBファイルの存在チェック
    initFlg = True
    if os.path.isfile(DB_FILE):
        initFlg = False
    global conn
    conn = sqlite3.connect(DB_FILE)
    if initFlg:
        # DBファイルが今回始めて作られた場合は中身を初期化
        create_table()

def create_table():
    '''初期テーブル作成'''
    cur = conn.cursor()
    cur.execute('CREATE TABLE post_log(id INTEGER PRIMARY KEY AUTOINCREMENT, link STRING, created_at TIMESTAMP)')
    conn.commit()

def delete_old_data():
    '''古いレコードを削除してvacuumを叩く'''
    cur = conn.cursor()
    cur.execute('DELETE FROM post_log WHERE created_at < datetime(\'now\', \'-' + AS_OLD_DATE + ' days\')')
    conn.commit()
    cur.execute('VACUUM')

def load_config():
    '''config.json読み込み'''
    with open("config.json", "r") as config_file:
        global config
        config = json.load(config_file)

def get_thumb(url) -> dict:
    '''サムネ取得'''
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    card = {
        "uri": url,
        "title": "",
        "description": "",
    }

    title_tag = soup.find("meta", property="og:title")
    if title_tag:
        card["title"] = title_tag["content"]
    description_tag = soup.find("meta", property="og:description")
    if description_tag:
        card["description"] = description_tag["content"]

    # if there is an "og:image" HTML meta tag, fetch and upload that image
    image_tag = soup.find("meta", property="og:image")
    if image_tag:
        img_url = image_tag["content"]
        if img_url == '':
            # og:imageが空欄の場合がある
            return
        # naively turn a "relative" URL (just a path) into a full URL, if needed
        if "://" not in img_url:
            img_url = url + img_url
        resp = requests.get(img_url)
        resp.raise_for_status()

        blob_resp = requests.post(
            "https://bsky.social/xrpc/com.atproto.repo.uploadBlob",
            headers={
                "Content-Type": IMAGE_MIMETYPE,
                "Authorization": "Bearer " + session['accessJwt'],
            },
            data=resp.content,
        )
        blob_resp.raise_for_status()
        try:
            card["thumb"] = blob_resp.json()["blob"]
        except:
            # サムネ取得に失敗する場合があるので例外処理
            pass
    
    return card

def post_bsky(entry, feed_name):
    '''BlueSkyに投稿'''
    url = 'https://bsky.social/xrpc/com.atproto.repo.createRecord'
    card = {}
    if (THUMB_ENABLED):
        card = get_thumb(entry.link)
    if (card and 'thumb' in card):
        external = {
            'uri': entry.link,
            'title': entry.title,
            'description': '',
            'thumb': card['thumb']
        }
    else:
        external = {
            'uri': entry.link,
            'title': entry.title,
            'description': ''
        }
    data = {
        'repo': session['did'],
        'collection': 'app.bsky.feed.post',
        'record': {
            'text': feed_name,
            'createdAt': datetime.utcnow().isoformat() + 'Z',
            'type': 'app.bsky.feed.post',
            'embed': {
                '$type': 'app.bsky.embed.external',
                'external': external
            }
        }
    }
    headers = {
        'Authorization': 'Bearer ' + session['accessJwt'],
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
    return now

def check_new_feeds(timestamp, feed):
    '''新着判定'''
    # 更新なしならそのままtimestampを返して処理終了
    if feed.updated == timestamp['updated']:
        print('no update : ' + feed.feed.title)
        return timestamp
    
    # 更新日時が違うなら前回のタイムスタンプより未来の記事を抽出
    cur = conn.cursor()
    for entry in feed.entries:
        if (try_parse_date(entry.updated)) > JST.fromutc(datetime.strptime(timestamp['updated'], DATE_FORMAT)):
            # 投稿前に投稿済み記事かチェック
            posted = cur.execute('SELECT count(id) FROM post_log WHERE link = \'' + entry.link + '\'')
            if posted.fetchone()[0] == 0:
                # 出力
                if (DEBUG_MODE):
                    print(entry.title)
                    print(entry.link)
                else:
                    post_bsky(entry, feed.feed.title)
                    cur.execute('INSERT INTO post_log(link, created_at) values(\''+ entry.link +'\',\''+ now +'\')')
    timestamp['updated'] = feed.updated
    conn.commit()
    cur.close()
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
                    'updated' : now
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
    # 前回のプロセスが残っている場合は処理を実行せず終了
    with open('.lock', 'w') as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            # 前回のプロセスが残っているため何もせず終了
            exit(0)
        try:
            create_bsky_session()
            create_db_connection()
            load_config()
            main()
            if len(sys.argv) > 1 and sys.argv[1] == 'vacuum':
                delete_old_data()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            conn.close()
