import streamlit as st
import pandas as pd
from datetime import date, datetime
import numpy as np
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# Google Sheets 連線設定
# ==========================================
# 設定權限範圍
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = 'secrets.json' # 確保呢個檔案喺同一個資料夾
SHEET_NAME = 'HealthApp_Database' # 👈 如果你頭先 Google Sheet 唔係叫呢個名，請改返啱！

# 建立連線 (終極防撞版：自動判斷係本機定雲端)
@st.cache_resource
def init_connection():
    try:
        # 1. 先嘗試讀取本機嘅 secrets.json 檔案 (你依家本機測試會成功行呢段)
        credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    except FileNotFoundError:
        # 2. 如果發生 FileNotFoundError 搵唔到檔案 (即係放上雲端後)，先至去讀取 Streamlit Secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    
    client = gspread.authorize(credentials)
    return client

# 讀取 Google Sheets 數據
def load_data():
    client = init_connection()
    sheet = client.open(SHEET_NAME).sheet1
    data = sheet.get_all_records()
    
    if data:
        df = pd.DataFrame(data)
        # 將 Google Sheet 讀返嚟嘅空字串轉為 NaN，確保圖表畫得啱
        df.replace("", np.nan, inplace=True)
        return df
    else:
        return pd.DataFrame(columns=['日期', '時間', '使用者', '血糖', '尿酸', '體重', '備註'])



# 儲存數據去 Google Sheets
def save_data(df_to_save):
    client = init_connection()
    sheet = client.open(SHEET_NAME).sheet1
    sheet.clear() # 先清空舊表
    # 將 NaN 轉回空字串，Google Sheet 先食得落
    df_clean = df_to_save.fillna("")
    # 寫入成個 DataFrame
    sheet.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())

# ==========================================
# 讀寫用戶密碼專用函數
# ==========================================
def load_users():
    client = init_connection()
    sheet = client.open(SHEET_NAME).worksheet('UserAccounts') # 讀取新分頁
    data = sheet.get_all_records()
    if data:
        # 將數據全部轉做字串，避免密碼「1234」變成數字格式出 bug
        return pd.DataFrame(data).astype(str)
    else:
        return pd.DataFrame(columns=['使用者', '密碼'])

def save_users_df(users_df_to_save):
    client = init_connection()
    sheet = client.open(SHEET_NAME).worksheet('UserAccounts')
    sheet.clear()
    sheet.update([users_df_to_save.columns.values.tolist()] + users_df_to_save.values.tolist())

df = load_data()
users_df = load_users() # <--- 新增呢行，一開 App 就讀取用戶名冊

st.title('🏠 家庭健康紀錄 App')

# ==========================================
# 第一部分：輸入區 (Input Form)
# ==========================================
st.header('📝 新增紀錄')

# 從密碼名冊度讀取現有使用者名單
existing_users = users_df['使用者'].tolist() if not users_df.empty else []

with st.form("input_form", clear_on_submit=True):
    options = ['-- 新增使用者 --'] + existing_users
    selected_user = st.selectbox('選擇使用者', options)
    
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        new_user = st.text_input('新使用者名字 (舊用戶請留空)')
    with col_u2:
        # 🔑 升級：將密碼欄位改為所有人必須填寫
        input_password = st.text_input('密碼 (新用戶設定密碼 / 舊用戶輸入密碼確認)', type='password')
    
    col1, col2 = st.columns(2)
    with col1:
        record_date = st.date_input('日期', date.today())
    with col2:
        record_time = st.time_input('時間', datetime.now().replace(second=0, microsecond=0).time())
        
    blood_sugar = st.number_input('血糖 (mmol/L)', min_value=0.0, value=None, format="%.1f")
    uric_acid = st.number_input('尿酸 (μmol/L)', min_value=0.0, value=None, format="%.1f")
    weight = st.number_input('體重 (kg)', min_value=0.0, value=None, format="%.1f")
    notes = st.selectbox('備註', ['飯前', '飯後'])
    
    submit_button = st.form_submit_button(label='💾 儲存紀錄')
    
    if submit_button:
        is_new = (selected_user == '-- 新增使用者 --')
        final_user = new_user.strip() if is_new else selected_user
        
        # 1. 基本錯誤檢查
        if final_user == "" or final_user == '-- 新增使用者 --':
            st.error("⚠️ 請選擇或輸入使用者名稱！")
        elif input_password == "":
            st.error("⚠️ 必須輸入密碼！(新用戶請設定密碼，舊用戶請輸入專屬密碼以確認身份)")
        else:
            # 2. 密碼驗證邏輯
            password_is_correct = False
            
            if is_new:
                # 如果係新用戶，儲存佢個名同密碼入 UserAccounts
                new_user_data = pd.DataFrame([{'使用者': final_user, '密碼': input_password}])
                users_df = pd.concat([users_df, new_user_data], ignore_index=True)
                save_users_df(users_df)
                st.info(f"🔑 成功為 {final_user} 建立帳戶及設定密碼！")
                password_is_correct = True # 新用戶設定完即代表驗證通過
            else:
                # 如果係舊用戶，程式會去 Google Sheets 對答案
                correct_password = str(users_df.loc[users_df['使用者'] == final_user, '密碼'].values[0])
                if input_password == correct_password:
                    password_is_correct = True
                else:
                    st.error(f"❌ 密碼錯誤！無法為 {final_user} 新增紀錄，請確認身份再試。")
            
            # 3. 只有「密碼正確」或者「成功建立新用戶」，先至准儲存健康數據
            if password_is_correct:
                new_data = pd.DataFrame([{
                    '日期': str(record_date),
                    '時間': str(record_time.strftime("%H:%M")),
                    '使用者': final_user,
                    '血糖': blood_sugar,
                    '尿酸': uric_acid,
                    '體重': weight,
                    '備註': notes
                }])
                df = pd.concat([df, new_data], ignore_index=True)
                save_data(df)
                
                st.success(f'✅ 身份確認！成功儲存 {final_user} 的健康紀錄！')
                st.rerun()
            
