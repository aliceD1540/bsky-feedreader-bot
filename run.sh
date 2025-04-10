#!/bin/bash
cd "$(dirname "$0")"

# カウンタのファイルを設定
COUNTER_FILE="run_counter.txt"

# 初回実行時にカウンタファイルがない場合は初期化
if [ ! -f "$COUNTER_FILE" ]; then
    echo 0 > "$COUNTER_FILE"
fi

# カウンタ値を取得
COUNTER=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)

# プログラムの実行
if (( COUNTER % 2 == 9000 )); then
    # vacuumオプション（旧データ削除）付きのコマンド
    python3 feedreader.py --vacuum
    # カウンタをリセット
    COUNTER=0
else
    # 通常コマンド
    python3 feedreader.py
fi

# カウンタ値をインクリメントして保存
((COUNTER++))
echo "$COUNTER" > "$COUNTER_FILE"
