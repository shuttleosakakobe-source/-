import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import requests
from datetime import datetime

# --- ページ基本設定 ---
st.set_page_config(page_title="ミスユーズ登録アプリ", layout="centered")
st.title("📋 ミスユーズ登録アプリ")

# --- 設定値の読み込み ---
SPREADSHEET_KEY = st.secrets.get("SPREADSHEET_KEY", "1A3_0mGiO1FRz4cVHjpxzd66jFKDcyJ-oUPCH3OtSooE")
FREEIMAGE_API_KEY = st.secrets.get("FREEIMAGE_API_KEY", "6d207e02198a847aa98d0a2a901485a5")

# ご提示いただいた正しい URL (gid) のマッピング
BRANCH_CONFIG = {
    "神戸中央店": {"gid": 0},
    "京都中央店": {"gid": 574516095},
    "大阪北店":   {"gid": 980545892},
    "大阪中央店": {"gid": 2139697515}
}

# 保存先シート名
TARGET_SHEET_NAME = "ミスユーズ顧客"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_credentials():
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict:
        pk = str(creds_dict["private_key"])
        pk = pk.replace("\\n", "\n")
        if "-----BEGIN PRIVATE KEY-----" in pk and "\n" not in pk:
            pk = pk.replace("-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n")
            pk = pk.replace("-----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----\n")
        creds_dict["private_key"] = pk

    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return creds

def upload_photo_external(uploaded_file):
    """外部フリーストレージ(freeimage.host API)へ画像を保存して直リンクURLを取得"""
    url = "https://freeimage.host/api/1/upload"
    params = {
        "key": FREEIMAGE_API_KEY,
        "action": "upload",
        "format": "json"
    }
    files = {
        "source": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)
    }
    
    response = requests.post(url, data=params, files=files, timeout=15)
    if response.status_code == 200:
        res_data = response.json()
        if res_data.get("status_code") == 200:
            image_info = res_data.get("image", {})
            direct_url = image_info.get("file", {}).get("url") or image_info.get("display_url") or image_info.get("url")
            return direct_url
        else:
            raise Exception(f"アップロード応答エラー: {res_data}")
    else:
        raise Exception(f"HTTPエラー: {response.status_code} - {response.text}")

# スプレッドシート初期接続
try:
    creds = get_credentials()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_KEY)
    
    # 保存先シートの存在確認・取得
    try:
        target_sheet = sh.worksheet(TARGET_SHEET_NAME)
    except Exception:
        # 見つからない場合は新規作成
        target_sheet = sh.add_worksheet(title=TARGET_SHEET_NAME, rows="1000", cols="10")
        target_sheet.append_row(["日時", "拠点", "顧客コード", "顧客名", "加盟店コード", "担当者加盟店名", "商品記号", "区分", "写真"])
except Exception as e:
    st.error(f"スプレッドシート接続エラー: {e}")
    st.stop()

# --- session_state の初期化 ---
if "search_results" not in st.session_state:
    st.session_state.search_results = None
if "searched_code" not in st.session_state:
    st.session_state.searched_code = ""

# ==========================================
# STEP 1: 拠点選択 ＆ 顧客コード検索
# ==========================================
st.subheader("1. 拠点選択 ＆ 顧客コード検索")

