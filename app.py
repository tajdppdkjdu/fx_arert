import streamlit as st
import requests
from datetime import datetime, timedelta

st.title("FX レート＆シグナル アラート 🚀")
st.write("ここで設定した条件を、ロボットが自動で監視します！（最大10個）")

st.sidebar.header("🔐 連携設定 (LINE & JSONBin)")
line_token = st.sidebar.text_input("LINE トークン", type="password")
line_user_id = st.sidebar.text_input("LINE ユーザーID", type="password")
jsonbin_id = st.sidebar.text_input("JSONBin Bin ID", type="password")
jsonbin_key = st.sidebar.text_input("JSONBin Master Key", type="password")

# --- 共有ポスト（JSONBin）との通信機能 ---
def load_alerts():
    if not jsonbin_id or not jsonbin_key: return []
    url = f"https://api.jsonbin.io/v3/b/{jsonbin_id}"
    res = requests.get(url, headers={"X-Master-Key": jsonbin_key})
    if res.status_code == 200:
        return res.json().get("record", {}).get("alerts", [])
    return []

def save_alerts(alerts):
    url = f"https://api.jsonbin.io/v3/b/{jsonbin_id}"
    headers = {"X-Master-Key": jsonbin_key, "Content-Type": "application/json"}
    res = requests.put(url, headers=headers, json={"alerts": alerts})
    return res.status_code == 200

if 'alerts_list' not in st.session_state:
    st.session_state.alerts_list = []

if st.sidebar.button("データを読み込む 🔄"):
    st.session_state.alerts_list = load_alerts()
    st.sidebar.success("読み込み完了！")

pairs = ["USDJPY", "EURJPY", "GBPJPY", "EURUSD", "GBPUSD", "EURGBP", "AUDJPY", "CADJPY", "CHFJPY", "GBPAUD", "AUDUSD", "USDCAD", "USDCHF", "EUR", "AUD", "GOLD", "SILVER"]
timeframes = ["5分足", "15分足", "1時間足", "4時間足"]
conditions_list = ["上回る", "下回る", "交差"]

def render_condition_ui(prefix_key):
    alert_type = st.radio("種類", ("① 価格×価格", "② 価格×SMA", "③ SMA×SMA"), key=f"{prefix_key}_type")
    col_a, col_b = st.columns(2)
    settings = {"type": alert_type}
    if alert_type == "① 価格×価格":
        # 🌟 ここを変更：小数第5位まで入力できるようにしました！
        with col_a: settings["target_price"] = st.number_input("目標レート", value=150.00000, step=0.0001, format="%.5f", key=f"{prefix_key}_p")
        with col_b: settings["direction"] = st.selectbox("条件", conditions_list, key=f"{prefix_key}_d")
    elif alert_type == "② 価格×SMA":
        with col_a: settings["target_sma"] = st.selectbox("比較するSMA", ["SMA6", "SMA25", "SMA100"], key=f"{prefix_key}_s")
        with col_b: settings["direction"] = st.selectbox("条件", conditions_list, key=f"{prefix_key}_d")
    elif alert_type == "③ SMA×SMA":
        with col_a: settings["sma1"] = st.selectbox("SMA (1つ目)", ["SMA6", "SMA25", "SMA100"], index=0, key=f"{prefix_key}_s1")
        with col_b: settings["sma2"] = st.selectbox("SMA (2つ目)", ["SMA6", "SMA25", "SMA100"], index=1, key=f"{prefix_key}_s2")
        settings["direction"] = st.selectbox("条件", conditions_list, key=f"{prefix_key}_d")
    return settings

st.write("---")
st.subheader("📥 新しいアラートを作成")

selected_pair = st.selectbox("通貨ペア", pairs)
selected_tf = st.selectbox("時間足", timeframes)

st.write("**【条件 A】**")
cond_a = render_condition_ui("condA")

logic = st.radio("条件の組み合わせ", ["組み合わせない（条件Aのみ）", "AND（条件A かつ 条件B）", "OR（条件A または 条件B）"])
cond_b = None
if logic != "組み合わせない（条件Aのみ）":
    st.write("**【条件 B】**")
    cond_b = render_condition_ui("condB")

# --- 制限と期限の設定 ---
st.write("**【制限の設定】**")
col_limit1, col_limit2 = st.columns(2)
with col_limit1:
    max_alerts = st.number_input("アラートの最大通知回数", min_value=1, value=1)
with col_limit2:
    time_limit_type = st.selectbox("時間制限", ["制限なし", "指定時間まで", "指定時間以降"])

limit_time_str = None
if time_limit_type != "制限なし":
    limit_time = st.time_input("時間を指定してください", value=datetime.strptime("15:00", "%H:%M").time())
    limit_time_str = limit_time.strftime("%H:%M")

st.info("💡 登録後、1週間（7日間）経過すると自動的にアラートは削除されます。")

if st.button("このアラートを登録してロボットに伝える ➕"):
    if not jsonbin_id or not jsonbin_key:
        st.error("⚠️ 先にサイドバーにJSONBinの鍵を入力してください！")
    elif len(st.session_state.alerts_list) >= 10:  
        st.error("登録できるアラートは最大10個までです！")
    else:
        now_jst = (datetime.utcnow() + timedelta(hours=9)).isoformat()
        new_alert = {
            "pair": selected_pair, "tf": selected_tf, 
            "cond_a": cond_a, "logic": logic, "cond_b": cond_b,
            "max_alerts": max_alerts, "trigger_count": 0,          
            "time_limit_type": time_limit_type, "limit_time_str": limit_time_str,
            "created_at": now_jst                                  
        }
        st.session_state.alerts_list.append(new_alert)
        if save_alerts(st.session_state.alerts_list):
            st.success(f"{selected_pair} のアラートを登録しました！ (現在 {len(st.session_state.alerts_list)}/10個)")
        else:
            st.error("データの保存に失敗しました。")

st.write("---")
st.subheader("📋 現在ロボットが監視中のアラート")

if len(st.session_state.alerts_list) == 0:
    st.info("現在登録されているアラートはありません。")
else:
    to_delete = None
    for i, alert in enumerate(st.session_state.alerts_list):
        col_list1, col_list2 = st.columns([4, 1])
        with col_list1:
            st.write(f"**{i+1}**: {alert['pair']} ({alert['tf']}) - {alert['logic']} / 通知: {alert.get('trigger_count', 0)}/{alert.get('max_alerts', 1)}回")
        with col_list2:
            if st.button("削除 🗑️", key=f"del_{i}"):
                to_delete = i
                
    if to_delete is not None:
        deleted_pair = st.session_state.alerts_list[to_delete]['pair']
        st.session_state.alerts_list.pop(to_delete)
        save_alerts(st.session_state.alerts_list)
        st.success(f"アラート {deleted_pair} を削除しました！")
        st.rerun()