# ==========================================
# 第二部分：展示區 (Dashboard) - 數據獨立的核心！
# ==========================================
st.header('📊 查看數據')

# 1. 改為從 users_df (用戶名冊) 讀取名單
existing_users = users_df['使用者'].tolist() if not users_df.empty else []

if existing_users:
    view_user = st.selectbox('你想查看誰的數據？', existing_users)
    
    # 2. 從 users_df 搵返呢個 user 嘅正確密碼出嚟
    correct_password = str(users_df.loc[users_df['使用者'] == view_user, '密碼'].values[0])
    
    # 3. 顯示密碼輸入框
    input_password = st.text_input(f'🔒 請輸入 {view_user} 的專屬密碼解鎖：', type='password')
    
    # 4. 驗證密碼
    if input_password == correct_password:
        st.success('🔓 解鎖成功！')
        
        # --- 👇 新增：更改密碼功能 👇 ---
        with st.expander("⚙️ 更改帳戶密碼"):
            new_pass = st.text_input("請輸入新密碼", type="password", key=f"new_pass_{view_user}")
            if st.button("💾 確認更改密碼"):
                if new_pass.strip() != "":
                    # 更新 DataFrame 入面嘅密碼
                    users_df.loc[users_df['使用者'] == view_user, '密碼'] = new_pass
                    # 寫入 Google Sheets
                    save_users_df(users_df)
                    st.success("✅ 密碼更改成功！下次請使用新密碼解鎖。")
                else:
                    st.error("⚠️ 密碼不能為空！")
        # --- 👆 更改密碼功能完畢 👆 ---

        # ==========================================
        # 以下係你原本嘅畫圖同表格代碼 (全部縮排咗放入嚟呢個 if 入面)
        # ==========================================
        filtered_df = df[df['使用者'] == view_user]
        
        if not filtered_df.empty:
            # 加入 horizontal=True 令啲掣橫向排列，慳位啲又靚啲
            meal_filter = st.radio('🔍 篩選圖表顯示時段：', ['全部', '飯前', '飯後'], horizontal=True)
            
            # 複製一份數據用嚟處理圖表，避免影響下方嘅 st.data_editor 歷史表格
            chart_df = filtered_df.copy()
            
            # 根據用家選擇，過濾數據
            if meal_filter != '全部':
                chart_df = chart_df[chart_df['備註'] == meal_filter]
            
            # 檢查篩選之後仲有冇數據
            if not chart_df.empty:
                chart_df['日期時間'] = pd.to_datetime(chart_df['日期'] + ' ' + chart_df['時間'])
                chart_df = chart_df.sort_values('日期時間')
                chart_df['日期時間'] = chart_df['日期時間'].dt.strftime('%Y-%m-%d %H:%M')
                chart_df = chart_df.set_index('日期時間')
                
                st.subheader(f'📈 {view_user} 的血糖趨勢 ({meal_filter})')
                st.line_chart(chart_df['血糖'].dropna())
                
                st.subheader(f'🩸 {view_user} 的尿酸趨勢 ({meal_filter})')
                st.line_chart(chart_df['尿酸'].dropna())
                
                st.subheader(f'⚖️ {view_user} 的體重趨勢 ({meal_filter})')
                st.line_chart(chart_df['體重'].dropna())
            else:
                st.warning(f"⚠️ {view_user} 暫時未有「{meal_filter}」嘅紀錄呀！")
            
            # 顯示詳細歷史紀錄表格 (升級做可編輯版本！)
            st.subheader('📋 詳細歷史紀錄 (可直接雙擊修改或選取刪除)')
            
            edited_df = st.data_editor(
                filtered_df, 
                num_rows="dynamic",        
                use_container_width=True,
                key=f"editor_{view_user}"  
            )
            
            if st.button('🔄 儲存表格修改'):
                main_df_without_user = df[df['使用者'] != view_user]
                df = pd.concat([main_df_without_user, edited_df], ignore_index=True)
                save_data(df)
                st.success(f'✅ 成功更新 {view_user} 的紀錄！')
                st.rerun() 
        else:
            st.info(f'暫時未有 {view_user} 的健康紀錄。')
            
    # 如果密碼唔啱，又唔係留空，就出 Error
    elif input_password != "":
        st.error("❌ 密碼錯誤，請重新輸入！ (如果忘記密碼，請搵 Admin 處理)")

else:
    st.info('目前未有任何使用者，請先在上方新增紀錄！')