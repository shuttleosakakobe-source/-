import streamlit as st
import requests
from PIL import Image
import io
import base64
import datetime

# ページ設定
st.set_page_config(page_title="伝票読み取り＆保存アプリ", page_icon="🧾", layout="centered")

st.title("🧾 伝票読み取り＆自動保存（無料版）")
st.caption("Google Driveの無料OCR機能を使って伝票を読み取り、スプレッドシートに保存します。")

# 設定情報の読み込み（Streamlit Cloud の Secrets から取得）
GAS_URL = st.secrets.get("GAS_URL", "")

if "ocr_text" not in st.session_state:
    st.session_state.ocr_text = ""

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

image_base64 = None
mime_type = "image/jpeg"

if image_input:
    image = Image.open(image_input)
    st.image(image, caption="撮影した画像", use_container_width=True)

    # 画像をBase64形式に変換
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

st.markdown("---")

# 2. 内容入力・送信フォーム
st.markdown("### 2. 内容確認・送信")

with st.form(key="receipt_form"):
    report_date = st.date_input("日付", value=datetime.date.today())
    customer_name = st.text_input("お客様名")
    branch_name = st.text_input("加盟店名/店舗名")
    amount = st.text_input("金額（数字のみ）")
    phone = st.text_input("電話番号")
    address = st.text_input("住所")
    content = st.text_area("詳細・メモ", value=st.session_state.ocr_text)

    submit_btn = st.form_submit_button("🚀 画像を解析してスプレッドシートに保存", type="primary", use_container_width=True)

# 3. GASへ送信処理
if submit_btn:
    if not GAS_URL:
        st.error("GAS WebApp URL が設定されていません。Streamlit Secretsを確認してください。")
    elif not image_base64 and not customer_name:
        st.warning("画像を選択するか、お客様名を入力してください。")
    else:
        with st.spinner("Google Driveの無料OCRで解析＆スプレッドシートへ保存中..."):
            payload = {
                "report_date": str(report_date),
                "customer_name": customer_name,
                "branch_name": branch_name,
                "amount": amount,
                "phone": phone,
                "address": address,
                "content": content,
                "image_base64": image_base64,
                "mime_type": mime_type
            }
            try:
                res = requests.post(GAS_URL, json=payload, timeout=30)
                res_data = res.json()
                
                if res_data.get("status") == "success":
                    st.success("🎉 スプレッドシートに正常保存されました！")
                    if res_data.get("extracted_text"):
                        st.info("📄 **読み取られたテキスト:**\n\n" + res_data.get("extracted_text"))
                else:
                    st.error(f"保存失敗: {res_data.get('message')}")
            except Exception as e:
                st.error(f"送信エラー: {e}")
