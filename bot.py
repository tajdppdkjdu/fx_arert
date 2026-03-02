import yfinance as yf
import pandas as pd
import requests
import os

# --- 設定部分 ---
# ※セキュリティのため、GitHubの「Secrets（秘密の金庫）」から鍵を取り出す設定にしています
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
        # 1時間足のデータを取得
        data = yf.download(ticker, period="5d", interval="1h", progress=False)
        
        if data.empty:
            print("データの取得に失敗しました。")
            return

        # 最新の価格を取得
        latest = data.iloc[-1]
        current_price = float(latest['Close'].iloc[0]) if isinstance(latest['Close'], pd.Series) else float(latest['Close'])
        
        # テスト用のメッセージを作成
        msg = f"🤖【定期チェック完了】\n現在のドル円(1時間足)は {current_price:.3f} 円です。\n※これは自動実行ロボットのテスト通知です。"
        
        # LINEに送信！
        send_line_message(msg)
        print("✅ LINEにメッセージを送信しました！")

    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    main()
