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
    "USDCHF": "USDCHF=X", 
    "EURAUD": "EURAUD=X",
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

def calc_radar_indicators(df):
    df['SMA100'] = df['Close'].rolling(window=100).mean()
    high26 = df['High'].rolling(window=26).max()
    low26 = df['Low'].rolling(window=26).min()
    df['Kijun'] = (high26 + low26) / 2
    return df

def get_env_status(ticker):
    status = {"dir": "エラー", "1h_c": 0}
    try:
        df_1h = yf.download(ticker, period="10d", interval="1h", progress=False)
        if df_1h.empty: return status
        if isinstance(df_1h.columns, pd.MultiIndex): df_1h.columns = df_1h.columns.get_level_values(0)
        df_1h = calc_radar_indicators(df_1h)
        status["1h_c"] = float(df_1h['Close'].iloc[-1])
        status["1h_h"] = float(df_1h['High'].iloc[-1])
        status["1h_l"] = float(df_1h['Low'].iloc[-1])
        status["1h_k"] = float(df_1h['Kijun'].iloc[-1])
        status["1h_sma"] = float(df_1h['SMA100'].iloc[-1])
        status["time_now"] = df_1h.index[-1].isoformat()
    except Exception: pass
    return status

def get_15m_breakout_target(ticker, is_buy):
    df = get_cached_df(ticker, "15分足")
    if df.empty or len(df) < 10: return None, None
    highs, lows, times = df['High'].squeeze(), df['Low'].squeeze(), df.index
    for i in range(len(df)-3, 5, -1):
        w_high = highs.iloc[i-6 : i+3]
        w_low = lows.iloc[i-6 : i+3]
        if is_buy:
            if highs.iloc[i] == w_high.max(): return float(highs.iloc[i]), times[i].isoformat()
        else:
            if lows.iloc[i] == w_low.min(): return float(lows.iloc[i]), times[i].isoformat()
    return None, None

def fmt_t(t_str):
    if not t_str: return ""
    try:
        dt = pd.to_datetime(t_str)
        if dt.tzinfo is not None: dt = dt.tz_convert('Asia/Tokyo')
        else: dt = dt.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return dt.strftime('%m/%d %H:%M')
    except: return ""

