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
        if highs.iloc[i] == w_high.max(): alt_ext.append({'idx': i, 'val': float(highs.iloc[i]), 'type': 'peak', 'conf': fut==6, 'time': times[i]})
        if lows.iloc[i] == w_low.min(): alt_ext.append({'idx': i, 'val': float(lows.iloc[i]), 'type': 'trough', 'conf': fut==6, 'time': times[i]})
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
        if state in ["上昇トレンド", "仮上昇トレンド"] and baseline and cp < baseline: state, baseline = "レンジ", None
        elif state in ["下降トレンド", "仮下降トレンド"] and baseline and cp > baseline: state, baseline = "レンジ", None
    state_map = {"上昇トレンド": 1, "仮上昇トレンド": 2, "下降トレンド": 3, "仮下降トレンド": 4, "レンジ": 5}
    return {"code": state_map[state], "name": state, "last": last_trend, "h1": r_h1, "h2": r_h2, "l1": r_l1, "l2": r_l2, "t_h1": t_h1, "t_h2": t_h2, "t_l1": t_l1, "t_l2": t_l2}

def calc_radar_indicators(df):
    df['SMA100'] = df['Close'].rolling(window=100).mean()
    high26 = df['High'].rolling(window=26).max()
    low26 = df['Low'].rolling(window=26).min()
    df['Kijun'] = (high26 + low26) / 2
    return df

def fmt_dt_str(t):
    if not t: return None
    return t.isoformat() if hasattr(t, 'isoformat') else str(t)

def fmt_t(t_str):
    if not t_str: return ""
    try:
        dt = pd.to_datetime(t_str)
        if dt.tzinfo is not None: dt = dt.tz_convert('Asia/Tokyo')
        else: dt = dt.tz_localize('UTC').tz_convert('Asia/Tokyo')
        return dt.strftime('%m/%d %H:%M')
    except: return ""

@st.cache_data(ttl=300, show_spinner=False)
def get_env_status(ticker):
    status = {"dir": "エラー", "dir_1h": "-", "dir_4h": "-", "dir_d": "-", "sim_phase": 1, "sim_cycle": 1, "sim_0_pct": 0, "sim_100_pct": 0, "time_0": None, "time_100": None}
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
        pct_0, pct_100, current_lowest = 0.0, 0.0, 0.0
        time_0, time_100, current_lowest_time = None, None, None
        timer, last_mode, cross_time = 0, None, None

        df_sim = df_1h_30d.dropna(subset=['SMA100', 'Kijun']).tail(336)
        for i in range(len(df_sim)):
            c, h, l = float(df_sim['Close'].iloc[i]), float(df_sim['High'].iloc[i]), float(df_sim['Low'].iloc[i])
            k, sma = float(df_sim['Kijun'].iloc[i]), float(df_sim['SMA100'].iloc[i])
            t = df_sim.index[i]
            is_buy_mode = (k > sma)
            if last_mode is not None and is_buy_mode != last_mode:
                cross_time = t
                phase, cycle, pct_0, pct_100, time_0, time_100 = 1, 1, 0.0, 0.0, None, None
            last_mode = is_buy_mode

            if phase == 4:
                if is_buy_mode and c > k: phase, cycle, pct_0, time_0 = 1, 1, h, t
                elif not is_buy_mode and c < k: phase, cycle, pct_0, time_0 = 1, 1, l, t
            elif phase == 1:
                if is_buy_mode:
                    if pct_0 == 0 or h > pct_0: pct_0, time_0 = h, t
                    if c < k:
                        if pct_100 == 0: pct_100, time_100 = sma, t
                        phase, current_lowest, current_lowest_time, timer = 2, l, t, 0
                else:
                    if pct_0 == 0 or l < pct_0: pct_0, time_0 = l, t
                    if c > k:
                        if pct_100 == 0: pct_100, time_100 = sma, t
                        phase, current_lowest, current_lowest_time, timer = 2, h, t, 0
            elif phase in [2, 3]:
                timer += 1
                if (timer >= 72) or (is_buy_mode and c < pct_100) or (not is_buy_mode and c > pct_100):
                    phase = 4
                    continue
                if is_buy_mode:
                    if l < current_lowest: current_lowest, current_lowest_time = l, t
                    if h > pct_0:
                        pct_100, time_100, pct_0, time_0, phase, cycle = current_lowest, current_lowest_time, h, t, 1, cycle + 1
                else:
                    if h > current_lowest: current_lowest, current_lowest_time = h, t
                    if l < pct_0:
                        pct_100, time_100, pct_0, time_0, phase, cycle = current_lowest, current_lowest_time, l, t, 1, cycle + 1

        k1, sma1 = df_1h_30d['Kijun'].iloc[-1], df_1h_30d['SMA100'].iloc[-1]
        c1 = df_1h_30d['Close'].iloc[-1]
        c4, k4 = df_4h['Close'].iloc[-1], df_4h['Kijun'].iloc[-1]
        cd, kd = df_d['Close'].iloc[-1], df_d['Kijun'].iloc[-1]

        main_dir = "買い目線" if k1 > sma1 else "売り目線"
        if phase == 4: main_dir = "方向感無し"
        
        status.update({
            "dir": main_dir,
            "dir_1h": "買" if c1 > k1 else "売", "dir_4h": "買" if c4 > k4 else "売", "dir_d": "買" if cd > kd else "売",
            "sim_phase": phase, "sim_cycle": cycle, "sim_0_pct": pct_0, "sim_100_pct": pct_100,
            "sim_cur_low": current_lowest, "sim_cur_low_t": fmt_dt_str(current_lowest_time),
            "time_0": fmt_dt_str(time_0), "time_100": fmt_dt_str(time_100), "cross_time": fmt_dt_str(cross_time)
        })
    except Exception as e: pass
    return status

