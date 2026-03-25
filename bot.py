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
        df_1h = yf.download(ticker, period="30d", interval="1h", progress=False)
        if df_1h.empty: return status
        if isinstance(df_1h.columns, pd.MultiIndex): df_1h.columns = df_1h.columns.get_level_values(0)
        df_1h = calc_radar_indicators(df_1h)
        
        status["1h_c"] = float(df_1h['Close'].iloc[-1])
        status["1h_h"] = float(df_1h['High'].iloc[-1])
        status["1h_l"] = float(df_1h['Low'].iloc[-1])
        status["1h_k"] = float(df_1h['Kijun'].iloc[-1])
        status["1h_sma"] = float(df_1h['SMA100'].iloc[-1])
        status["time_now"] = df_1h.index[-1].isoformat()

        df_clean = df_1h.dropna(subset=['SMA100', 'Kijun'])
        if not df_clean.empty:
            is_buy_series = df_clean['Kijun'] > df_clean['SMA100']
            changes = is_buy_series[is_buy_series != is_buy_series.shift(1)]
            cross_time = changes.index[-1] if len(changes) > 1 else df_clean.index[0]
            status["cross_time"] = cross_time.isoformat()
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

# 🌟 抜け落ちていたアラート用の補助関数群を完全復元 🌟
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
        if state in ["上昇トレンド", "仮上昇トレンド"] and baseline and cp < baseline: state, baseline = "レンジ", None
        elif state in ["下降トレンド", "仮下降トレンド"] and baseline and cp > baseline: state, baseline = "レンジ", None
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
    now_jst = datetime.utcnow() + timedelta(hours=9)
    is_weekend = False
    if now_jst.weekday() == 5 and now_jst.hour >= 8: is_weekend = True
    elif now_jst.weekday() == 6: is_weekend = True
    elif now_jst.weekday() == 0 and now_jst.hour < 6: is_weekend = True

    if is_weekend: return

    data = load_data()
    is_changed = False
    
    # 🌟 抜け落ちていたアラート実行エンジンを完全復元 🌟
    alerts = data.get("alerts", [])
    valid_alerts = []
    
    for alert in alerts:
        if 'created_at' in alert:
            created_at = datetime.fromisoformat(alert['created_at'])
            if now_jst - created_at > timedelta(days=7): 
                is_changed = True
                continue 

        limit_mode = alert.get('time_mode', 'なし（1週間で自動無効）')
        if limit_mode != 'なし（1週間で自動無効）' and alert.get('limit_dt'):
            limit_dt = datetime.fromisoformat(alert['limit_dt']).replace(tzinfo=None)
            if limit_mode == "指定日時まで有効" and now_jst > limit_dt:
                is_changed = True
                continue
            if limit_mode == "指定日時以降に有効" and now_jst < limit_dt:
                valid_alerts.append(alert)
                continue

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
            recent_closes = [float(v.iloc[0] if isinstance(v, pd.Series) else v) for v in df['Close'].tail(4)]

            if sit == "上昇トレンドが始まったら" and curr_code in [1, 2]: trigger = True
            elif sit == "下降トレンドが始まったら" and curr_code in [3, 4]: trigger = True
            elif sit == "トレンドが始まったら" and curr_code in [1, 2, 3, 4]: trigger = True
            elif sit == "上昇トレンドが終了したら" and base:
                if any(c < base for c in recent_closes): trigger = True
            elif sit == "下降トレンドが終了したら" and base:
                if any(c > base for c in recent_closes): trigger = True

            if trigger:
                msg = f"📈【トレンドアラート】\n{alert['pair']} ({alert['tf']})\n設定: {sit}\n現在値: {cp:.5f}\n条件を満たしました！"
                send_line(msg)
                is_changed = True
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
                alert['current_count'] = alert.get('current_count', 0) + 1
                max_c = alert.get('max_count', 1)
                msg = f"🚨【通常アラート】({alert['current_count']}/{max_c}回目)\n{alert['pair']} ({alert['tf']})\n現在値: {cp:.5f}\n(高値: {ch:.5f} / 安値: {cl:.5f})\n条件を満たしました！"
                send_line(msg)
                is_changed = True
                
                if alert['current_count'] >= max_c: continue 
                else:
                    valid_alerts.append(alert) 
                    continue 

        valid_alerts.append(alert)

    if is_changed or len(valid_alerts) != len(alerts):
        data["alerts"] = valid_alerts
        is_changed = True

    # === 🌍 最強レーダー心臓部 ===
    radar_data = data.get("radar", {})

    for pair_key, state in radar_data.items():
        if not state.get("active", False): continue

        ticker = pairs[pair_key]
        env = get_env_status(ticker)
        if env["1h_c"] == 0: continue 
        
        is_buy = (env["1h_k"] > env["1h_sma"])
        time_now = env["time_now"]

        if state["phase"] == 4:
            if is_buy and env["1h_c"] > env["1h_k"]:
                state.update({"phase": 1, "cycle": 1, "0_pct": env["1h_h"], "time_0": time_now, "target_15m": 0, "time_tgt": ""})
                is_changed = True
            elif not is_buy and env["1h_c"] < env["1h_k"]:
                state.update({"phase": 1, "cycle": 1, "0_pct": env["1h_l"], "time_0": time_now, "target_15m": 0, "time_tgt": ""})
                is_changed = True
            continue

        if state["phase"] == 1:
            if is_buy:
                if env["1h_h"] > state.get("0_pct", 0):
                    state["0_pct"], state["time_0"] = env["1h_h"], time_now
                if env["1h_c"] < env["1h_k"]:
                    if state.get("100_pct", 0) == 0: state["100_pct"], state["time_100"] = env["1h_sma"], time_now
                    state.update({"phase": 2, "current_lowest": env["1h_l"], "current_lowest_time": time_now, "timer": 0, "notified_p2": False, "notified_p3_count": 0})
                    is_changed = True
            else:
                if state.get("0_pct", 0) == 0 or env["1h_l"] < state["0_pct"]:
                    state["0_pct"], state["time_0"] = env["1h_l"], time_now
                if env["1h_c"] > env["1h_k"]:
                    if state.get("100_pct", 0) == 0: state["100_pct"], state["time_100"] = env["1h_sma"], time_now
                    state.update({"phase": 2, "current_lowest": env["1h_h"], "current_lowest_time": time_now, "timer": 0, "notified_p2": False, "notified_p3_count": 0})
                    is_changed = True
                    
        elif state["phase"] in [2, 3]:
            state["timer"] = state.get("timer", 0) + 1
            
            cancel = False
            if state["timer"] >= 72: cancel = True
            if is_buy and (env["1h_c"] < state["100_pct"]): cancel = True
            if not is_buy and (env["1h_c"] > state["100_pct"]): cancel = True
            
            if cancel:
                state.update({"phase": 4, "cycle": 1, "100_pct": 0, "0_pct": 0, "target_15m": 0, "time_tgt": ""})
                is_changed = True
                continue

            # 🌟 エラー対策：データがない場合は現在のレートを強制セット
            if "current_lowest" not in state or state["current_lowest"] == 0:
                state["current_lowest"] = env["1h_l"] if is_buy else env["1h_h"]
                state["current_lowest_time"] = time_now
            else:
                if is_buy and env["1h_l"] < state["current_lowest"]:
                    state["current_lowest"], state["current_lowest_time"] = env["1h_l"], time_now
                elif not is_buy and env["1h_h"] > state["current_lowest"]:
                    state["current_lowest"], state["current_lowest_time"] = env["1h_h"], time_now

            if (is_buy and env["1h_h"] > state["0_pct"]) or (not is_buy and env["1h_l"] < state["0_pct"]):
                state["100_pct"], state["time_100"] = state["current_lowest"], state["current_lowest_time"]
                state["0_pct"], state["time_0"] = (env["1h_h"], time_now) if is_buy else (env["1h_l"], time_now)
                state.update({"phase": 1, "cycle": state.get("cycle", 1) + 1, "target_15m": 0, "time_tgt": ""})
                is_changed = True
                cross_str = f" ({fmt_t(env.get('cross_time'))}〜)" if env.get('cross_time') else ""
                msg = f"🚀 【①開始待ち (第{state['cycle']}ｻｲｸﾙ)】\n🌍 {pair_key} : {'🔴 買い目線' if is_buy else '🔵 売り目線'}{cross_str}\nトレンド継続！0%を更新しました。\n\n[基準レート]\n100%: {state['100_pct']:.5f} ({fmt_t(state['time_100'])})\n\n次の②準備期(押し目)を待機します。"
                send_line(msg)
                continue

            target_15m, target_time = get_15m_breakout_target(ticker, is_buy)
            if target_15m:
                state["target_15m"], state["time_tgt"] = target_15m, target_time
            
            if state["phase"] == 2:
                if not state.get("notified_p2", False):
                    cross_str = f" ({fmt_t(env.get('cross_time'))}〜)" if env.get('cross_time') else ""
                    cl_label = "押し安値" if is_buy else "戻り高値"
                    cl = state.get('current_lowest', 0)
                    cl_t = state.get('current_lowest_time', '')
                    cl_str = f"\n{cl_label}: {cl:.5f} ({fmt_t(cl_t)})" if cl != 0 else ""
                    tgt_str = f"\nﾌﾞﾚｲｸ基準: {target_15m:.5f} ({fmt_t(target_time)})" if target_15m else "\nﾌﾞﾚｲｸ基準: 探索中..."
                    msg = f"📉 【②準備待ち (第{state.get('cycle', 1)}ｻｲｸﾙ)】\n🌍 {pair_key} : {'🔴 買い目線' if is_buy else '🔵 売り目線'}{cross_str}\n1時間足が基準線を割りました。\n\n[基準レート]\n0%: {state['0_pct']:.5f} ({fmt_t(state['time_0'])}){cl_str}\n100%: {state['100_pct']:.5f} ({fmt_t(state['time_100'])}){tgt_str}\n\n15分足のブレイクアウトを待機します！"
                    send_line(msg)
                    state["notified_p2"] = True
                    is_changed = True
                
                if target_15m:
                    if (is_buy and env["1h_c"] > target_15m) or (not is_buy and env["1h_c"] < target_15m):
                        state["phase"] = 3
                        is_changed = True
            
            if state["phase"] == 3:
                if state.get("notified_p3_count", 0) < 2:
                    range_diff = abs(state["0_pct"] - state["100_pct"])
                    # 🌟 エラー対策：データ取得を安全な形に変更
                    cl = state.get('current_lowest', env["1h_l"] if is_buy else env["1h_h"])
                    ret_pct = abs(state["0_pct"] - cl) / range_diff * 100 if range_diff > 0 else 0
                    tgt, ttgt = state.get('target_15m', 0), state.get('time_tgt', '')
                    cross_str = f" ({fmt_t(env.get('cross_time'))}〜)" if env.get('cross_time') else ""
                    msg = f"🔥 【③ｴﾝﾄﾘｰ待ち (第{state.get('cycle', 1)}ｻｲｸﾙ)】\n🌍 {pair_key} : {'🔴 買い目線' if is_buy else '🔵 売り目線'}{cross_str}\n15分足の戻り高値をブレイクしました！\n\n[基準レート]\nﾌﾞﾚｲｸ基準: {tgt:.5f} ({fmt_t(ttgt)})\n📉 押し目の深さ：{ret_pct:.1f}%\n\n今すぐチャートを確認してください！"
                    send_line(msg)
                    state["notified_p3_count"] = state.get("notified_p3_count", 0) + 1
                    is_changed = True

    if is_changed:
        data["radar"] = radar_data
        save_data(data)

if __name__ == "__main__":
    main()
