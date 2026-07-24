import streamlit as st
import requests
from google import genai
from PIL import Image
import json
import datetime

# ページ設定
st.set_page_config(page_title="伝票読み取りアプリ", page_icon="🧾", layout="centered")

st.title("🧾 伝票読み取り＆自動保存")
st.caption("伝票を撮影するとAIが内容を自動抽出して保存します。")

# 設定情報の読み込み（Streamlit Cloud の Secrets から取得）
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
GAS_URL = st.secrets.get("GAS_URL", "")

if "ocr_result" not in st.session_state:
    st.session_state.ocr_result = {}

# 1. スマホカメラ撮影 / ファイル選択
st.markdown("### 1. 伝票の撮影・アップロード")
tab1, tab2 = st.tabs(["📷 スマホで撮影", "📁 画像を選択"])

image_input = None
with tab1:
    camera_photo = st.camera_input("伝票を撮影してください")
    if camera_photo:
        image_input = camera_photo

with tab2:
    uploaded_file = st.file_uploader("画像を選択", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image_input = uploaded_file

# 画像読み取り処理
if image_input:
    image = Image.open(image_input)
    st.image(image, caption="撮影した画像", use_container_width=True)

    if st.button("🔍 AIで伝票を自動読み取り", type="primary", use_container_width=True):
        if not GEMINI_API_KEY:
            st.error("Gemini API Key が設定されていません。Streamlit Cloudの Secrets を確認してください。")
        else:
            with st.spinner("AIが伝票を解析中..."):
                try:
                    # クライアント初期化
                    client = genai.Client(api_key=GEMINI_API_KEY)

                    prompt = """
                    この伝票・領収書の画像から以下の項目を読み取り、JSONフォーマットのみで返してください。
                    キー名は以下に統一してください:
                    - customer_name: お客様名・宛名
                    - branch_name: 加盟店名・店舗名
                    - amount: 金額（数値のみ）
                    - date: 日付（YYYY-MM-DD形式。不明なら空欄）
                    - phone: 電話番号
                    - address: 住所
                    - content: 品名・作業詳細
                    
                    読み取れない項目は空文字 "" にしてください。JSON以外の解説文は出力しないでください。
                    """

                    # 無料枠の制限を回避するため gemini-2.0-flash-lite を指定
                    response = client.models.generate_content(
                        model='gemini-2.0-flash-lite',
                        contents=[image, prompt]
                    )

                    raw_text = response.text.strip()
                    if "```" in raw_text:
                        raw_text = raw_text.split("```")[1]
                        if raw_text.startswith("json"):
                            raw_text = raw_text[4:]
                    
                    parsed_data = json.loads(raw_text.strip())
                    st.session_state.ocr_result = parsed_data
                    st.success("✨ 読み取り完了！下のフォームを確認してください。")

                except Exception as e:
                    st.error(f"読み取りエラー: {e}")

st.markdown("---")

# 2. データの確認・手修正フォーム
st.markdown("### 2. 内容確認・送信")
ocr = st.session_state.ocr_result

with st.form(key="receipt_form"):
    parsed_date_str = ocr.get("date", "")
    default_date = datetime.date.today()
    if parsed_date_str:
        try:
            default_date = datetime.datetime.strptime(parsed_date_str, "%Y-%m-%d").date()
        except:
            pass

    report_date = st.date_input("日付", value=default_date)
    customer_name = st.text_input("お客様名", value=ocr.get("customer_name", ""))
    branch_name = st.text_input("加盟店名/店舗名", value=ocr.get("branch_name", ""))
    amount = st.text_input("金額", value=str(ocr.get("amount", "")))
    phone = st.text_input("電話番号", value=ocr.get("phone", ""))
    address = st.text_input("住所", value=ocr.get("address", ""))
    content = st.text_area("詳細内容", value=ocr.get("content", ""))

    submit_btn = st.form_submit_button("💾 スプレッドシートに保存", type="primary", use_container_width=True)

# 3. GASへ送信
if submit_btn:
    if not GAS_URL:
        st.error("GAS WebApp URL が設定されていません。Streamlit Cloudの Secrets を確認してください。")
    elif not customer_name:
        st.warning("お客様名を入力してください。")
    else:
        with st.spinner("スプレッドシートへ保存中..."):
            payload = {
                "card_type": "伝票読取",
                "report_date": str(report_date),
                "customer_name": customer_name,
                "branch_name": branch_name,
                "amount": amount,
                "phone": phone,
                "address": address,
                "content": content
            }
            try:
                res = requests.post(GAS_URL, json=payload, timeout=15)
                st.success("🎉 スプレッドシートに正常保存されました！")
            except Exception as e:
                st.error(f"送信エラー: {e}")
