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
import pathlib
import traceback
import logging
import time
import timeout_decorator
import argparse
from utils.bsky_util import BlueskyUtil

load_dotenv(".env")

logging.basicConfig(
    level=logging._nameToLevel[os.getenv("LOG_LEVEL", "FATAL")],
    format="%(asctime)s %(name)s %(levelname)s:%(message)s",
    filename="./debug.log",
)
logger = logging.getLogger(__name__)

# サムネ有効設定
THUMB_ENABLED = os.getenv("THUMB_ENABLED", True)

# デバッグモード
DEBUG_MODE = os.getenv("DEBUG_MODE", True)

# DBファイル名
DB_FILE = "post_log.sqlite"

new_data = []

bsky_util = BlueskyUtil()

# フィード解析用宣言
DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
FEED_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S %z",
    "%Y-%m-%dT%H:%M:%S%z",
]
JST = pytz.timezone("Asia/Tokyo")
nowDt = datetime.now(JST)
now = nowDt.strftime(DATE_FORMAT)
nowUtc = nowDt.isoformat() + "Z"

AS_OLD_DATE = int(os.getenv("AS_OLD_DATE", 30))


def create_db_connection():
    """DB セッションの作成"""
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
    """初期テーブル作成"""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE post_log(id INTEGER PRIMARY KEY AUTOINCREMENT, link STRING, created_at TIMESTAMP)"
    )
    conn.commit()


def delete_old_data():
    """古いレコードを削除してvacuumを叩く"""
    print("delete old data")
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM post_log WHERE created_at < datetime('now', ? || ' days')",
        (f"-{AS_OLD_DATE}",),
    )
    conn.commit()
    cur.execute("VACUUM")


def load_config():
    """config.json読み込み"""
    global config
    # envのTARGET_FEEDSを確認
    if os.getenv("TARGET_FEEDS", "") != "":
        # envに設定されたURLから読み込み
        config = requests.get(os.getenv("TARGET_FEEDS")).json()
        logger.debug("Config loaded from remote source.")
    else:
        # 空欄ならローカルの config.json から読み込み
        with open("config.json", "r") as config_file:
            config = json.load(config_file)
        logger.debug("Config loaded from local source.")


def get_thumb(url) -> bytes:
    """サムネ取得"""
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # title_tag = soup.find("meta", property="og:title")
    # description_tag = soup.find("meta", property="og:description")
    image_tag = soup.find("meta", property="og:image")

    if image_tag and image_tag["content"] != "":
        try:
            img_url = image_tag["content"]
            if "://" not in img_url:
                img_url = url + img_url

            resp = requests.get(img_url)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.error(e)
            return
    else:
        # 画像が取得できない場合はサムネなし扱い
        return


def try_parse_date(date_string):
    """複数の書式で日付文字列のパースを試みる"""
    for format in FEED_DATE_FORMATS:
        try:
            ans = datetime.strptime(date_string, format)
            return ans
        except:
            # 失敗したら次のフォーマットで試してみる
            pass
    # 想定外の書式だった場合、エラーを出しつつ暫定的に現在時刻を返す
    logger.warning("failed to parse : " + date_string)
    return now


def check_new_feeds(timestamp, feed, session):
    """新着判定"""
    # 更新なしならそのままtimestampを返して処理終了
    if feed.updated == timestamp["updated"]:
        print("no update : " + feed.feed.title)
        return timestamp

    # 更新日時が違うなら前回のタイムスタンプより未来の記事を抽出
    cur = conn.cursor()
    cur.execute("BEGIN TRANSACTION")
    loop_count = 0
    for entry in feed.entries:
        loop_count = +1
        if loop_count > os.getenv("MAX_CHECK_ENTRIES", 50):
            break
        if (try_parse_date(entry.updated)) > JST.fromutc(
            datetime.strptime(timestamp["updated"], DATE_FORMAT)
        ):
            # 投稿前に投稿済み記事かチェック
            posted = cur.execute(
                "SELECT count(id) FROM post_log WHERE link = :link",
                {"link": entry.link},
            )
            if posted.fetchone()[0] == 0:
                # ISO 8601形式に変換して格納
                entry_date = try_parse_date(entry.updated)
                iso_created_at = entry_date.strftime("%Y-%m-%d %H:%M:%S")
                cur.execute(
                    "INSERT INTO post_log(link, created_at) values(:link, :created_at)",
                    {"link": entry.link, "created_at": iso_created_at},
                )
                # 出力
                if DEBUG_MODE:
                    # デバッグモードの時は投稿せずprint
                    print(entry.title)
                    print(entry.link)
                else:
                    if THUMB_ENABLED:
                        img = get_thumb(entry.link)
                    else:
                        img = None
                    # if not bsky_util.post_feed(entry, feed.feed.title, session, card):
                    if not bsky_util.post_external(feed.feed.title, entry, img):
                        # 投稿に失敗したらループを抜けておく
                        logger.warning("post to bsky failed.")
                        break
                    else:
                        # レート制限回避のため5秒スリープしてから次へ
                        time.sleep(5)
    timestamp["updated"] = feed.updated
    cur.close()
    conn.commit()
    return timestamp


@timeout_decorator.timeout(300)
def main(session):
    # 最終読み取り時間を元に更新チェック
    with open("last.json", "r") as last_data:
        data = json.load(last_data)
        for check_feeds in config["check_feeds"]:
            tmp = [d for d in data if d["href"] == check_feeds["url"]]
            if len(tmp) == 0:
                timestamp = {"href": check_feeds["url"], "updated": now}
            else:
                timestamp = tmp[0]
            try:
                feed = feedparser.parse(check_feeds["url"])
                # bozo=1だったらパースに失敗（URLが死んでるなど？）
                timestamp = check_new_feeds(timestamp, feed, session)
                new_data.append(timestamp)
            except Exception as e:
                logger.error(e)
                # パースに失敗したら次のフィードへ
                logger.warning("feedparser parse failed. : " + check_feeds["url"])

    # 最終読み取り時間を更新
    with open("last.json", "w") as last_data:
        json.dump(new_data, last_data)


if __name__ == "__main__":
    # stopファイルが残っていたら何も実行しない
    stop_file = pathlib.Path("./stop")
    if stop_file.exists():
        exit(0)
    # 前回のプロセスが残っている場合は処理を実行せず終了
    with open(".lock", "w") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            # 前回のプロセスが残っているため何もせず終了
            exit(0)
        try:
            param_parser = argparse.ArgumentParser()
            param_parser.add_argument(
                "--vacuum",
                action="store_true",
                help="Perform vacuum operation to clean old data",
            )
            session = bsky_util.load_session()
            if session:
                create_db_connection()
                load_config()
                main(session)
                if param_parser.parse_args().vacuum:
                    delete_old_data()
            else:
                logger.warning("failed to create session.")
        except Exception as e:
            # 想定していない例外が発生した場合、エラーが発生した遺言を残して停止
            logger.error(e)
            stop_file.touch()
            with open(stop_file.name, "a") as f:
                traceback.print_exc(file=f)
            bsky_util.post_text(
                "処理中にエラーが発生しました。対応が完了するまで投稿を停止します。",
                session,
            )
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            try:
                conn.close()
            except:
                pass
