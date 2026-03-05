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

def load_data():
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}"
    headers = {"X-Master-Key": JSONBIN_KEY}
    res = requests.get(url, headers=headers)
    if res.status_code == 200: return res.json().get("record", {})
    return {"alerts": [], "execution_logs": []}

def save_data(data):
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}"
    headers = {"X-Master-Key": JSONBIN_KEY, "Content-Type": "application/json"}
    requests.put(url, headers=headers, json=data)

cache_data = {}
def get_cached_df(ticker, tf):
    key = f"{ticker}_{tf}"
    if key in cache_data: return cache_data[key]
    
    tf_map = {"5分足": "5m", "15分足": "15m", "1時間足": "1h"}
    if tf == "4時間足":
        df = yf.download(ticker, period="60d", interval="1h", progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df.resample('4h').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
    else:
        df = yf.download(ticker, period="60d", interval=tf_map[tf], progress=False)
        if not df.empty and isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
    cache_data[key] = df
    return df

def analyze_dow_trend(df):
    highs, lows, closes = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    alt_ext = []
    for i in range(6, len(df)):
        fut = min(6, len(df) - 1 - i)
        w_high, w_low = highs.iloc[i-6 : i+fut+1], lows.iloc[i-6 : i+fut+1]
        if highs.iloc[i] == w_high.max(): alt_ext.append({'idx': i, 'val': float(highs.iloc[i]), 'type': 'peak', 'conf': fut==6})
        if lows.iloc[i] == w_low.min(): alt_ext.append({'idx': i, 'val': float(lows.iloc[i]), 'type': 'trough', 'conf': fut==6})

    filtered = []
    for e in alt_ext:
        if not filtered: filtered.append(e)
        else:
            last_e = filtered[-1]
            if last_e['type'] == e['type']:
                if (e['type'] == 'peak' and e['val'] > last_e['val']) or (e['type'] == 'trough' and e['val'] < last_e['val']):
                    filtered[-1] = e
            else: filtered.append(e)

    state, baseline = "レンジ", None
    h_hist, l_hist = [], []

    for i in range(len(df)):
        e = next((x for x in filtered if x['idx'] == i), None)
        if e:
            if e['type'] == 'peak':
                h_hist.append(e)
                if state in ["下降トレンド", "仮下降トレンド"]: baseline = e['val']
            else:
                l_hist.append(e)
                if state in ["上昇トレンド", "仮上昇トレンド"]: baseline = e['val']
                
            if len(h_hist) >= 2 and len(l_hist) >= 2:
                H1, H2, L1, L2 = h_hist[-2], h_hist[-1], l_hist[-2], l_hist[-1]
                if L1['idx'] < H1['idx'] < L2['idx'] < H2['idx'] and e['idx'] == H2['idx']:
                    if L1['val'] < L2['val'] and H1['val'] < H2['val']:
                        state = "上昇トレンド" if H2['conf'] else "仮上昇トレンド"
                        baseline = L2['val']
                elif H1['idx'] < L1['idx'] < H2['idx'] < L2['idx'] and e['idx'] == L2['idx']:
                    if H1['val'] > H2['val'] and L1['val'] > L2['val']:
                        state = "下降トレンド" if L2['conf'] else "仮下降トレンド"
                        baseline = H2['val']

        cp = float(closes.iloc[i])
        if state in ["上昇トレンド", "仮上昇トレンド"] and baseline and cp < baseline:
            state, baseline = "レンジ", None
        elif state in ["下降トレンド", "仮下降トレンド"] and baseline and cp > baseline:
            state, baseline = "レンジ", None

    state_map = {"上昇トレンド": 1, "仮上昇トレンド": 2, "下降トレンド": 3, "仮下降トレンド": 4, "レンジ": 5}
    return state_map[state]

def check_cross(prev_price, curr_high, curr_low, prev_target, curr_target, mode):
    up = (prev_price <= prev_target and curr_high > curr_target)
    down = (prev_price >= prev_target and curr_low < curr_target)
    if mode == "上回る": return up
    if mode == "下回る": return down
    if mode == "交差": return up or down
    return False

def eval_cond(cond, pp, ch, cl, ps, cs):
    if cond["type"] == "① 価格×価格": return check_cross(pp, ch, cl, cond["target_price"], cond["target_price"], cond["direction"])
    elif cond["type"] == "② 価格×SMA": return check_cross(pp, ch, cl, ps[cond["target_sma"]], cs[cond["target_sma"]], cond["direction"])
    elif cond["type"] == "③ SMA×SMA": return check_cross(ps[cond["sma1"]], cs[cond["sma1"]], cs[cond["sma1"]], ps[cond["sma2"]], cs[cond["sma2"]], cond["direction"])
    return False

def main():
    data = load_data()
    alerts = data.get("alerts", [])
    logs = data.get("execution_logs", [])

    now_jst = datetime.utcnow() + timedelta(hours=9)
    logs.append(now_jst.strftime("%Y-%m-%d %H:%M:%S"))
    data["execution_logs"] = logs[-10:]

    if not alerts:
        save_data(data)
        return

    valid_alerts = []
    
    for alert in alerts:
        if 'created_at' in alert:
            created_at = datetime.fromisoformat(alert['created_at'])
            if now_jst - created_at > timedelta(days=7): continue

        ticker = pairs[alert['pair']]
        df = get_cached_df(ticker, alert['tf'])
        if df.empty:
            valid_alerts.append(alert)
            continue

        trigger = False
        val = df['Close'].iloc[-1]
        cp = float(val.iloc[0] if isinstance(val, pd.Series) else val)

        if alert.get('type') == 'trend':
            curr_code = analyze_dow_trend(df)
            sit = alert['situation']
            base = alert.get('baseline_rate')
            
            # 🌟 新機能：ロボットが寝ていた間に確定したローソク足（直近4本分）の終値をすべて取得
            # これにより、5分足設定時でも15分間の間の「終値でのブレイク」を絶対に見逃しません。
            recent_closes = [float(v.iloc[0] if isinstance(v, pd.Series) else v) for v in df['Close'].tail(4)]

            if sit == "上昇トレンドが始まったら" and curr_code in [1, 2]: trigger = True
            elif sit == "下降トレンドが始まったら" and curr_code in [3, 4]: trigger = True
            elif sit == "トレンドが始まったら" and curr_code in [1, 2, 3, 4]: trigger = True
            elif sit == "上昇トレンドが終了したら" and base:
                # 過去4本の終値のうち、1つでも基準レートを下回っていれば通知！
                if any(c < base for c in recent_closes): trigger = True
            elif sit == "下降トレンドが終了したら" and base:
                # 過去4本の終値のうち、1つでも基準レートを上回っていれば通知！
                if any(c > base for c in recent_closes): trigger = True

            if trigger:
                msg = f"📈【トレンドアラート】\n{alert['pair']} ({alert['tf']})\n設定: {sit}\n現在値: {cp:.5f}\n条件を満たしました！"
                send_line(msg)
                print(f"✅ トレンドアラート発動 ({alert['pair']})")
                continue 

        else:
            df['SMA6'] = df['Close'].rolling(window=6).mean()
            df['SMA25'] = df['Close'].rolling(window=25).mean()
            df['SMA100'] = df['Close'].rolling(window=100).mean()

            latest, previous = df.iloc[-1], df.iloc[-2]
            def gv(r, c): return float(r[c].iloc[0]) if isinstance(r[c], pd.Series) else float(r[c])
            
            pp = gv(previous, 'Close')
            ch, cl = gv(latest, 'High'), gv(latest, 'Low')
            cs = {"SMA6": gv(latest, 'SMA6'), "SMA25": gv(latest, 'SMA25'), "SMA100": gv(latest, 'SMA100')}
            ps = {"SMA6": gv(previous, 'SMA6'), "SMA25": gv(previous, 'SMA25'), "SMA100": gv(previous, 'SMA100')}

            result_a = eval_cond(alert['cond_a'], pp, ch, cl, ps, cs)
            final_result = result_a
            
            if alert.get('logic') == "AND（条件A かつ 条件B）": final_result = result_a and eval_cond(alert['cond_b'], pp, ch, cl, ps, cs)
            elif alert.get('logic') == "OR（条件A または 条件B）": final_result = result_a or eval_cond(alert['cond_b'], pp, ch, cl, ps, cs)

            if final_result:
                msg = f"🚨【FX通常アラート】\n通貨ペア: {alert['pair']} ({alert['tf']})\n現在値: {cp:.5f}\n(高値: {ch:.5f} / 安値: {cl:.5f})\n条件を満たしました！"
                send_line(msg)
                print(f"✅ 通常アラート発動 ({alert['pair']})")
                continue 

        valid_alerts.append(alert)

    data["alerts"] = valid_alerts
    save_data(data)

if __name__ == "__main__":
    main()
