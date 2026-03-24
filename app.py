import streamlit as st
import requests
import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

JSONBIN_ID = os.environ.get("JSONBIN_BIN_ID")
JSONBIN_KEY = os.environ.get("JSONBIN_API_KEY")
LINE_TOKEN = os.environ.get("LINE_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
MAX_ALERTS_LIMIT = 15

pairs = {
    "USDJPY": "USDJPY=X", "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "EURGBP": "EURGBP=X",
    "AUDJPY": "AUDJPY=X", "CADJPY": "CADJPY=X", "CHFJPY": "CHFJPY=X",
    "GBPAUD": "GBPAUD=X", "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X", 
    "EURAUD": "EURAUD=X",
    "GOLD": "GC=F", "SILVER": "SI=F"
}

@st.cache_data(ttl=300)
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
    st.cache_data.clear()

def send_line(msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    requests.post(url, headers=headers, json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg}]})

def get_current_rate(ticker):
    df = yf.download(ticker, period="1d", interval="1m", progress=False)
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        val = df['Close'].iloc[-1]
        return float(val.iloc[0] if isinstance(val, pd.Series) else val)
    return None

def analyze_dow_trend(df):
    highs, lows, closes = df['High'].squeeze(), df['Low'].squeeze(), df['Close'].squeeze()
    times = df.index
    alt_ext = []
    
    for i in range(6, len(df)):
        fut = min(6, len(df) - 1 - i)
        w_high, w_low = highs.iloc[i-6 : i+fut+1], lows.iloc[i-6 : i+fut+1]
        
        if highs.iloc[i] == w_high.max():
            alt_ext.append({'idx': i, 'val': float(highs.iloc[i]), 'type': 'peak', 'conf': fut==6, 'time': times[i]})
        if lows.iloc[i] == w_low.min():
            alt_ext.append({'idx': i, 'val': float(lows.iloc[i]), 'type': 'trough', 'conf': fut==6, 'time': times[i]})

    filtered = []
    for e in alt_ext:
        if not filtered: filtered.append(e)
        else:
            last_e = filtered[-1]
            if last_e['type'] == e['type']:
                if (e['type'] == 'peak' and e['val'] > last_e['val']) or (e['type'] == 'trough' and e['val'] < last_e['val']):
                    filtered[-1] = e
            else: filtered.append(e)

    state, last_trend, baseline = "レンジ", "なし", None
    h_hist, l_hist = [], []
    r_h1 = r_h2 = r_l1 = r_l2 = 0.0
    t_h1 = t_h2 = t_l1 = t_l2 = None

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
                        baseline, last_trend = L2['val'], state
                        r_h1, r_h2, r_l1, r_l2 = H1['val'], H2['val'], L1['val'], L2['val']
                        t_h1, t_h2, t_l1, t_l2 = H1['time'], H2['time'], L1['time'], L2['time']
                elif H1['idx'] < L1['idx'] < H2['idx'] < L2['idx'] and e['idx'] == L2['idx']:
                    if H1['val'] > H2['val'] and L1['val'] > L2['val']:
                        state = "下降トレンド" if L2['conf'] else "仮下降トレンド"
                        baseline, last_trend = H2['val'], state
                        r_h1, r_h2, r_l1, r_l2 = H1['val'], H2['val'], L1['val'], L2['val']
                        t_h1, t_h2, t_l1, t_l2 = H1['time'], H2['time'], L1['time'], L2['time']

        cp = float(closes.iloc[i])
        if state in ["上昇トレンド", "仮上昇トレンド"] and baseline and cp < baseline:
            state, baseline = "レンジ", None
        elif state in ["下降トレンド", "仮下降トレンド"] and baseline and cp > baseline:
            state, baseline = "レンジ", None

    state_map = {"上昇トレンド": 1, "仮上昇トレンド": 2, "下降トレンド": 3, "仮下降トレンド": 4, "レンジ": 5}
    return {"code": state_map[state], "name": state, "last": last_trend, 
            "h1": r_h1, "h2": r_h2, "l1": r_l1, "l2": r_l2,
            "t_h1": t_h1, "t_h2": t_h2, "t_l1": t_l1, "t_l2": t_l2}

# === レーダー用 計算エンジン ===
def calc_radar_indicators(df):
    df['SMA100'] = df['Close'].rolling(window=100).mean()
    high26 = df['High'].rolling(window=26).max()
    low26 = df['Low'].rolling(window=26).min()
    df['Kijun'] = (high26 + low26) / 2
    return df