st.title("FX 自動アラートシステム")
data = load_data()
alerts = data.get("alerts", [])

st.subheader("🔍 現在のレート確認")
c1, c2 = st.columns([3, 1])
with c1: check_pair = st.selectbox("通貨ペア", list(pairs.keys()), key="check")
with c2: 
    st.write("")
    if st.button("取得"):
        rate = get_current_rate(pairs[check_pair])
        if rate: st.success(f"{check_pair} : {rate:.5f}")
        else: st.error("取得失敗")

st.divider()

if len(alerts) >= MAX_ALERTS_LIMIT:
    st.warning(f"登録上限（{MAX_ALERTS_LIMIT}個）です。")
else:
    with st.expander("🔔 通常アラート（価格・SMA）を設定する"):
        pair = st.selectbox("通貨ペア", list(pairs.keys()), key="na_pair")
        tf = st.selectbox("時間足", ["5分足", "15分足", "1時間足", "4時間足"], key="na_tf")
        def cond_ui(label):
            st.write(f"**{label}**")
            ctype = st.selectbox("種類", ["① 価格×価格", "② 価格×SMA", "③ SMA×SMA"], key=f"ctype_{label}")
            if ctype == "① 価格×価格":
                price = st.number_input("目標価格", value=0.00000, format="%.5f", key=f"price_{label}")
                dir_ = st.selectbox("条件", ["上回る", "下回る", "交差"], key=f"dir_{label}")
                return {"type": ctype, "target_price": price, "direction": dir_}
            elif ctype == "② 価格×SMA":
                sma = st.selectbox("SMA", ["SMA6", "SMA25", "SMA100"], key=f"sma_{label}")
                dir_ = st.selectbox("条件", ["上回る", "下回る", "交差"], key=f"dir2_{label}")
                return {"type": ctype, "target_sma": sma, "direction": dir_}
            else:
                s1 = st.selectbox("SMA(主)", ["SMA6", "SMA25", "SMA100"], key=f"s1_{label}")
                s2 = st.selectbox("SMA(副)", ["SMA6", "SMA25", "SMA100"], index=1, key=f"s2_{label}")
                dir_ = st.selectbox("条件", ["上回る", "下回る", "交差"], key=f"dir3_{label}")
                return {"type": ctype, "sma1": s1, "sma2": s2, "direction": dir_}
        cond_a = cond_ui("条件A")
        logic = st.selectbox("条件Bの追加", ["条件Aのみ", "AND（条件A かつ 条件B）", "OR（条件A または 条件B）"])
        cond_b = cond_ui("条件B") if logic != "条件Aのみ" else None
        st.write("---")
        st.write("**⏱️ 制限設定（通常アラート）**")
        col_c, col_t = st.columns(2)
        with col_c: max_count = st.number_input("通知の最大回数 (1〜5回)", min_value=1, max_value=5, value=1)
        with col_t: time_limit_mode = st.selectbox("時間制限", ["なし（1週間で自動無効）", "指定日時まで有効", "指定日時以降に有効"])
        limit_dt = None
        if time_limit_mode != "なし（1週間で自動無効）":
            col_d, col_tm = st.columns(2)
            with col_d: limit_date = st.date_input("日付 (JST)")
            with col_tm: limit_time = st.time_input("時間 (JST)", value=(datetime.now() + timedelta(hours=1)).time())
            limit_dt = datetime.combine(limit_date, limit_time).isoformat()
        if st.button("通常アラートを登録"):
            now_jst = datetime.utcnow() + timedelta(hours=9)
            new_alert = {"type": "normal", "pair": pair, "tf": tf, "logic": logic, "cond_a": cond_a, "cond_b": cond_b, "created_at": now_jst.isoformat(), "max_count": max_count, "current_count": 0, "time_mode": time_limit_mode, "limit_dt": limit_dt}
            alerts.append(new_alert)
            data["alerts"] = alerts
            save_data(data)
            st.success("登録しました！")
            st.rerun()

    st.write("---")
    st.write("📈 **トレンドアラートを設定する**")
    t_toggle = st.radio("", ["× (設定しない)", "〇 (設定する)"], horizontal=True, label_visibility="collapsed")
    if t_toggle == "〇 (設定する)":
        alert_t_pair = st.selectbox("通貨ペア (トレンド監視用)", list(pairs.keys()), key="at_pair")
        alert_t_tf = st.selectbox("時間足 (トレンド監視用)", ["5分足", "15分足", "1時間足", "4時間足"], key="at_tf")
        alert_t_curr = st.selectbox("現在のトレンド（手動選択）", ["1. 上昇トレンド", "2. 仮上昇トレンド", "3. 下降トレンド", "4. 仮下降トレンド", "5. レンジ"])
        if alert_t_curr.startswith("1") or alert_t_curr.startswith("2"): sit_opts = ["上昇トレンドが終了したら", "下降トレンドが始まったら"]
        elif alert_t_curr.startswith("3") or alert_t_curr.startswith("4"): sit_opts = ["下降トレンドが終了したら", "上昇トレンドが始まったら"]
        else: sit_opts = ["上昇トレンドが始まったら", "下降トレンドが始まったら", "トレンドが始まったら"]
        alert_sit = st.selectbox("シチュエーション選択", sit_opts)
        base_rate = None
        if "終了したら" in alert_sit:
            st.info("💡 終了判定の基準となるレートを入力してください。")
            base_rate = st.number_input("基準レート", value=0.00000, format="%.5f", key="base_rate")
        st.write("---")
        st.write("**⏱️ 制限設定（トレンドアラート）**")
        t_time_limit_mode = st.selectbox("時間制限", ["なし（1週間で自動無効）", "指定日時まで有効", "指定日時以降に有効"], key="t_time_mode")
        t_limit_dt = None
        if t_time_limit_mode != "なし（1週間で自動無効）":
            t_col_d, t_col_tm = st.columns(2)
            with t_col_d: t_limit_date = st.date_input("日付 (JST)", key="t_date")
            with t_col_tm: t_limit_time = st.time_input("時間 (JST)", value=(datetime.now() + timedelta(hours=1)).time(), key="t_time")
            t_limit_dt = datetime.combine(t_limit_date, t_limit_time).isoformat()
        if st.button("トレンドアラートを登録"):
            now_jst = datetime.utcnow() + timedelta(hours=9)
            new_alert = {"type": "trend", "pair": alert_t_pair, "tf": alert_t_tf, "current_trend": alert_t_curr, "situation": alert_sit, "baseline_rate": base_rate, "created_at": now_jst.isoformat(), "time_mode": t_time_limit_mode, "limit_dt": t_limit_dt}
            alerts.append(new_alert)
            data["alerts"] = alerts
            save_data(data)
            st.success("登録しました！")
            st.rerun()

