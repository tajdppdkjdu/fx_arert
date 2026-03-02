import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- 画面のタイトルと初期設定 ---
st.title("FX レート＆シグナル アラート 🚀")
st.write("複数のアラートを組み合わせて登録しましょう！（最大5個）")

# アラートを保存する「バインダー（リスト）」を準備します
if 'alerts_list' not in st.session_state:
    st.session_state.alerts_list = []

# --- LINE通知用の関数 ---
def send_line_message(token, user_id, message_text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    data = {"to": user_id, "messages": [{"type": "text", "text": message_text}]}
    return requests.post(url, headers=headers, json=data)

st.sidebar.header("🔐 LINE Bot連携設定")
line_token = st.sidebar.text_input("チャネルアクセストークン", type="password")
line_user_id = st.sidebar.text_input("ユーザーID (Uから始まるもの)", type="password")

# --- データ定義 ---
pairs = {
    "USDJPY": "USDJPY=X", "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "EURGBP": "EURGBP=X",
    "AUDJPY": "AUDJPY=X", "CADJPY": "CADJPY=X", "CHFJPY": "CHFJPY=X",
    "GBPAUD": "GBPAUD=X", "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X", "EUR": "EUR=X", "AUD": "AUD=X",
    "GOLD": "GC=F", "SILVER": "SI=F"
}
timeframes = ["5分足", "15分足", "1時間足", "4時間足"]
conditions_list = ["上回る", "下回る", "交差"]

# --- 条件入力画面を作る「お助け機能（関数）」 ---
# 同じ画面を「条件A」と「条件B」で2回使い回すための工夫です
def render_condition_ui(prefix_key):
    alert_type = st.radio(f"アラートの種類", ("① 価格×価格", "② 価格×SMA", "③ SMA×SMA"), key=f"{prefix_key}_type")
    
    col_a, col_b = st.columns(2)
    settings = {"type": alert_type}
    
    if alert_type == "① 価格×価格":
        with col_a: settings["target_price"] = st.number_input("目標レート", value=150.00, step=0.01, key=f"{prefix_key}_p")
        with col_b: settings["direction"] = st.selectbox("条件", conditions_list, key=f"{prefix_key}_d")
    elif alert_type == "② 価格×SMA":
        with col_a: settings["target_sma"] = st.selectbox("比較するSMA", ["SMA6", "SMA25", "SMA100"], key=f"{prefix_key}_s")
        with col_b: settings["direction"] = st.selectbox("条件", conditions_list, key=f"{prefix_key}_d")
    elif alert_type == "③ SMA×SMA":
        col_c, col_d, col_e = st.columns(3)
        with col_c: settings["sma1"] = st.selectbox("SMA (1つ目)", ["SMA6", "SMA25", "SMA100"], index=0, key=f"{prefix_key}_s1")
        with col_d: settings["sma2"] = st.selectbox("SMA (2つ目)", ["SMA6", "SMA25", "SMA100"], index=1, key=f"{prefix_key}_s2")
        with col_e: settings["direction"] = st.selectbox("条件", conditions_list, key=f"{prefix_key}_d")
        if settings["sma1"] == settings["sma2"]: st.warning("⚠️ 同じSMAが選ばれています")
            
    return settings

# --- アラート追加コーナー ---
st.write("---")
st.subheader("📥 新しいアラートを作成")

with st.expander("ここをタップしてアラートを設定する", expanded=True):
    selected_pair = st.selectbox("対象の通貨ペア", list(pairs.keys()))
    selected_tf = st.selectbox("時間足", timeframes)
    
    st.write("**【条件 A】**")
    cond_a = render_condition_ui("condA")
    
    # かつ・または の組み合わせ選択
    logic_operator = st.radio("条件の組み合わせ", ["組み合わせない（条件Aのみ）", "AND（条件A かつ 条件B）", "OR（条件A または 条件B）"])
    
    cond_b = None
    if logic_operator != "組み合わせない（条件Aのみ）":
        st.write("**【条件 B】**")
        cond_b = render_condition_ui("condB")
    
    # 登録ボタン
    if st.button("このアラートをリストに追加する ➕"):
        if len(st.session_state.alerts_list) >= 5:
            st.error("登録できるアラートは最大5個までです！")
        else:
            new_alert = {
                "pair": selected_pair,
                "tf": selected_tf,
                "cond_a": cond_a,
                "logic": logic_operator,
                "cond_b": cond_b
            }
            st.session_state.alerts_list.append(new_alert)
            st.success(f"{selected_pair} のアラートを登録しました！ (現在 {len(st.session_state.alerts_list)}/5個)")

# --- 登録済みアラートの確認と実行コーナー ---
st.write("---")
st.subheader("📋 登録済みのアラート一覧")

if len(st.session_state.alerts_list) == 0:
    st.info("現在登録されているアラートはありません。")
else:
    for i, alert in enumerate(st.session_state.alerts_list):
        st.write(f"**アラート {i+1}**: {alert['pair']} ({alert['tf']}) - 組み合わせ: {alert['logic']}")
    
    if st.button("リストをすべてリセットする 🗑️"):
        st.session_state.alerts_list = []
        st.success("すべてのアラートを削除しました。")

    st.write("---")
    # ここがメインのチェックボタンです
    if st.button("▶️ 登録されたすべてのアラートをチェック！"):
        if not line_token or not line_user_id:
            st.warning("⚠️ サイドバーにLINEのトークンとユーザーIDを入力してください。")
            st.stop()

        # 交差チェック用のお助け機能
        def check_cross(prev1, curr1, prev2, curr2, mode):
            up = (prev1 <= prev2 and curr1 > curr2)
            down = (prev1 >= prev2 and curr1 < curr2)
            if mode == "上回る": return up
            if mode == "下回る": return down
            if mode == "交差": return up or down
            return False

        # 判定用のお助け機能（条件Aや条件Bを計算します）
        def evaluate_condition(cond, curr_p, prev_p, curr_s, prev_s):
            if cond["type"] == "① 価格×価格":
                return check_cross(prev_p, curr_p, cond["target_price"], cond["target_price"], cond["direction"])
            elif cond["type"] == "② 価格×SMA":
                return check_cross(prev_p, curr_p, prev_s[cond["target_sma"]], curr_s[cond["target_sma"]], cond["direction"])
            elif cond["type"] == "③ SMA×SMA":
                return check_cross(prev_s[cond["sma1"]], curr_s[cond["sma1"]], prev_s[cond["sma2"]], curr_s[cond["sma2"]], cond["direction"])
            return False

        # リストの中身を1つずつ順番にチェックします
        for i, alert in enumerate(st.session_state.alerts_list):
            st.write(f"🔍 アラート {i+1} ({alert['pair']}) をチェック中...")
            ticker = pairs[alert['pair']]
            
            # データ取得
            try:
                if alert['tf'] == "4時間足":
                    data = yf.download(ticker, period="60d", interval="1h", progress=False)
                    data = data.resample('4h').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
                else:
                    tf_map = {"5分足": "5m", "15分足": "15m", "1時間足": "1h"}
                    data = yf.download(ticker, period="60d", interval=tf_map[alert['tf']], progress=False)

                if data.empty:
                    st.error("データ取得失敗")
                    continue

                data['SMA6'] = data['Close'].rolling(window=6).mean()
                data['SMA25'] = data['Close'].rolling(window=25).mean()
                data['SMA100'] = data['Close'].rolling(window=100).mean()

                latest, previous = data.iloc[-1], data.iloc[-2]
                def gv(r, c): return float(r[c].iloc[0]) if isinstance(r[c], pd.Series) else float(r[c])
                
                cp, pp = gv(latest, 'Close'), gv(previous, 'Close')
                cs = {"SMA6": gv(latest, 'SMA6'), "SMA25": gv(latest, 'SMA25'), "SMA100": gv(latest, 'SMA100')}
                ps = {"SMA6": gv(previous, 'SMA6'), "SMA25": gv(previous, 'SMA25'), "SMA100": gv(previous, 'SMA100')}

                # 条件Aの判定
                result_a = evaluate_condition(alert['cond_a'], cp, pp, cs, ps)
                
                # 最終的な判定（AND / OR の計算）
                final_result = result_a
                if alert['logic'] == "AND（条件A かつ 条件B）":
                    result_b = evaluate_condition(alert['cond_b'], cp, pp, cs, ps)
                    final_result = result_a and result_b  # 両方TrueならTrue
                elif alert['logic'] == "OR（条件A または 条件B）":
                    result_b = evaluate_condition(alert['cond_b'], cp, pp, cs, ps)
                    final_result = result_a or result_b   # どちらかがTrueならTrue

                if final_result:
                    msg = f"🚨【アラート {i+1} 発動】\n{alert['pair']} ({alert['tf']})\n現在価格: {cp:.3f}\n条件を満たしました！"
                    send_line_message(line_token, line_user_id, msg)
                    st.error(f"🚨 アラート {i+1}: 条件達成！LINEに通知しました。")
                else:
                    st.success(f"✅ アラート {i+1}: 条件は満たしていません。")

            except Exception as e:
                st.error(f"アラート {i+1} でエラー: {e}")
