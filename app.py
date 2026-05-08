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

df = load_data()

st.title('🏠 家庭健康紀錄 App')

# ==========================================
# 第一部分：輸入區 (Input Form)
# ==========================================
st.header('📝 新增紀錄')

# 1. 取得資料庫中已有的使用者名單（排除重複）
existing_users = df['使用者'].dropna().unique().tolist()

with st.form("input_form", clear_on_submit=True):
    # 提供下拉選單畀舊用戶，預設第一個選項係「-- 新增使用者 --」
    options = ['-- 新增使用者 --'] + existing_users
    selected_user = st.selectbox('選擇使用者', options)
    
    # 提供文字框畀新用戶輸入名字
    new_user = st.text_input('如果係新使用者，請喺度輸入名字：', placeholder="例如：阿哥")
    
    col1, col2 = st.columns(2)
    with col1:
        record_date = st.date_input('日期', date.today())
    with col2:
        # 預設時間設定為現在這一刻 (now)，並將秒數隱藏
        record_time = st.time_input('時間', datetime.now().replace(second=0, microsecond=0).time())
        
    blood_sugar = st.number_input('血糖 (mmol/L)', min_value=0.0, value=None, format="%.1f")
    uric_acid = st.number_input('尿酸 (μmol/L)', min_value=0.0, value=None, format="%.1f")
    
    weight = st.number_input('體重 (kg)', min_value=0.0, value=None, format="%.1f")
    notes = st.selectbox('備註', ['飯前', '飯後'])
    
    submit_button = st.form_submit_button(label='💾 儲存紀錄')
    
    if submit_button:
        final_user = new_user.strip() if new_user.strip() != "" else selected_user
        
        if final_user == '-- 新增使用者 --' or final_user == "":
            st.error("⚠️ 請選擇或輸入使用者名稱！")
        else:
            new_data = pd.DataFrame([{
                '日期': str(record_date),
                '時間': str(record_time.strftime("%H:%M")), # <--- 將時間格式化為 小時:分鐘 (例如 14:30)
                '使用者': final_user,
                '血糖': blood_sugar,
                '尿酸': uric_acid,
                '體重': weight,
                '備註': notes
            }])
            df = pd.concat([df, new_data], ignore_index=True)
            save_data(df)
            
            st.success(f'✅ 成功儲存 {final_user} 的紀錄！')
            st.rerun()

# ==========================================
# 第二部分：展示區 (Dashboard) - 數據獨立的核心！
# ==========================================
st.header('📊 查看數據')

if not df.empty:
    # 同樣動態讀取名單
    existing_users = df['使用者'].dropna().unique().tolist()
    
    if existing_users:
        view_user = st.selectbox('你想查看誰的數據？', existing_users)
        
        filtered_df = df[df['使用者'] == view_user]
    
    if not filtered_df.empty:
        # --- 👇 新增：飯前/飯後篩選器 👇 ---
        # 加入 horizontal=True 令啲掣橫向排列，慳位啲又靚啲
        meal_filter = st.radio('🔍 篩選圖表顯示時段：', ['全部', '飯前', '飯後'], horizontal=True)
        
        # 複製一份數據用嚟處理圖表，避免影響下方嘅 st.data_editor 歷史表格
        chart_df = filtered_df.copy()
        
        # 根據用家選擇，過濾數據
        if meal_filter != '全部':
            # 如果揀咗飯前/飯後，就淨係保留「備註」欄位符合選擇嘅數據
            chart_df = chart_df[chart_df['備註'] == meal_filter]
        # --- 👆 篩選器完畢 👆 ---
        
        # 檢查篩選之後仲有冇數據 (例如可能揀咗「飯後」但其實從來未入過飯後數據)
        if not chart_df.empty:
            # 1. 合併並轉換成時間格式 (為咗可以正確排序)
            chart_df['日期時間'] = pd.to_datetime(chart_df['日期'] + ' ' + chart_df['時間'])
            
            # 2. 按時間先後排好次序
            chart_df = chart_df.sort_values('日期時間')
            
            # 3. 排好序之後，將時間轉換返做「純文字字串」
            chart_df['日期時間'] = chart_df['日期時間'].dt.strftime('%Y-%m-%d %H:%M')
            
            # 4. 設定為 X 軸 (Index)
            chart_df = chart_df.set_index('日期時間')
            
            # 顯示血糖折線圖
            st.subheader(f'📈 {view_user} 的血糖趨勢 ({meal_filter})')
            st.line_chart(chart_df['血糖'].dropna())
            
            # 顯示尿酸折線圖
            st.subheader(f'🩸 {view_user} 的尿酸趨勢 ({meal_filter})')
            st.line_chart(chart_df['尿酸'].dropna())
            
            # 顯示體重折線圖
            st.subheader(f'⚖️ {view_user} 的體重趨勢 ({meal_filter})')
            st.line_chart(chart_df['體重'].dropna())
        else:
            # 如果篩選後無數據，就顯示溫馨提示
            st.warning(f"⚠️ {view_user} 暫時未有「{meal_filter}」嘅紀錄呀！")
        
        # 顯示詳細歷史紀錄表格 (升級做可編輯版本！)
        st.subheader('📋 詳細歷史紀錄 (可直接雙擊修改或選取刪除)')
        
        # 使用 st.data_editor 代替原本嘅 st.dataframe
        edited_df = st.data_editor(
            filtered_df, 
            num_rows="dynamic",        # 開啟呢個設定就可以畀用家新增或刪除整行資料
            use_container_width=True,
            key=f"editor_{view_user}"  # 加入 key 確保切換使用者時表格識得重新載入
        )
        
        # 加一個專屬按鈕去確認儲存表格嘅修改
        if st.button('🔄 儲存表格修改'):
            # 邏輯：先喺主資料庫 (df) 移除呢個 user 嘅所有舊紀錄
            main_df_without_user = df[df['使用者'] != view_user]
            
            # 然後將畫面上面修改好嘅新表格 (edited_df) 合併返入去
            df = pd.concat([main_df_without_user, edited_df], ignore_index=True)
            
            # 儲存入 Google Sheets
            save_data(df)
            
            st.success(f'✅ 成功更新 {view_user} 的紀錄！')
            st.rerun() # 重新載入頁面更新圖表
    else:
        st.info(f'暫時未有 {view_user} 的紀錄。')
else:
    st.info('目前未有任何數據，請先在上方新增紀錄！')