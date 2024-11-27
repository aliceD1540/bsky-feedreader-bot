import os
from atproto import Client, models, exceptions

# セッション保持ファイル
BSKY_SESSION_FILE = 'bsky_session.json'

class BlueskyUtil():

    def __init__(self) -> None:
        self.client = Client()

    def save_session(self):
        '''セッション情報の保存'''
        with open(BSKY_SESSION_FILE, 'w') as file:
            file.write(self.client.export_session_string())

    def load_session(self):
        '''セッション情報のロード'''
        try:
            print('try relogin.')
            with open(BSKY_SESSION_FILE, 'r') as file:
                session_str = file.read()
            return self.client.login(session_string=session_str)
        except (FileNotFoundError, ValueError, exceptions.BadRequestError):
            # ファイルが存在しなかったりトークンが取得できない場合はセッション作成
            print('failed. create session...')
            return self.create_session()

    def create_session(self):
        '''セッションの作成'''
        self.client = Client()
        login = self.client.login(login=os.getenv('BSKY_USER_NAME'), password=os.getenv('BSKY_APP_PASS'))
        self.save_session()
        return login

    def post_external(self, message:str, card:dict, img:bytes):
        '''カード付きポスト'''
        if img:
            upload = self.client.upload_blob(img)
            external = models.AppBskyEmbedExternal.External(uri=card.link, title=card.title, thumb=upload.blob, description='')
        else:
            external = models.AppBskyEmbedExternal.External(uri=card.link, title=card.title, description='')
        embed = models.AppBskyEmbedExternal.Main(external=external)
        
        return self.client.send_post(message, embed=embed)

    def post_text(self, text:str):
        '''テキストのみのポスト'''
        self.client.post(text)
