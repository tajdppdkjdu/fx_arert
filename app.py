import streamlit as st
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="FX 自動アラート", layout="wide")
st.title("FX レート＆シグナル アラート 🚀")
st.write("ここで設定した条件を、ロボットが自動で監視します！（最大10個）")

# --- 金庫（Secrets）から鍵を自動で取り出す ---
line_token = st.secrets.get("LINE_TOKEN", "")
line_user_id = st.secrets.get("LINE_USER_ID", "")
jsonbin_id = st.secrets.get("JSONBIN_BIN_ID", "")
jsonbin_key = st.secrets.get("JSONBIN_API_KEY", "")

# --- お助け機能：LINE開通テスト用の送信 ---
def send_test_line(msg):
    if not line_token or not line_user_id:
        return False, "金庫(Secrets)にLINEの鍵が設定されていません。"
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {line_token}"}
    res = requests.post(url, headers=headers, json={"to": line_user_id, "messages": [{"type": "text", "text": msg}]})
    if res.status_code == 200:
        return True, "送信成功"
    else:
        return False, f"エラーが発生しました ({res.status_code})"

st.sidebar.header("🛠️ 連携テスト")
if st.sidebar.button("LINE開通テストを送信 ✉️"):
    success, info = send_test_line("✅ 【テスト通知】FXアラートのLINE連携が正常に完了しています！")
    if success:
        st.sidebar.success("テストLINEを送信しました！スマホをご確認ください。")
    else:
        st.sidebar.error(f"送信失敗: {info}")

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
    st.session_state.alerts_list = load_alerts()

tickers_dict = {
    "USDJPY": "USDJPY=X", "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "EURGBP": "EURGBP=X",
    "AUDJPY": "AUDJPY=X", "CADJPY": "CADJPY=X", "CHFJPY": "CHFJPY=X",
    "GBPAUD": "GBPAUD=X", "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X", "EUR": "EUR=X", "AUD": "AUD=X",
    "GOLD": "GC=F", "SILVER": "SI=F"
}
timeframes = ["5分足", "15分足", "1時間足", "4時間足"]
conditions_list = ["上回る", "下回る", "交差"]

st.write("---")
st.subheader("💱 現在のレートを確認")

check_pair = st.selectbox("確認したい通貨ペアを選択", list(tickers_dict.keys()), key="rate_check_pair")
if st.button("現在のレートを確認 🔍"):
    ticker_symbol = tickers_dict[check_pair]
    st.info(f"{check_pair} の最新データを取得中...")
    try:
        data = yf.download(ticker_symbol, period="1d", interval="15m", progress=False)
        if not data.empty:
            latest_close = float(data.iloc[-1]['Close'].iloc[0]) if isinstance(data.iloc[-1]['Close'], pd.Series) else float(data.iloc[-1]['Close'])
            st.success(f"**{check_pair} の現在価格:** {latest_close:.5f}")
        else:
            st.error("データの取得に失敗しました。時間をおいてお試しください。")
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")

def render_condition_ui(prefix_key):
    alert_type = st.radio("種類", ("① 価格×価格", "② 価格×SMA", "③ SMA×SMA"), key=f"{prefix_key}_type")
    col_a, col_b = st.columns(2)
    settings = {"type": alert_type}
    if alert_type == "① 価格×価格":
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

selected_pair = st.selectbox("通貨ペア", list(tickers_dict.keys()), key="alert_pair")
selected_tf = st.selectbox("時間足", timeframes)

st.write("**【条件 A】**")
cond_a = render_condition_ui("condA")

logic = st.radio("条件の組み合わせ", ["組み合わせない（条件Aのみ）", "AND（条件A かつ 条件B）", "OR（条件A または 条件B）"])
cond_b = None
if logic != "組み合わせない（条件Aのみ）":
    st.write("**【条件 B】**")
    cond_b = render_condition_ui("condB")

# --- 🌟 ここを変更：日付と時間を一緒に設定できるようにしました！ ---
st.write("**【制限の設定】**")
col_limit1, col_limit2 = st.columns(2)
with col_limit1:
    max_alerts = st.number_input("アラートの最大通知回数", min_value=1, value=1)
with col_limit2:
    time_limit_type = st.selectbox("時間制限", ["制限なし", "指定時間まで", "指定時間以降"])

limit_datetime_str = None
if time_limit_type != "制限なし":
    now_jst = datetime.utcnow() + timedelta(hours=9)
    col_date, col_time = st.columns(2)
    with col_date:
        # カレンダーで日付を指定
        limit_date = st.date_input("日付を指定", value=now_jst.date())
    with col_time:
        # 時間を指定
        limit_time = st.time_input("時間を指定", value=datetime.strptime("15:00", "%H:%M").time())
    
    # 日付と時間をくっつけて「2026-03-05 15:00」という文字列にします
    limit_datetime_str = f"{limit_date.strftime('%Y-%m-%d')} {limit_time.strftime('%H:%M')}"

st.info("💡 登録後、1週間（7日間）経過すると自動的にアラートは削除されます。")

if st.button("このアラートを登録してロボットに伝える ➕"):
    if not jsonbin_id or not jsonbin_key:
        st.error("⚠️ StreamlitのSettingsからSecrets（鍵）を設定してください！")
    elif len(st.session_state.alerts_list) >= 10:  
        st.error("登録できるアラートは最大10個までです！")
    else:
        now_jst = (datetime.utcnow() + timedelta(hours=9)).isoformat()
        new_alert = {
            "pair": selected_pair, "tf": selected_tf, 
            "cond_a": cond_a, "logic": logic, "cond_b": cond_b,
            "max_alerts": max_alerts, "trigger_count": 0,          
            "time_limit_type": time_limit_type, "limit_datetime_str": limit_datetime_str, # 変数名を変更
            "created_at": now_jst                                  
        }
        st.session_state.alerts_list.append(new_alert)
        if save_alerts(st.session_state.alerts_list):
            st.success(f"{selected_pair} のアラートを登録しました！ (現在 {len(st.session_state.alerts_list)}/10個)")
        else:
            st.error("データの保存に失敗しました。")

st.write("---")
st.subheader("📋 現在ロボットが監視中のアラート")

if not jsonbin_id:
    st.warning("⚠️ StreamlitのSettingsからSecretsに鍵を設定すると、ここに監視中のアラートが表示されます。")
elif len(st.session_state.alerts_list) == 0:
    st.info("現在登録されているアラートはありません。")
else:
    to_delete = None
    for i, alert in enumerate(st.session_state.alerts_list):
        col_list1, col_list2 = st.columns([4, 1])
        with col_list1:
            # 登録リストに「日付＋時間」の制限情報も表示するようにしました
            limit_disp = ""
            if alert.get('time_limit_type') != "制限なし":
                limit_disp = f" / {alert.get('time_limit_type')}: {alert.get('limit_datetime_str')}"
            
            st.write(f"**{i+1}**: {alert['pair']} ({alert['tf']}) - {alert['logic']} / 通知: {alert.get('trigger_count', 0)}/{alert.get('max_alerts', 1)}回{limit_disp}")
        with col_list2:
            if st.button("削除 🗑️", key=f"del_{i}"):
                to_delete = i
                
    if to_delete is not None:
        deleted_pair = st.session_state.alerts_list[to_delete]['pair']
        st.session_state.alerts_list.pop(to_delete)
        save_alerts(st.session_state.alerts_list)
        st.success(f"アラート {deleted_pair} を削除しました！")
        st.rerun()