st.divider()
with st.expander("⚠️ データが壊れて画面が動かない場合の緊急リセット"):
    if st.button("🗑️ アラートデータを全消去する"):
        data["alerts"] = []
        save_data(data)
        st.success("初期化完了！画面をリロードしてください。")
        st.rerun()

st.subheader("📋 登録済みアラート")
if not alerts: st.write("登録されていません。")
def fmt_limit(a):
    tm = a.get('time_mode', 'なし（1週間で自動無効）')
    if tm == 'なし（1週間で自動無効）': return "1週間で無効"
    dt_str = datetime.fromisoformat(a['limit_dt']).strftime('%m/%d %H:%M')
    return f"{dt_str} まで有効" if tm == "指定日時まで有効" else f"{dt_str} 以降有効"
for i, a in enumerate(alerts):
    try:
        if a.get("type") == "trend":
            st.markdown(f"**[{i+1}] 📈 トレンドアラート | {a.get('pair', '不明')} ({a.get('tf', '不明')})**")
            st.write(f"状況設定: {a.get('situation', '不明')}")
            if a.get('baseline_rate'): st.write(f"基準レート: {a['baseline_rate']:.3f} 割れ")
            st.caption(f"⏱️ 期限: {fmt_limit(a)}")
        else:
            st.markdown(f"**[{i+1}] 🔔 通常アラート | {a.get('pair', '不明')} ({a.get('tf', '不明')})**")
            def fmt_cond(c):
                if not c: return "不明"
                t, d = c.get('type', '不明'), c.get('direction', '不明')
                if t == "① 価格×価格": return f"{t} : {c.get('target_price')} を {d}"
                if t == "② 価格×SMA": return f"{t} : {c.get('target_sma')} を {d}"
                if t == "③ SMA×SMA": return f"{t} : {c.get('sma1')} が {c.get('sma2')} を {d}"
                return f"{t} ({d})"
            st.write(f"A: {fmt_cond(a.get('cond_a'))}")
            logic = a.get('logic', '条件Aのみ')
            cond_b = a.get('cond_b')
            if logic != "条件Aのみ" and cond_b is not None: st.write(f"{logic} \nB: {fmt_cond(cond_b)}")
            remain = a.get('max_count', 1) - a.get('current_count', 0)
            st.caption(f"⏱️ 期限: {fmt_limit(a)} ｜ 残り回数: {remain} / {a.get('max_count', 1)} 回")
    except Exception:
        st.warning(f"**[{i+1}] ⚠️ 読み込みエラー**")
    if st.button("削除", key=f"del_{i}"):
        alerts.pop(i)
        data["alerts"] = alerts
        save_data(data)
        st.rerun()

