import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, time

# 画面のタイトル
st.title("FX レート＆シグナル アラート 🚀")
st.write("設定したいアラートの条件を組み立ててください。")

# --- 一時メモ機能（セッション・ステート）の準備 ---
# ここでアラートの回数や、開始した日時を一時的に記憶します
if 'alert_count' not in st.session_state:
    st.session_state.alert_count = 0
if 'start_time' not in st.session_state:
    st.session_state.start_time = None

# --- 選択肢のデータ準備 ---
pairs = {
    "USDJPY": "USDJPY=X", "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "EURGBP": "EURGBP=X",
    "AUDJPY": "AUDJPY=X", "CADJPY": "CADJPY=X", "CHFJPY": "CHFJPY=X",
    "GBPAUD": "GBPAUD=X", "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X", "EUR": "EUR=X", "AUD": "AUD=X",
    "GOLD": "GC=F", "SILVER": "SI=F"
}
timeframes = ["5分足", "15分足", "1時間足", "4時間足"]

# --- 画面のレイアウト作成 ---
st.subheader("条件の設定")

alert_type = st.radio(
    "アラートの種類を選択してください",
    ("① 価格 × 価格アラート", "② 価格 × 条件アラート", "③ 条件 × 条件アラート")
)

st.write("---")
col1, col2 = st.columns(2)
with col1:
    selected_pair = st.selectbox("(1) 通貨ペア", list(pairs.keys()))
with col2:
    selected_tf = st.selectbox("(2) 時間足", timeframes)

# (4) の選択肢を「交差」を追加した3択に変更
conditions_list = ["上回る", "下回る", "交差"]

if alert_type == "① 価格 × 価格アラート":
    col3, col4 = st.columns(2)
    with col3:
        target_price = st.number_input("(3) 目標レートを入力", value=150.000, step=0.01)
    with col4:
        direction = st.selectbox("(4) アラート条件", conditions_list)

elif alert_type == "② 価格 × 条件アラート":
    col3, col4 = st.columns(2)
    with col3:
        target_sma = st.selectbox("(3') 比較するSMA", ["SMA6", "SMA25", "SMA100"])
    with col4:
        direction = st.selectbox("(4) アラート条件", conditions_list)

elif alert_type == "③ 条件 × 条件アラート":
    col3, col4, col5 = st.columns(3)
    with col3:
        sma1 = st.selectbox("(3') SMA (1つ目)", ["SMA6", "SMA25", "SMA100"], index=0)
    with col4:
        sma2 = st.selectbox("(3\") SMA (2つ目)", ["SMA6", "SMA25", "SMA100"], index=1)
    with col5:
        direction = st.selectbox("(4) アラート条件", conditions_list)
    if sma1 == sma2:
        st.error("⚠️ (3')と(3\")が同じSMAです。別の組み合わせを選択してください。")

st.write("---")
st.subheader("制限の設定")

# アラートの回数と時間制限の設定画面
col6, col7 = st.columns(2)
with col6:
    max_alerts = st.number_input("アラートの最大通知回数", min_value=1, value=1)
with col7:
    time_limit_type = st.selectbox("時間制限", ["制限なし", "指定時間まで", "指定時間以降"])

# 時間制限が選ばれた場合のみ、時間を入力する枠を出します
limit_time = None
if time_limit_type != "制限なし":
    limit_time = st.time_input("時間を指定してください", value=time(15, 0)) # 初期値は15:00

# 1週間で無効になることの案内
st.info("💡 設定後、1週間（7日間）経過すると自動的にアラートは無効になります。")

st.write("---")

# リセットボタン（テスト用に記憶をゼロに戻すボタン）
if st.button("記憶をリセットして新しく設定する"):
    st.session_state.alert_count = 0
    st.session_state.start_time = None
    st.success("設定と記憶をリセットしました！")

# --- 裏側のデータ取得・計算処理 ---
is_invalid = (alert_type == "③ 条件 × 条件アラート" and sma1 == sma2)

