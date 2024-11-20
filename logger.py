import pathlib
from datetime import datetime
import pytz

JST = pytz.timezone('Asia/Tokyo')
DATE_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
nowDt = datetime.now(JST)
now = nowDt.strftime(DATE_FORMAT)

def write_warn(message):
    '''想定している異常だけど多発した際の記録用に発生時間は残しておきたい'''
    warn_file = pathlib.Path('./warn.log')
    warn_file.touch()

    with open("warn.log", mode='a') as warn_txt:
        warn_txt.write(now + " : " + message + "\n")

def write_error(message):
    '''想定外のエラー'''
    error_file = pathlib.Path('./error.log')
    error_file.touch()

    with open("error.log", mode='a') as error_txt:
        error_txt.write(now + " : " + message + "\n")
