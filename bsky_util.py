import json
import requests
import logger
import os
import time
from datetime import datetime

# セッション保持ファイル
BSKY_SESSION_FILE = 'bsky_session.json'

def save_session(session_data):
    '''セッション情報の保存'''
    with open(BSKY_SESSION_FILE, 'w') as file:
        json.dump(session_data, file)

def load_session():
    '''セッション情報のロード'''
    try:
        with open(BSKY_SESSION_FILE, 'r') as file:
            session_data = json.load(file)
        # global session
        session = {
            'accessJwt': session_data['accessJwt'],
            'refreshJwt': session_data['refreshJwt'],
            'did': session_data['did']
        }
        if get_session(session):
            # トークンが有効ならそのまま使用
            return session
        else:
            # トークンが無効ならリフレッシュ
            return refresh_session(session)
    except (FileNotFoundError, KeyError):
        # ファイルが存在しなかったりトークンが取得できない場合はセッション作成
        print('create session')
        return create_session()

def get_session(session):
    '''セッションが有効かチェック'''
    try:
        url = 'https://bsky.social/xrpc/com.atproto.server.getSession'
        headers = {
            'Authorization': 'Bearer ' + session['accessJwt'],
            'content-type': 'application/json'
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return True
    except Exception as e:
        logger.write_error(e)
        return
    return False

def refresh_session(session):
    '''セッションの更新'''
    try:
        url = 'https://bsky.social/xrpc/com.atproto.server.refreshSession'
        headers = {
            'Authorization': 'Bearer ' + session['refreshJwt'],
            'content-type': 'application/json'
        }
        response = requests.post(url, headers=headers).json()
        save_session(response)
        session = {
            'accessJwt': response['accessJwt'],
            'refreshJwt': response['refreshJwt'],
            'did': response['did']
        }
    except Exception as e:
        logger.write_error(e)
        return
    return session

def create_session():
    '''セッションの作成'''
    try:
        url = 'https://bsky.social/xrpc/com.atproto.server.createSession'
        data = {'identifier': os.getenv('BSKY_USER_NAME'), 'password': os.getenv('BSKY_APP_PASS')}
        headers = {'content-type': 'application/json'}
        response = requests.post(url, data=json.dumps(data), headers=headers).json()
        save_session(response)
        # global session
        session = {
            'accessJwt': response['accessJwt'],
            'did': response['did']
        }
        return session
    except Exception as e:
        # 通信不良等でセッションの作成に失敗した場合は処理終了
        logger.write_error(e)
        return

def post_feed(entry, feed_name, session, card={}):
    '''BlueSkyに投稿'''
    url = 'https://bsky.social/xrpc/com.atproto.repo.createRecord'

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

    ans = False
    try:
        response = requests.post(url, data=json.dumps(data), headers=headers)
        ans = True
    except Exception as e:
        logger.write_error(e)
    finally:
        # 5秒スリープする（レート制限回避処理）
        time.sleep(5)
    return ans

def post_text(text:str, session):
    '''BlueSkyに投稿（テキスト指定）'''
    url = 'https://bsky.social/xrpc/com.atproto.repo.createRecord'

    data = {
        'repo': session['did'],
        'collection': 'app.bsky.feed.post',
        'record': {
            'text': text,
            'createdAt': datetime.utcnow().isoformat() + 'Z',
            'type': 'app.bsky.feed.post',
        }
    }
    headers = {
        'Authorization': 'Bearer ' + session['accessJwt'],
        'content-type': 'application/json'
    }

    response = requests.post(url, data=json.dumps(data), headers=headers)

def create_link_card(img_data:bytes, url:str, title:str, description:str, session):
    '''リンクカード作成'''
    # 現時点では添付データは画像を想定、画像以外の形式は未検証
    card = {
        "uri": url,
        "title": title,
        "description": description,
    }
    try:
        blob_resp = requests.post(
            "https://bsky.social/xrpc/com.atproto.repo.uploadBlob",
            headers={
                "Content-Type": "image/webp",
                "Authorization": "Bearer " + session['accessJwt'],
            },
            data=img_data,
        )
        blob_resp.raise_for_status()
        card["thumb"] = blob_resp.json()["blob"]
    except:
        return

    return card
