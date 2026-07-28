import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- ページ基本設定 ---
st.set_page_config(page_title="ミスユーズ登録アプリ", layout="centered")
st.title("📋 ミスユーズ登録アプリ")

# --- Google スプレッドシート接続設定 ---
SPREADSHEET_KEY = "1A3_0mGiO1FRz4cVHjpxzd66jFKDcyJ-oUPCH3OtSooE"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_gspread_client():
    # Secrets の [gcp_service_account] から認証情報を取り出し
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # \n 文字列が含まれる場合に備えて自動補正
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client

try:
    gc = get_gspread_client()
    sh = gc.open_by_key(SPREADSHEET_KEY)
    contract_sheet = sh.worksheet("契約データ")
    target_sheet = sh.worksheet("ミスユーズ(神戸)")
except Exception as e:
    st.error(f"スプレッドシートへの接続エラー: {e}")
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
    st.write(" ") # レイアウト調整用スペース
    search_clicked = st.button("🔍 検索", use_container_width=True)

if search_clicked and input_code.strip():
    # 先頭ゼロを除去＆文字列化して整形比較できるようにする
    target_code_clean = input_code.strip().lstrip("0")
    
    with st.spinner("「契約データ」シートを検索中..."):
        all_rows = contract_sheet.get_all_values()
        header = all_rows[0]
        data_rows = all_rows[1:]
        
        # A列(顧客コード)で一致する全行を抽出
        matches = []
        for row in data_rows:
            if len(row) >= 5:
                row_code_clean = str(row[0]).strip().lstrip("0")
                if row_code_clean == target_code_clean:
                    matches.append({
                        "code": row[0].strip(),        # A列: 顧客コード
                        "name": row[1].strip(),        # B列: 顧客名
                        "branch_code": row[2].strip(), # C列: 加盟店コード
                        "branch_name": row[3].strip(), # D列: 加盟店名
                        "product_code": row[4].strip() # E列: 商品記号
                    })
        
        st.session_state.search_results = matches
        st.session_state.searched_code = input_code.strip()

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
        
        # 共通情報の取得（最初の一致行から取得）
        customer_code = results[0]["code"]
        customer_name = results[0]["name"]
        branch_code = results[0]["branch_code"]
        branch_name = results[0]["branch_name"]
        
        # 一致する全ての商品記号リスト（重複排除）
        all_product_codes = sorted(list(set([r["product_code"] for r in results if r["product_code"]])))
        
        # --- 基本情報カード表示 ---
        st.markdown("##### 📌 顧客・加盟店情報")
        col_a, col_b = st.columns(2)
        with col_a:
            st.info(f"**顧客コード**: {customer_code}\n\n**顧客名**: {customer_name}")
        with col_b:
            st.info(f"**加盟店コード**: {branch_code}\n\n**加盟店名**: {branch_name}")

        st.subheader("2. 詳細入力")
        with st.form("data_entry_form"):
            
            # --- 商品記号の複数選択（ボタン式選択） ---
            st.write("**商品記号を選択（複数選択可）**")
            selected_products = st.multiselect(
                "対象の商品記号を選択してください",
                options=all_product_codes,
                default=all_product_codes
            )
            
            # --- 区分（ラジオボタン ＋ その他記述） ---
            st.write("**区分を選択**")
            category_option = st.radio(
                "区分",
                options=["キリコ", "毛髪", "オイル", "その他"],
                horizontal=True
            )
            
            # 「その他」が選ばれた場合のみテキスト入力欄を表示
            other_text = ""
            if category_option == "その他":
                other_text = st.text_input("「その他」の詳細を入力してください")
            
            # 最終的な区分文字列を設定
            final_category = f"その他（{other_text}）" if category_option == "その他" and other_text else category_option
            
            # --- 写真の添付 ---
            st.write("**写真の添付**")
            uploaded_photo = st.file_uploader("写真を添付してください（任意）", type=["jpg", "jpeg", "png"])
            if uploaded_photo is not None:
                st.image(uploaded_photo, caption="添付画像プレビュー", width=200)

            st.write("")
            submit_button = st.form_submit_button("🚀 「ミスユーズ(神戸)」シートに送信・保存", use_container_width=True)

        # --- 送信処理 ---
        if submit_button:
            if not selected_products:
                st.error("商品記号を1つ以上選択してください。")
            else:
                with st.spinner("スプレッドシートへ保存中..."):
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    photo_name = uploaded_photo.name if uploaded_photo else "写真なし"
                    
                    # 選択された商品記号ごとに1行ずつデータを生成
                    new_rows = []
                    for prod in selected_products:
                        row = [
                            timestamp,       # A列: タイムスタンプ
                            customer_code,   # B列: 顧客コード
                            customer_name,   # C列: 顧客名
                            branch_code,     # D列: 加盟店コード
                            branch_name,     # E列: 加盟店名
                            prod,            # F列: 商品記号（1行に1つ）
                            final_category,  # G列: 区分
                            photo_name       # H列: 写真（ファイル名）
                        ]
                        new_rows.append(row)
                    
                    # 「ミスユーズ(神戸)」シートへ末尾一括追加
                    target_sheet.append_rows(new_rows)
                    
                    st.success(f"🎉 正常に保存されました！（計 {len(new_rows)} 行のデータを作成）")
                    st.balloons()
