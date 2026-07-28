import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import io

# --- ページ基本設定 ---
st.set_page_config(page_title="ミスユーズ登録アプリ", layout="centered")
st.title("📋 ミスユーズ登録アプリ")

# --- Google 設定 ---
SPREADSHEET_KEY = "1A3_0mGiO1FRz4cVHjpxzd66jFKDcyJ-oUPCH3OtSooE"

# 共有いただいたGoogleドライブのフォルダID
DRIVE_FOLDER_ID = "1eg4vR-8v0qNpWKjEYvQ-2IDMK9O52DhU" 

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_gcp_services():
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    if "private_key" in creds_dict:
        pk = str(creds_dict["private_key"])
        pk = pk.replace("\\n", "\n")
        if "-----BEGIN PRIVATE KEY-----" in pk and "\n" not in pk:
            pk = pk.replace("-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n")
            pk = pk.replace("-----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----")
        creds_dict["private_key"] = pk

    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    
    gc = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    
    return gc, drive_service

def upload_photo_to_drive(drive_service, uploaded_file, folder_id):
    """指定のGoogleドライブフォルダに画像を保存し、スプレッドシート用直リンクURLを返す"""
    file_metadata = {
        'name': f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}",
        'parents': [folder_id]
    }
    
    media = MediaIoBaseUpload(
        io.BytesIO(uploaded_file.getvalue()),
        mimetype=uploaded_file.type,
        resumable=True
    )
    
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    file_id = file.get('id')
    
    # スプレッドシートの =IMAGE 関数で表示できるようにリンク閲覧権限を付与
    drive_service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    # 画像の直リンクURLを返却
    direct_url = f"https://drive.google.com/uc?export=view&id={file_id}"
    return direct_url

try:
    gc, drive_service = get_gcp_services()
    sh = gc.open_by_key(SPREADSHEET_KEY)
    contract_sheet = sh.worksheet("契約データ")
    target_sheet = sh.worksheet("ミスユーズ(神戸)")
except Exception as e:
    st.error(f"接続エラー: {e}")
    st.stop()

# --- session_state (状態保持) の初期化 ---
if "search_results" not in st.session_state:
    st.session_state.search_results = None
if "searched_code" not in st.session_state:
    st.session_state.searched_code = ""

# ==========================================
# STEP 1: 顧客コード検索
# ==========================================
st.subheader("1. 顧客コード検索")
col_input, col_btn = st.columns([3, 1])

with col_input:
    input_code = st.text_input(
        "顧客コードを入力してください", 
        value=st.session_state.searched_code, 
        placeholder="例: 0115923 または 115923"
    )

with col_btn:
    st.write(" ")
    search_clicked = st.button("🔍 検索", use_container_width=True)

if search_clicked and input_code.strip():
    raw_input = input_code.strip()
    target_code_clean = raw_input.lstrip("0") if raw_input.lstrip("0") else "0"
    
    with st.spinner("「契約データ」シートを検索中..."):
        all_rows = contract_sheet.get_all_values()
        
        if len(all_rows) > 1:
            header = all_rows[0]
            data_rows = all_rows[1:]
            
            matches = []
            for row in data_rows:
                if len(row) >= 5:
                    row_code = str(row[0]).strip()
                    row_code_clean = row_code.lstrip("0") if row_code.lstrip("0") else "0"
                    
                    if row_code_clean == target_code_clean:
                        matches.append({
                            "code": row[0].strip(),
                            "name": row[1].strip(),
                            "branch_code": row[2].strip(),
                            "branch_name": row[3].strip(),
                            "product_code": row[4].strip()
                        })
            
            st.session_state.search_results = matches
            st.session_state.searched_code = raw_input

st.divider()

# ==========================================
# STEP 2: 検索結果表示 ＆ データ入力フォーム
# ==========================================
if st.session_state.search_results is not None:
    results = st.session_state.search_results
    
    if not results:
        st.warning(f"顧客コード「{st.session_state.searched_code}」に一致する契約データが見つかりませんでした。")
    else:
        st.success(f"✅ {len(results)} 件の契約データが見つかりました！")
        
        customer_code = results[0]["code"]
        customer_name = results[0]["name"]
        branch_code = results[0]["branch_code"]
        branch_name = results[0]["branch_name"]
        
        all_product_codes = sorted(list(set([r["product_code"] for r in results if r["product_code"]])))
        
        st.markdown("##### 📌 顧客・加盟店情報")
        col_a, col_b = st.columns(2)
        with col_a:
            st.info(f"**顧客コード**: {customer_code}\n\n**顧客名**: {customer_name}")
        with col_b:
            st.info(f"**加盟店コード**: {branch_code}\n\n**加盟店名**: {branch_name}")

        st.subheader("2. 詳細入力")
        with st.form("data_entry_form", clear_on_submit=False):
            
            selected_products = st.multiselect(
                "対象の商品記号を選択してください",
                options=all_product_codes,
                default=all_product_codes
            )
            
            category_option = st.radio(
                "区分",
                options=["キリコ", "毛髪", "オイル", "その他"],
                horizontal=True
            )
            
            other_text = st.text_input("「その他」を選択した場合の詳細")
            
            uploaded_photo = st.file_uploader("写真を添付してください（任意）", type=["jpg", "jpeg", "png"])
            if uploaded_photo is not None:
                st.image(uploaded_photo, caption="添付画像プレビュー", width=200)

            st.write("")
            submit_button = st.form_submit_button("🚀 「ミスユーズ(神戸)」シートに送信・保存", use_container_width=True)

        if submit_button:
            if not selected_products:
                st.error("商品記号を1つ以上選択してください。")
            else:
                final_category = f"その他（{other_text}）" if category_option == "その他" and other_text else category_option
                
                with st.spinner("写真のアップロードとスプレッドシートへの保存処理中..."):
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 画像アップロード処理
                    photo_val = "写真なし"
                    if uploaded_photo is not None:
                        try:
                            # Googleドライブのフォルダへ保存してURL取得
                            photo_url = upload_photo_to_drive(drive_service, uploaded_photo, DRIVE_FOLDER_ID)
                            # スプレッドシート内で画像表示させる数式
                            photo_val = f'=IMAGE("{photo_url}")'
                        except Exception as upload_err:
                            st.error(f"写真のアップロードに失敗しました。フォルダの共有設定を確認してください: {upload_err}")
                            photo_val = "アップロード失敗"
                    
                    new_rows = []
                    for prod in selected_products:
                        row = [
                            timestamp,       # A列: タイムスタンプ
                            customer_code,   # B列: 顧客コード
                            customer_name,   # C列: 顧客名
                            branch_code,     # D列: 加盟店コード
                            branch_name,     # E列: 加盟店名
                            prod,            # F列: 商品記号
                            final_category,  # G列: 区分
                            photo_val        # H列: 写真（セル内に画像が表示されます）
                        ]
                        new_rows.append(row)
                    
                    # 数式（=IMAGE）をそのまま評価させるオプションを指定
                    target_sheet.append_rows(new_rows, value_input_option="USER_ENTERED")
                    
                    st.success(f"🎉 正常に保存されました！（指定ドライブに保存＆スプレッドシートに反映完了）")
                    st.balloons()