st.divider()
st.subheader("🌍 環境認識＆手法レーダー (別枠監視)")

radar_data = data.get("radar", {})

with st.expander("レーダーを展開する", expanded=False):
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 全通貨を一括取得する"):
            with st.spinner("全通貨のデータを取得中..."):
                for pair_key, ticker in pairs.items():
                    st.session_state[f"env_cache_{pair_key}"] = get_env_status(ticker)
    with col_btn2:
        if st.button("🛑 全ての監視を一括停止する"):
            for pk in radar_data: radar_data[pk]["active"] = False
            data["radar"] = radar_data
            save_data(data)
            st.success("全て停止しました")
            st.rerun()

    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([2, 1.5, 2.5, 3.0, 1.0])
    with col_h1: st.caption("通貨ペア")
    with col_h2: st.caption("個別取得")
    with col_h3: st.caption("目線 (環境認識)")
    with col_h4: st.caption("フェーズ / 基準レート(時間)")
    with col_h5: st.caption("監視")
    st.write("---")

    for pair_key, ticker in pairs.items():
        if pair_key not in radar_data:
            radar_data[pair_key] = {"active": False, "phase": 0, "cycle": 1, "0_pct": 0, "100_pct": 0}
        r_state = radar_data[pair_key]
        col1, col2, col3, col4, col5 = st.columns([2, 1.5, 2.5, 3.0, 1.0])
        with col1: st.write(f"**{pair_key}**")
        with col2:
            if st.button("🔄", key=f"get_{pair_key}"):
                with st.spinner(""): st.session_state[f"env_cache_{pair_key}"] = get_env_status(ticker)
        with col3:
            env_data = st.session_state.get(f"env_cache_{pair_key}")
            if env_data:
                if env_data['dir'] == "エラー": st.write("⚠️ 取得失敗")
                else:
                    mark = "🔴" if env_data['dir'] == "買い目線" else "🔵" if env_data['dir'] == "売り目線" else "⚪️"
                    cross_t = fmt_t(env_data.get('cross_time'))
                    cross_str = f" ({cross_t}〜)" if cross_t else ""
                    st.write(f"{mark} {env_data['dir']}{cross_str}")
                    st.caption(f"1H:{env_data.get('dir_1h')} / 4H:{env_data.get('dir_4h')} / 日:{env_data.get('dir_d')}")
            else: st.write("⚪️ 未取得")
        with col4:
            if r_state["active"]:
                p = r_state.get('phase', 0)
                phase_map = {0: "待機中", 1: "①開始待ち", 2: "②準備待ち", 3: "③ｴﾝﾄﾘｰ待ち", 4: "⚪️方向感無し"}
                st.write(f"**{phase_map.get(p, '待機中')}** (第{r_state.get('cycle', 1)}ｻｲｸﾙ)")
                
                p0, p100, tgt = r_state.get('0_pct', 0), r_state.get('100_pct', 0), r_state.get('target_15m', 0)
                t0, t100, ttgt = r_state.get('time_0'), r_state.get('time_100'), r_state.get('time_tgt')
                cl = r_state.get('current_lowest', 0)
                cl_t = r_state.get('current_lowest_time')
                
                cl_str = f"\n押し/戻り: {cl:.5f} ({fmt_t(cl_t)})" if cl != 0 else ""
                tgt_str = f"\nﾌﾞﾚｲｸ: {tgt:.5f} ({fmt_t(ttgt)})" if tgt else "\nﾌﾞﾚｲｸ: 探索中..."
                
                if p == 1 and p100 != 0: 
                    st.code(f"100%: {p100:.5f} ({fmt_t(t100)})")
                elif p in [2, 3]: 
                    st.code(f"0%: {p0:.5f} ({fmt_t(t0)}){cl_str}\n100%: {p100:.5f} ({fmt_t(t100)}){tgt_str}")
            else:
                if env_data and env_data['dir'] != "エラー":
                    sim_p, sim_c = env_data.get('sim_phase', 1), env_data.get('sim_cycle', 1)
                    sim_0, sim_100 = env_data.get('sim_0_pct', 0), env_data.get('sim_100_pct', 0)
                    t0, t100 = env_data.get('time_0'), env_data.get('time_100')
                    s_cl = env_data.get('sim_cur_low', 0)
                    s_cl_t = env_data.get('sim_cur_low_t')
                    
                    p_str = "①開始待ち" if sim_p == 1 else "②準備/ｴﾝﾄﾘｰ" if sim_p in [2,3] else "⚪️方向感無し"
                    st.write(f"_{p_str}_ (第{sim_c}ｻｲｸﾙ)")
                    
                    s_cl_str = f"\n押し/戻り: {s_cl:.5f} ({fmt_t(s_cl_t)})" if s_cl != 0 else ""
                    
                    if sim_p == 1 and sim_100 != 0: 
                        st.code(f"100%: {sim_100:.5f} ({fmt_t(t100)})")
                    elif sim_p in [2,3] and sim_0 != 0: 
                        st.code(f"0%: {sim_0:.5f} ({fmt_t(t0)}){s_cl_str}\n100%: {sim_100:.5f} ({fmt_t(t100)})")
                else: st.write("待機(停止中)")
        with col5:
            btn_label = "🛑" if r_state["active"] else "👀"
            if st.button(btn_label, key=f"btn_r_{pair_key}"):
                r_state["active"] = not r_state["active"]
                if r_state["active"]:
                    env_data = st.session_state.get(f"env_cache_{pair_key}")
                    if env_data and env_data['dir'] != "エラー":
                        r_state["phase"], r_state["cycle"] = env_data.get("sim_phase", 1), env_data.get("sim_cycle", 1)
                        r_state["0_pct"], r_state["100_pct"] = env_data.get("sim_0_pct", 0), env_data.get("sim_100_pct", 0)
                        r_state["time_0"], r_state["time_100"] = env_data.get("time_0"), env_data.get("time_100")
                        # 🌟 ここが抜けていました！押し安値の引き継ぎを追加！
                        r_state["current_lowest"] = env_data.get("sim_cur_low", 0)
                        r_state["current_lowest_time"] = env_data.get("sim_cur_low_t", "")
                    else:
                        r_state["phase"], r_state["cycle"], r_state["0_pct"], r_state["100_pct"] = 1, 1, 0, 0
                        r_state["current_lowest"], r_state["current_lowest_time"] = 0, ""
                else: r_state["phase"] = 0
                data["radar"] = radar_data
                save_data(data)
                st.rerun()
        st.write("---")