selected_branch = st.radio(
    "拠点を選択してください",
    options=["神戸中央店", "京都中央店", "大阪北店", "大阪中央店"],
    horizontal=True
)

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
    # 先頭のゼロを除去して文字列・数値の表記揺れを補正
    target_code_clean = raw_input.lstrip("0") if raw_input.lstrip("0") else "0"
    
    config = BRANCH_CONFIG.get(selected_branch)
    target_gid = config["gid"]
    
    contract_sheet = None
    
    # gid を使用して直接正確なワークシートを取得
    try:
        contract_sheet = sh.get_worksheet_by_id(target_gid)
    except Exception as err:
        st.error(f"「{selected_branch}」(gid: {target_gid}) のシートを開くことができませんでした: {err}")
        contract_sheet = None

    if contract_sheet is not None:
        with st.spinner(f"「{selected_branch}」のシート（{contract_sheet.title}）を読み込み中..."):
            try:
                all_rows = contract_sheet.get_all_values()
                
                if len(all_rows) > 1:
                    header = [str(cell).strip() for cell in all_rows[0]]
                    data_rows = all_rows[1:]
                    
                    # 各店舗のヘッダーの位置を自動検索（標準の位置をデフォルトに設定）
                    idx_code = 0
                    idx_name = 1 if len(header) > 1 else 0
                    idx_bcode = 2 if len(header) > 2 else 0
                    idx_bname = 3 if len(header) > 3 else 0
                    idx_pcode = 4 if len(header) > 4 else 0
                    
                    # 列名が含まれているか判定してインデックスを自動調整
                    for i, col in enumerate(header):
                        if "顧客コード" in col or ("コード" in col and i < 2):
                            idx_code = i
                        elif "顧客名" in col or "氏名" in col or "名" in col:
                            idx_name = i
                        elif "加盟店コード" in col:
                            idx_bcode = i
                        elif "加盟店名" in col:
                            idx_bname = i
                        elif "商品" in col or "記号" in col:
                            idx_pcode = i

                    matches = []
                    for row in data_rows:
                        if len(row) > idx_code:
                            row_code = str(row[idx_code]).strip()
                            row_code_clean = row_code.lstrip("0") if row_code.lstrip("0") else "0"
                            
                            if row_code_clean == target_code_clean:
                                matches.append({
                                    "code": row_code,
                                    "name": str(row[idx_name]).strip() if len(row) > idx_name else "",
                                    "branch_code": str(row[idx_bcode]).strip() if len(row) > idx_bcode else "",
                                    "branch_name": str(row[idx_bname]).strip() if len(row) > idx_bname else "",
                                    "product_code": str(row[idx_pcode]).strip() if len(row) > idx_pcode else ""
                                })
                    
                    st.session_state.search_results = matches
                    st.session_state.searched_code = raw_input
                else:
                    st.warning("シートにデータ行が存在しません。")
            except Exception as search_err:
                st.error(f"データの検索中にエラーが発生しました: {search_err}")

st.divider()

# ==========================================
# STEP 2: 検索結果表示 ＆ データ入力フォーム
# ==========================================
if st.session_state.search_results is not None:
    results = st.session_state.search_results
    
    if not results:
        st.warning(f"拠点「{selected_branch}」から顧客コード「{st.session_state.searched_code}」に一致するデータが見つかりませんでした。")
    else:
        st.success(f"✅ {len(results)} 件の契約データが見つかりました！（検索対象: {selected_branch}）")
        
        customer_code = results[0]["code"]
        customer_name = results[0]["name"]
        branch_code = results[0]["branch_code"]
        branch_name = results[0]["branch_name"]
        
        all_product_codes = sorted(list(set([r["product_code"] for r in results if r["product_code"]])))
        
        st.markdown("##### 📌 顧客・加盟店情報")
        col_a, col_b = st.columns(2)
        with col_a:
            st.info(f"**拠点**: {selected_branch}\n\n**顧客コード**: {customer_code}\n\n**顧客名**: {customer_name}")
        with col_b:
            st.info(f"**加盟店コード**: {branch_code}\n\n**担当者加盟店名**: {branch_name}")

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
            submit_button = st.form_submit_button(f"🚀 「{TARGET_SHEET_NAME}」シートに送信・保存", use_container_width=True)

        if submit_button:
            if not selected_products:
                st.error("商品記号を1つ以上選択してください。")
            else:
                final_category = f"その他（{other_text}）" if category_option == "その他" and other_text else category_option
                
                with st.spinner("写真のアップロードと保存処理中..."):
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    photo_val = "写真なし"
                    if uploaded_photo is not None:
                        try:
                            photo_url = upload_photo_external(uploaded_photo)
                            photo_val = f'=IMAGE("{photo_url}")'
                        except Exception as upload_err:
                            st.error(f"写真の保存に失敗しました: {upload_err}")
                            photo_val = "アップロード失敗"
                    
                    new_rows = []
                    for prod in selected_products:
                        row = [
                            timestamp,       # A列: 日時
                            selected_branch, # B列: 拠点
                            customer_code,   # C列: 顧客コード
                            customer_name,   # D列: 顧客名
                            branch_code,     # E列: 加盟店コード
                            branch_name,     # F列: 担当者加盟店名
                            prod,            # G列: 商品記号
                            final_category,  # H列: 区分
                            photo_val        # I列: 写真
                        ]
                        new_rows.append(row)
                    
                    try:
                        target_sheet.append_rows(new_rows, value_input_option="USER_ENTERED")
                        st.success(f"🎉 正常に保存されました！（「{TARGET_SHEET_NAME}」シートに追記完了）")
                        st.balloons()
                    except Exception as append_err:
                        st.error(f"スプレッドシートへの追記に失敗しました: {append_err}")