def main():
    now_jst = datetime.utcnow() + timedelta(hours=9)
    is_weekend = False
    if now_jst.weekday() == 5 and now_jst.hour >= 8: is_weekend = True
    elif now_jst.weekday() == 6: is_weekend = True
    elif now_jst.weekday() == 0 and now_jst.hour < 6: is_weekend = True

    if is_weekend: return

    data = load_data()
    
    # === レーダー心臓部 ===
    radar_data = data.get("radar", {})
    radar_changed = False

    for pair_key, state in radar_data.items():
        if not state.get("active", False): continue

        ticker = pairs[pair_key]
        env = get_env_status(ticker)
        if env["1h_c"] == 0: continue 
        
        is_buy = (env["1h_k"] > env["1h_sma"])
        time_now = env["time_now"]

        # 🌟 フェーズ4 (方向感無し) からの復帰ロジック
        if state["phase"] == 4:
            if is_buy and env["1h_c"] > env["1h_k"]:
                state.update({"phase": 1, "cycle": 1, "0_pct": env["1h_h"], "time_0": time_now})
                radar_changed = True
            elif not is_buy and env["1h_c"] < env["1h_k"]:
                state.update({"phase": 1, "cycle": 1, "0_pct": env["1h_l"], "time_0": time_now})
                radar_changed = True
            continue

        if state["phase"] == 1:
            if is_buy:
                if env["1h_h"] > state.get("0_pct", 0):
                    state["0_pct"], state["time_0"] = env["1h_h"], time_now
                if env["1h_c"] < env["1h_k"]:
                    if state.get("100_pct", 0) == 0: state["100_pct"], state["time_100"] = env["1h_sma"], time_now
                    state.update({"phase": 2, "current_lowest": env["1h_l"], "current_lowest_time": time_now, "timer": 0, "notified_p2": False, "notified_p3_count": 0})
                    radar_changed = True
            else:
                if state.get("0_pct", 0) == 0 or env["1h_l"] < state["0_pct"]:
                    state["0_pct"], state["time_0"] = env["1h_l"], time_now
                if env["1h_c"] > env["1h_k"]:
                    if state.get("100_pct", 0) == 0: state["100_pct"], state["time_100"] = env["1h_sma"], time_now
                    state.update({"phase": 2, "current_lowest": env["1h_h"], "current_lowest_time": time_now, "timer": 0, "notified_p2": False, "notified_p3_count": 0})
                    radar_changed = True
                    
        elif state["phase"] in [2, 3]:
            state["timer"] = state.get("timer", 0) + 1
            
            # 🌟 100%割れ等の矛盾で「方向感無し(Phase 4)」へ
            cancel = False
            if state["timer"] >= 72: cancel = True
            if is_buy and (env["1h_c"] < state["100_pct"]): cancel = True
            if not is_buy and (env["1h_c"] > state["100_pct"]): cancel = True
            
            if cancel:
                state.update({"phase": 4, "cycle": 1, "100_pct": 0, "0_pct": 0})
                radar_changed = True
                continue

            if is_buy:
                if env["1h_l"] < state.get("current_lowest", env["1h_l"]):
                    state["current_lowest"], state["current_lowest_time"] = env["1h_l"], time_now
            else:
                if env["1h_h"] > state.get("current_lowest", env["1h_h"]):
                    state["current_lowest"], state["current_lowest_time"] = env["1h_h"], time_now

            # 0%更新で次サイクルへ
            if (is_buy and env["1h_h"] > state["0_pct"]) or (not is_buy and env["1h_l"] < state["0_pct"]):
                state["100_pct"], state["time_100"] = state["current_lowest"], state["current_lowest_time"]
                state["0_pct"], state["time_0"] = (env["1h_h"], time_now) if is_buy else (env["1h_l"], time_now)
                state["phase"] = 1
                state["cycle"] = state.get("cycle", 1) + 1
                radar_changed = True
                msg = f"🚀 【①開始待ち (第{state['cycle']}ｻｲｸﾙ)】\n🌍 {pair_key} : {'🔴 買い目線' if is_buy else '🔵 売り目線'}\nトレンド継続！0%を更新しました。\n\n[基準レート]\n100%: {state['100_pct']:.5f} ({fmt_t(state['time_100'])})\n\n次の②準備期(押し目)を待機します。"
                send_line(msg)
                continue

            target_15m, target_time = get_15m_breakout_target(ticker, is_buy)
            if target_15m:
                state["target_15m"], state["time_tgt"] = target_15m, target_time
            
            if state["phase"] == 2:
                if not state.get("notified_p2", False):
                    msg = f"📉 【②準備待ち (第{state.get('cycle', 1)}ｻｲｸﾙ)】\n🌍 {pair_key} : {'🔴 買い目線' if is_buy else '🔵 売り目線'}\n1時間足が基準線を割りました。\n\n[基準レート]\n0%: {state['0_pct']:.5f} ({fmt_t(state['time_0'])})\n100%: {state['100_pct']:.5f} ({fmt_t(state['time_100'])})\n\n15分足のブレイクアウトを待機します！"
                    send_line(msg)
                    state["notified_p2"] = True
                    radar_changed = True
                
                if target_15m:
                    if (is_buy and env["1h_c"] > target_15m) or (not is_buy and env["1h_c"] < target_15m):
                        state["phase"] = 3
                        radar_changed = True
            
            if state["phase"] == 3:
                if state.get("notified_p3_count", 0) < 2:
                    range_diff = abs(state["0_pct"] - state["100_pct"])
                    ret_pct = abs(state["0_pct"] - state["current_lowest"]) / range_diff * 100 if range_diff > 0 else 0
                    tgt, ttgt = state.get('target_15m', 0), state.get('time_tgt', '')
                    msg = f"🔥 【③ｴﾝﾄﾘｰ待ち (第{state.get('cycle', 1)}ｻｲｸﾙ)】\n🌍 {pair_key} : {'🔴 買い目線' if is_buy else '🔵 売り目線'}\n15分足の戻り高値をブレイクしました！\n\n[基準レート]\nﾌﾞﾚｲｸ基準: {tgt:.5f} ({fmt_t(ttgt)})\n📉 押し目の深さ：{ret_pct:.1f}%\n\n今すぐチャートを確認してください！"
                    send_line(msg)
                    state["notified_p3_count"] = state.get("notified_p3_count", 0) + 1
                    radar_changed = True

    if radar_changed:
        data["radar"] = radar_data
        save_data(data)

if __name__ == "__main__":
    main()
