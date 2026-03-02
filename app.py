import streamlit as st
import yfinance as yf
import pandas as pd

# 画面のタイトル
st.title("FX レート＆シグナル アラート 🚀")
st.write("設定したいアラートの条件を組み立ててください。")

# --- 選択肢のデータ準備 ---

# (1) 通貨ペアの選択肢（17種類）
pairs = {
 "USDJPY=X",
"EURJPY=X",
"GBPJPY=X",
 "EURUSD=X",
"GBPUSD=X",
 "EURGBP=X",
"AUDJPY=X",
 "CADJPY=X",
 "CHFJPY=X",
"GBPAUD=X",
 "AUDUSD=X",
"USDCAD=X",
"USDCHF=X",
"EUR=X",
"AUD=X",
"GC=F",
 "SI=F"
}

# (2) 時間足の選択肢（4種類）
timeframes = ["5分足", "15分足", "1時間足", "4時間足"]

# --- 画面のレイアウト作成 ---
st.subheader("条件の設定")

# アラートのパターンを選択させます
alert_type = st.radio(
    "アラートの種類を選択してください",
    ("① 価格 × 価格アラート", "② 価格 × 条件アラート", "③ 条件 × 条件アラート")
)

st.write("---")
st.write(f"**【 {alert_type} の設定】**")

# 横並びのレイアウト（列）を作って、(1)と(2)を配置します
col1, col2 = st.columns(2)
with col1:
    selected_pair = st.selectbox("(1) 通貨ペア", list(pairs.keys()))
with col2:
    selected_tf = st.selectbox("(2) 時間足", timeframes)

# 選ばれたアラート種類に応じて、(3)と(4)の表示を切り替えます
if alert_type == "① 価格 × 価格アラート":
    col3, col4 = st.columns(2)
    with col3:
        # レートを自分で入力する枠を作ります
        target_price = st.number_input("(3) 目標レートを入力", value=150.000, step=0.01)
    with col4:
        direction = st.selectbox("(4) アラート条件", ["上回った", "下回った"])

elif alert_type == "② 価格 × 条件アラート":
    col3, col4 = st.columns(2)
    with col3:
        target_sma = st.selectbox("(3') 比較するSMA", ["SMA6", "SMA25", "SMA100"])
    with col4:
        direction = st.selectbox("(4) アラート条件", ["上回った", "下回った"])

elif alert_type == "③ 条件 × 条件アラート":
    col3, col4, col5 = st.columns(3)
    with col3:
        sma1 = st.selectbox("(3') SMA (1つ目)", ["SMA6", "SMA25", "SMA100"], index=0)
    with col4:
        # index=1 で初期値をSMA25にズラしています
        sma2 = st.selectbox("(3\") SMA (2つ目)", ["SMA6", "SMA25", "SMA100"], index=1)
    with col5:
        direction = st.selectbox("(4) アラート条件", ["上回った", "下回った"])
    
    # もし同じSMAが選ばれたら、エラーメッセージを出します
    if sma1 == sma2:
        st.error("⚠️ (3')と(3\")が同じSMAです。別の組み合わせを選択してください。")

st.write("---")

# --- 裏側のデータ取得・計算処理 ---

# (3')と(3")が同じ場合は、ボタンを押せないようにする設定です
is_invalid = (alert_type == "③ 条件 × 条件アラート" and sma1 == sma2)

if st.button("この条件で現在の状況をチェック！", disabled=is_invalid):
    ticker = pairs[selected_pair]
    st.info(f"データ取得中: {selected_pair} / {selected_tf}...")
    
    try:
        # yfinanceの仕様上、4時間足は直接取得できないため、1時間足から変換します
        if selected_tf == "4時間足":
            # SMA100（100本分）を計算するために、たっぷり60日分の1時間足を取得します
            data = yf.download(ticker, period="60d", interval="1h", progress=False)
            if not data.empty:
                # 1時間足を4時間足に束ねる（リサンプル）魔法のコードです
                data = data.resample('4h').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
        else:
            tf_map = {"5分足": "5m", "15分足": "15m", "1時間足": "1h"}
            interval = tf_map[selected_tf]
            # SMA100を計算するために60日分のデータを取得します
            data = yf.download(ticker, period="60d", interval=interval, progress=False)

        if data.empty:
            st.error("データの取得に失敗しました。時間をおいて再度お試しください。")
        else:
            # 3種類のSMAを計算
            data['SMA6'] = data['Close'].rolling(window=6).mean()
            data['SMA25'] = data['Close'].rolling(window=25).mean()
            data['SMA100'] = data['Close'].rolling(window=100).mean()

            # 最新のデータ（現在）と、1つ前のデータ（前回）を取得
            latest = data.iloc[-1]
            previous = data.iloc[-2]

            # データを扱いやすい数値に変換するお助け機能（関数）
            def get_val(row, column):
                val = row[column]
                return float(val.iloc[0]) if isinstance(val, pd.Series) else float(val)

            curr_price = get_val(latest, 'Close')
            prev_price = get_val(previous, 'Close')
            
            curr_sma = {"SMA6": get_val(latest, 'SMA6'), "SMA25": get_val(latest, 'SMA25'), "SMA100": get_val(latest, 'SMA100')}
            prev_sma = {"SMA6": get_val(previous, 'SMA6'), "SMA25": get_val(previous, 'SMA25'), "SMA100": get_val(previous, 'SMA100')}

            # 画面に現在の数値をカッコよく表示します（metricという機能を使います）
            st.write("### 現在のデータ")
            colA, colB, colC, colD = st.columns(4)
            colA.metric("現在の価格", f"{curr_price:.3f}")
            colB.metric("SMA6", f"{curr_sma['SMA6']:.3f}")
            colC.metric("SMA25", f"{curr_sma['SMA25']:.3f}")
            colD.metric("SMA100", f"{curr_sma['SMA100']:.3f}")

            # ここから判定ロジック
            is_alert = False

            if alert_type == "① 価格 × 価格アラート":
                if direction == "上回った":
                    # 前回は目標以下で、今回は目標より大きい場合
                    if prev_price <= target_price and curr_price > target_price:
                        is_alert = True
                else: # 下回った
                    if prev_price >= target_price and curr_price < target_price:
                        is_alert = True

            elif alert_type == "② 価格 × 条件アラート":
                c_sma = curr_sma[target_sma]
                p_sma = prev_sma[target_sma]
                if direction == "上回った":
                    if prev_price <= p_sma and curr_price > c_sma:
                        is_alert = True
                else: # 下回った
                    if prev_price >= p_sma and curr_price < c_sma:
                        is_alert = True

            elif alert_type == "③ 条件 × 条件アラート":
                c_sma1, c_sma2 = curr_sma[sma1], curr_sma[sma2]
                p_sma1, p_sma2 = prev_sma[sma1], prev_sma[sma2]
                if direction == "上回った":
                    if p_sma1 <= p_sma2 and c_sma1 > c_sma2:
                        is_alert = True
                else: # 下回った
                    if p_sma1 >= p_sma2 and c_sma1 < c_sma2:
                        is_alert = True

            # 判定結果を表示
            st.write("### 判定結果")
            if is_alert:
                st.error(f"🚨【アラート発動】設定した条件を満たしました！")
            else:
                st.success("✅ 現在、設定したアラート条件は満たしていません。")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