@st.cache_data(ttl=300, show_spinner=False)
def get_env_status(ticker):
    # 🌟 初期値に dir_4h と dir_d を追加
    status = {"match": False, "dir": "エラー", "dir_4h": "-", "dir_d": "-", "1h_k": 0, "1h_c": 0, "1h_sma": 0, "sim_phase": 1, "sim_cycle": 1, "sim_0_pct": 0, "sim_100_pct": 0}
    try:
        df_1h_30d = yf.download(ticker, period="30d", interval="1h", progress=False)
        df_d = yf.download(ticker, period="60d", interval="1d", progress=False)
        
        if df_1h_30d.empty or df_d.empty: return status

        for df in [df_1h_30d, df_d]:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        df_4h = df_1h_30d.resample('4h').agg({'High':'max', 'Low':'min', 'Close':'last'}).dropna()

        df_1h_30d = calc_radar_indicators(df_1h_30d)
        df_4h = calc_radar_indicators(df_4h)
        df_d = calc_radar_indicators(df_d)

        phase, cycle = 1, 1
        pct_0, pct_100, timer, current_lowest = 0.0, 0.0, 0, 0.0
        last_mode = None

        df_sim = df_1h_30d.dropna(subset=['SMA100', 'Kijun']).tail(336)
        for i in range(len(df_sim)):
            c, k, sma = float(df_sim['Close'].iloc[i]), float(df_sim['Kijun'].iloc[i]), float(df_sim['SMA100'].iloc[i])
            is_buy_mode = (k > sma)
            
            if last_mode is not None and is_buy_mode != last_mode:
                phase, cycle, pct_0, pct_100 = 1, 1, 0.0, 0.0
            last_mode = is_buy_mode

            if phase == 1:
                if is_buy_mode:
                    if c > pct_0: pct_0 = c
                    if c < k:
                        if pct_100 == 0: pct_100 = sma
                        phase, current_lowest, timer = 2, c, 0
                else:
                    if pct_0 == 0 or c < pct_0: pct_0 = c
                    if c > k:
                        if pct_100 == 0: pct_100 = sma
                        phase, current_lowest, timer = 2, c, 0
            else:
                timer += 1
                cancel = (timer >= 72) or (is_buy_mode and c < pct_100) or (not is_buy_mode and c > pct_100)
                if cancel:
                    phase, cycle, pct_0, pct_100 = 1, 1, 0.0, 0.0
                    continue
                
                if is_buy_mode:
                    current_lowest = min(current_lowest, c)
                    if c > pct_0:
                        pct_100, pct_0, phase, cycle = current_lowest, c, 1, cycle + 1
                else:
                    current_lowest = max(current_lowest, c)
                    if c < pct_0:
                        pct_100, pct_0, phase, cycle = current_lowest, c, 1, cycle + 1

        status["sim_phase"] = phase
        status["sim_cycle"] = cycle
        status["sim_0_pct"] = pct_0
        status["sim_100_pct"] = pct_100

        c1, k1 = df_1h_30d['Close'].iloc[-1], df_1h_30d['Kijun'].iloc[-1]
        c4, k4 = df_4h['Close'].iloc[-1], df_4h['Kijun'].iloc[-1]
        cd, kd = df_d['Close'].iloc[-1], df_d['Kijun'].iloc[-1]
        
        dir1 = "買" if c1 > k1 else "売"
        dir4 = "買" if c4 > k4 else "売"
        dird = "買" if cd > kd else "売"

        status["1h_c"] = float(c1)
        status["1h_k"] = float(k1)
        status["1h_sma"] = float(df_1h_30d['SMA100'].iloc[-1])
        status["dir"] = dir1
        status["dir_4h"] = dir4  # 🌟 4H目線を保存
        status["dir_d"] = dird   # 🌟 日足目線を保存
        status["match"] = (dir1 == dir4 == dird)
    except Exception as e:
        pass
    return status

# === 【追加部品②】環境認識＆手法レーダー UI ===
st.divider()
st.subheader("🌍 環境認識＆手法レーダー (別枠監視)")

radar_data = data.get("radar", {})

