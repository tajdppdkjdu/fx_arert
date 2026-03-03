import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta

LINE_TOKEN = os.environ.get("LINE_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
JSONBIN_ID = os.environ.get("JSONBIN_BIN_ID")
JSONBIN_KEY = os.environ.get("JSONBIN_API_KEY")

pairs = {
    "USDJPY": "USDJPY=X", "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "EURGBP": "EURGBP=X",
    "AUDJPY": "AUDJPY=X", "CADJPY": "CADJPY=X", "CHFJPY": "CHFJPY=X",
    "GBPAUD": "GBPAUD=X", "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X", "EUR": "EUR=X", "AUD": "AUD=X",
    "GOLD": "GC=F", "SILVER": "SI=F"
}

def send_line(msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    requests.post(url, headers=headers, json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg}]})

def load_alerts():
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}"
    headers = {"X-Master-Key": JSONBIN_KEY}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json().get("record", {}).get("alerts", [])
    return []

def save_alerts(alerts):
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}"
    headers = {"X-Master-Key": JSONBIN_KEY, "Content-Type": "application/json"}
    requests.put(url, headers=headers, json={"alerts": alerts})

def check_cross(prev1, curr1, prev2, curr2, mode):
    up = (prev1 <= prev2 and curr1 > curr2)
    down = (prev1 >= prev2 and curr1 < curr2)
    if mode == "上回る": return up
    if mode == "下回る": return down
    if mode == "交差": return up or down
    return False

def eval_cond(cond, cp, pp, cs, ps):
    if cond["type"] == "① 価格×価格":
        return check_cross(pp, cp, cond["target_price"], cond["target_price"], cond["direction"])
    elif cond["type"] == "② 価格×SMA":
        return check_cross(pp, cp, ps[cond["target_sma"]], cs[cond["target_sma"]], cond["direction"])
    elif cond["type"] == "③ SMA×SMA":
        return check_cross(ps[cond["sma1"]], cs[cond["sma1"]], ps[cond["sma2"]], cs[cond["sma2"]], cond["direction"])
    return False

def main():
    alerts = load_alerts()
    if not alerts:
        print("💤 登録されたアラートがないため終了します。")
        return

    # 現在の日本時間を取得
    now_jst = datetime.utcnow() + timedelta(hours=9)
    
    valid_alerts = []
    needs_update = False  

    print(f"🤖 {len(alerts)}個のアラートをチェックします...")
    
    for i, alert in enumerate(alerts):
        # 1. 1週間期限のチェック
        if 'created_at' in alert:
            created_at = datetime.fromisoformat(alert['created_at'])
            if now_jst - created_at > timedelta(days=7):
                print(f"🗑️ アラート {i+1} は1週間経過したため自動削除します。")
                needs_update = True
                continue
                
        # 2. 回数制限のチェック
        trigger_count = alert.get('trigger_count', 0)
        max_alerts = alert.get('max_alerts', 1)
        if trigger_count >= max_alerts:
            print(f"💤 アラート {i+1} は上限({max_alerts}回)に達しているためスキップします。")
            valid_alerts.append(alert)
            continue

        # 3. 🌟 新機能：日付＋時間の制限チェック
        limit_type = alert.get('time_limit_type', '制限なし')
        limit_datetime_str = alert.get('limit_datetime_str')
        
        if limit_type != "制限なし" and limit_datetime_str:
            # 「2026-03-05 15:00」という文字列を、計算できる日時のデータに変換します
            limit_dt = datetime.strptime(limit_datetime_str, "%Y-%m-%d %H:%M")
            
            if limit_type == "指定時間まで" and now_jst > limit_dt:
                print(f"💤 アラート {i+1} は指定日時({limit_datetime_str})を過ぎたためスキップします。")
                valid_alerts.append(alert)
                continue
            elif limit_type == "指定時間以降" and now_jst < limit_dt:
                print(f"💤 アラート {i+1} は指定日時({limit_datetime_str})前のためスキップします。")
                valid_alerts.append(alert)
                continue

        ticker = pairs[alert['pair']]
        try:
            if alert['tf'] == "4時間足":
                data = yf.download(ticker, period="60d", interval="1h", progress=False)
                data = data.resample('4h').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
            else:
                tf_map = {"5分足": "5m", "15分足": "15m", "1時間足": "1h"}
                data = yf.download(ticker, period="60d", interval=tf_map[alert['tf']], progress=False)

            if data.empty:
                valid_alerts.append(alert)
                continue

            data['SMA6'] = data['Close'].rolling(window=6).mean()
            data['SMA25'] = data['Close'].rolling(window=25).mean()
            data['SMA100'] = data['Close'].rolling(window=100).mean()

            latest, previous = data.iloc[-1], data.iloc[-2]
            def gv(r, c): return float(r[c].iloc[0]) if isinstance(r[c], pd.Series) else float(r[c])
            
            cp, pp = gv(latest, 'Close'), gv(previous, 'Close')
            cs = {"SMA6": gv(latest, 'SMA6'), "SMA25": gv(latest, 'SMA25'), "SMA100": gv(latest, 'SMA100')}
            ps = {"SMA6": gv(previous, 'SMA6'), "SMA25": gv(previous, 'SMA25'), "SMA100": gv(previous, 'SMA100')}

            result_a = eval_cond(alert['cond_a'], cp, pp, cs, ps)
            final_result = result_a
            
            if alert['logic'] == "AND（条件A かつ 条件B）":
                final_result = result_a and eval_cond(alert['cond_b'], cp, pp, cs, ps)
            elif alert['logic'] == "OR（条件A または 条件B）":
                final_result = result_a or eval_cond(alert['cond_b'], cp, pp, cs, ps)

            if final_result:
                alert['trigger_count'] = trigger_count + 1 
                needs_update = True
                msg = f"🚨【FX自動アラート】\n通貨ペア: {alert['pair']} ({alert['tf']})\n現在価格: {cp:.5f}\n条件を満たしました！\n(通知: {alert['trigger_count']}/{max_alerts}回)"
                send_line(msg)
                print(f"✅ アラート発動！LINEに通知しました。")
            else:
                print(f"💤 アラート条件未達です。")
                
        except Exception as e:
            print(f"エラー: {e}")

        valid_alerts.append(alert)

    if needs_update:
        save_alerts(valid_alerts)
        print("💾 アラートの最新状態をJSONBinに保存しました。")

if __name__ == "__main__":
    main()
