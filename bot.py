import yfinance as yf
import pandas as pd
import requests
import os

LINE_TOKEN = os.environ.get("LINE_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

def send_line_message(message_text):
    if not LINE_TOKEN or not LINE_USER_ID:
        print("LINEの鍵が設定されていません。")
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    data = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": message_text}]}
    requests.post(url, headers=headers, json=data)

def main():
    print("🤖 ロボットが起動しました！データを確認します...")
    ticker = "USDJPY=X" # ドル円
    
    try:
        data = yf.download(ticker, period="5d", interval="1h", progress=False)
        if data.empty:
            print("データの取得に失敗しました。")
            return

        latest = data.iloc[-1]
        current_price = float(latest['Close'].iloc[0]) if isinstance(latest['Close'], pd.Series) else float(latest['Close'])
        
        # --- ここからが「賢い判定」の仕組みです ---
        target_price = 155.00 # 仮の目標レート（155円）
        
        print(f"現在の価格: {current_price:.3f} 円 / 目標: {target_price} 円")

        if current_price > target_price:
            # 条件を満たした時だけ、この中に入ってLINEを送ります
            msg = f"🚨【アラート発動】\nドル円が {target_price} 円を上回りました！\n現在の価格: {current_price:.3f} 円"
            send_line_message(msg)
            print("✅ アラート条件を満たしたため、LINEに送信しました！")
        else:
            # 条件を満たしていない時は、LINEを送らずに黒い画面（ログ）にメモだけ残します
            print("💤 アラート条件を満たしていないため、LINEは送らずに終了します。")

    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    main()