if st.button("この条件で現在の状況をチェック！", disabled=is_invalid):
    # --- 制限のチェック ---
    # サーバーの時間は世界標準時(UTC)なので、9時間足して日本時間(JST)にします
    now_jst = datetime.utcnow() + timedelta(hours=9)
    
    # 1. 1週間期限のチェック
    if st.session_state.start_time is None:
        st.session_state.start_time = now_jst # 初めて押した時に時間を記録
    
    time_elapsed = now_jst - st.session_state.start_time
    if time_elapsed > timedelta(days=7):
        st.error("期限切れ：設定から1週間が経過したため、アラートは無効になりました。リセットしてください。")
        st.stop() # ここでプログラムを止めます

    # 2. 回数制限のチェック
    if st.session_state.alert_count >= max_alerts:
        st.error(f"回数制限：すでに上限（{max_alerts}回）までアラートを通知しました。")
        st.stop()

    # 3. 時間制限のチェック
    current_time_only = now_jst.time()
    if time_limit_type == "指定時間まで":
        if current_time_only > limit_time:
            st.warning(f"時間外：現在は指定時間（{limit_time}）を過ぎているため監視をお休みしています。")
            st.stop()
    elif time_limit_type == "指定時間以降":
        if current_time_only < limit_time:
            st.warning(f"時間外：指定時間（{limit_time}）になるまで監視をお休みしています。")
            st.stop()

    # --- これ以降は前回のデータ取得・判定処理と同じです ---
    ticker = pairs[selected_pair]
    st.info(f"データ取得中: {selected_pair} / {selected_tf}...")
    
    try:
        if selected_tf == "4時間足":
            data = yf.download(ticker, period="60d", interval="1h", progress=False)
            if not data.empty:
                data = data.resample('4h').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
        else:
            tf_map = {"5分足": "5m", "15分足": "15m", "1時間足": "1h"}
            data = yf.download(ticker, period="60d", interval=tf_map[selected_tf], progress=False)

        if data.empty:
            st.error("データの取得に失敗しました。時間をおいて再度お試しください。")
        else:
            data['SMA6'] = data['Close'].rolling(window=6).mean()
            data['SMA25'] = data['Close'].rolling(window=25).mean()
            data['SMA100'] = data['Close'].rolling(window=100).mean()

            latest = data.iloc[-1]
            previous = data.iloc[-2]

            def get_val(row, column):
                val = row[column]
                return float(val.iloc[0]) if isinstance(val, pd.Series) else float(val)

            curr_price = get_val(latest, 'Close')
            prev_price = get_val(previous, 'Close')
            curr_sma = {"SMA6": get_val(latest, 'SMA6'), "SMA25": get_val(latest, 'SMA25'), "SMA100": get_val(latest, 'SMA100')}
            prev_sma = {"SMA6": get_val(previous, 'SMA6'), "SMA25": get_val(previous, 'SMA25'), "SMA100": get_val(previous, 'SMA100')}

            st.write("### 現在のデータ")
            colA, colB, colC, colD = st.columns(4)
            colA.metric("現在の価格", f"{curr_price:.3f}")
            colB.metric("SMA6", f"{curr_sma['SMA6']:.3f}")
            colC.metric("SMA25", f"{curr_sma['SMA25']:.3f}")
            colD.metric("SMA100", f"{curr_sma['SMA100']:.3f}")

            is_alert = False

            # 「交差」の判定（上抜け、または下抜けのどちらかであればTrue）
            def check_cross(prev_val1, curr_val1, prev_val2, curr_val2, mode):
                cross_up = (prev_val1 <= prev_val2 and curr_val1 > curr_val2)
                cross_down = (prev_val1 >= prev_val2 and curr_val1 < curr_val2)
                
                if mode == "上回る": return cross_up
                elif mode == "下回る": return cross_down
                elif mode == "交差": return cross_up or cross_down
                return False

            if alert_type == "① 価格 × 価格アラート":
                is_alert = check_cross(prev_price, curr_price, target_price, target_price, direction)
            elif alert_type == "② 価格 × 条件アラート":
                is_alert = check_cross(prev_price, curr_price, prev_sma[target_sma], curr_sma[target_sma], direction)
            elif alert_type == "③ 条件 × 条件アラート":
                is_alert = check_cross(prev_sma[sma1], curr_sma[sma1], prev_sma[sma2], curr_sma[sma2], direction)

            if is_alert:
                st.session_state.alert_count += 1 # アラート回数を1増やす
                st.error(f"🚨【アラート発動】設定した条件を満たしました！ (現在の通知回数: {st.session_state.alert_count}/{max_alerts})")
            else:
                st.success(f"✅ 現在、設定したアラート条件は満たしていません。(現在の通知回数: {st.session_state.alert_count}/{max_alerts})")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
