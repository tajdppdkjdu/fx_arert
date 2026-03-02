import streamlit as st

# 画面のタイトルを設定します
st.title("FX レート＆シグナル アラート 🚀")

st.write("お好みの条件を選んで、監視をスタートしましょう！")

# 1. 通貨ペアの選択肢を作る
pair = st.selectbox(
    "1. チェックしたい通貨ペアは？", 
    ["USD/JPY (米ドル/円)", "EUR/JPY (ユーロ/円)", "GBP/JPY (ポンド/円)", "GOLD (金)", "SILVER (銀)"]
)

# 2. 時間足の選択肢を作る
timeframe = st.selectbox(
    "2. 時間足は？", 
    ["5分足", "15分足", "1時間足"]
)

# 3. アラート条件の選択肢を作る
condition = st.selectbox(
    "3. どのアラートを受け取りますか？", 
    [
        "価格がSMA25を下回る",
        "価格がSMA25を上回る",
        "SMA6とSMA25のゴールデンクロス",
        "SMA6とSMA25のデッドクロス"
    ]
)

st.write("---")

if st.button("この条件で監視をスタート！"):
    st.success(f"✅ 以下の条件で設定しました！\n\n【{pair}】の【{timeframe}】で「{condition}」をチェックします。")