with st.expander("レーダーを展開する", expanded=False):
    if st.button("🔄 全通貨を一括取得する (※Yahoo制限に注意 / 数十秒かかります)"):
        with st.spinner("全通貨のデータを取得中..."):
            for pair_key, ticker in pairs.items():
                st.session_state[f"env_cache_{pair_key}"] = get_env_status(ticker)

    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([2, 1.5, 2.5, 2.5, 1.5])
    with col_h1: st.caption("通貨ペア")
    with col_h2: st.caption("個別取得")
    with col_h3: st.caption("目線 (環境認識)")
    with col_h4: st.caption("フェーズ / 基準レート")
    with col_h5: st.caption("個別監視")
    st.write("---")

    for pair_key, ticker in pairs.items():
        if pair_key not in radar_data:
            radar_data[pair_key] = {"active": False, "phase": 0, "cycle": 1, "0_pct": 0, "100_pct": 0}
        
        r_state = radar_data[pair_key]
        col1, col2, col3, col4, col5 = st.columns([2, 1.5, 2.5, 2.5, 1.5])
        
        with col1:
            st.write(f"**{pair_key}**")
            
        with col2:
            if st.button("🔄", key=f"get_{pair_key}"):
                with st.spinner(""):
                    st.session_state[f"env_cache_{pair_key}"] = get_env_status(ticker)
                    
        with col3:
            env_data = st.session_state.get(f"env_cache_{pair_key}")
            if env_data:
                if env_data['dir'] == "エラー":
                    st.write("⚠️ 取得失敗")
                else:
                    mark = "🔴" if env_data['dir'] == "買" else "🔵" if env_data['dir'] == "売" else "⚪️"
                    match_str = "〇" if env_data['match'] else "×"
                    st.write(f"{mark} {env_data['dir']} (一致{match_str})")
                    # 🌟 買(一致〇) の下に、日足と4Hの目線を小さく追加！
                    st.caption(f"日: {env_data.get('dir_d', '-')} / 4H: {env_data.get('dir_4h', '-')}")
            else:
                st.write("⚪️ 未取得")
                
        with col4:
            if r_state["active"]:
                p = r_state.get('phase', 0)
                phase_map = {0: "待機中", 1: "①開始待ち", 2: "②準備待ち", 3: "③ｴﾝﾄﾘｰ待ち"}
                st.write(f"**{phase_map.get(p, '待機中')}** (第{r_state.get('cycle', 1)}ｻｲｸﾙ)")
                
                p0 = r_state.get('0_pct', 0)
                p100 = r_state.get('100_pct', 0)
                tgt = r_state.get('target_15m', 0)
                
                if p == 1 and p100 != 0:
                    st.code(f"100%: {p100:.5f}")
                elif p == 2:
                    st.code(f"0%: {p0:.5f}\n100%: {p100:.5f}")
                elif p == 3 and tgt != 0:
                    st.code(f"ﾌﾞﾚｲｸ基準: {tgt:.5f}")
            else:
                if env_data and env_data['dir'] != "エラー":
                    sim_p = env_data.get('sim_phase', 1)
                    sim_c = env_data.get('sim_cycle', 1)
                    sim_0 = env_data.get('sim_0_pct', 0)
                    sim_100 = env_data.get('sim_100_pct', 0)
                    
                    p_str = "①開始待ち" if sim_p == 1 else "②準備/ｴﾝﾄﾘｰ"
                    st.write(f"_{p_str}_ (第{sim_c}ｻｲｸﾙ)")
                    
                    if sim_p == 1 and sim_100 != 0:
                        st.code(f"100%: {sim_100:.5f}")
                    elif sim_p == 2 and sim_0 != 0:
                        st.code(f"0%: {sim_0:.5f}\n100%: {sim_100:.5f}")
                else:
                    st.write("待機(停止中)")
                
        with col5:
            btn_label = "🛑 停止" if r_state["active"] else "👀 監視"
            if st.button(btn_label, key=f"btn_r_{pair_key}"):
                r_state["active"] = not r_state["active"]
                if r_state["active"]:
                    # 🌟 監視ONにした瞬間、シミュレーション結果を引き継ぐ！！
                    env_data = st.session_state.get(f"env_cache_{pair_key}")
                    if env_data and env_data['dir'] != "エラー":
                        r_state["phase"] = env_data.get("sim_phase", 1)
                        r_state["cycle"] = env_data.get("sim_cycle", 1)
                        r_state["0_pct"] = env_data.get("sim_0_pct", 0)
                        r_state["100_pct"] = env_data.get("sim_100_pct", 0)
                    else:
                        r_state["phase"] = 1
                        r_state["cycle"] = 1
                        r_state["0_pct"] = 0
                        r_state["100_pct"] = 0
                else:
                    r_state["phase"] = 0
                data["radar"] = radar_data
                save_data(data)
                st.rerun()
        st.write("---")
