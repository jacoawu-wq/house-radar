import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import google.generativeai as genai
import time
import json
import urllib.parse # 用來處理中文關鍵字編碼

# --- 1. 設定頁面 ---
st.set_page_config(page_title="房市輿情雷達 AI 版", page_icon="🏠", layout="wide")

# --- 2. 側邊欄：設定 API Key ---
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.secrets.get("GEMINI_API_KEY", None)
    
    if not api_key:
        api_key = st.text_input("請輸入 Google Gemini API Key", type="password")
    
    if api_key:
        genai.configure(api_key=api_key)
        st.success("✅ API Key 已設定")
    else:
        st.warning("⚠️ 請輸入 API Key 才能使用 AI 分析")
    
    st.divider()
    force_demo_ai = st.checkbox("🔧 強制使用模擬 AI 結果 (API 壞掉時用)", value=False)

# --- 3. 定義函數：透過 Google News 搜尋 Mobile01 ---
def search_mobile01_via_google(keyword):
    # 如果使用者沒輸入關鍵字，預設查 "台北 房產"
    if not keyword:
        keyword = "台北 房產"
        
    # 組合搜尋語法：關鍵字 + 限定 mobile01.com 網站
    # 例如： "大安區 site:mobile01.com"
    search_query = f"{keyword} site:mobile01.com"
    encoded_query = urllib.parse.quote(search_query)
    
    # Google News RSS 網址 (這是公開且免費的接口，比較不會擋 IP)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    try:
        response = requests.get(rss_url, timeout=10)
        
        # 解析 XML
        soup = BeautifulSoup(response.text, 'xml') # 使用 xml 解析模式
        items = soup.find_all('item')
        
        articles = []
        for item in items[:10]: # 只抓前 10 筆，避免 AI 分析太久
            title = item.title.text
            link = item.link.text
            pub_date = item.pubDate.text if item.pubDate else ""
            
            # 清理標題 (Google 標題通常會帶有 "- Mobile01"，把它去掉比較乾淨)
            title = title.replace("- Mobile01", "").strip()
            
            articles.append({
                "標題": title,
                "連結": link,
                "來源": "Mobile01 (Google搜尋)",
                "發布時間": pub_date
            })
            
        return articles

    except Exception as e:
        st.error(f"搜尋發生錯誤: {e}")
        return []

def get_demo_data():
    return [
        {"標題": "大安區預售屋開價破百萬合理嗎？最近看的心很累", "連結": "#", "來源": "Demo"},
        {"標題": "請問 XX 建案的施工品質如何？聽說之前有漏水案例", "連結": "#", "來源": "Demo"},
        {"標題": "分享：終於簽約了！推薦大家去看這間，格局真的很棒", "連結": "#", "來源": "Demo"},
        {"標題": "現在進場是不是高點？想買房自住但怕被套牢", "連結": "#", "來源": "Demo"},
        {"標題": "信義區舊公寓 vs 新北重劃區新成屋 怎麼選？", "連結": "#", "來源": "Demo"},
    ]

# --- 4. 定義函數：AI 分析 (防彈版) ---
def analyze_with_gemini(df, use_fake=False):
    if use_fake or not api_key:
        time.sleep(1) 
        st.toast("使用模擬 AI 結果...")
        
        # 簡單的模擬資料
        demo_sentiments = []
        demo_keywords = []
        
        # 迴圈產生足夠數量的假資料
        base_sents = ["焦慮", "負面", "正面", "觀望", "中立"]
        base_keys = ["價格, 預算", "漏水, 品質", "格局, 採光", "升息, 政策", "一般討論"]
        
        for i in range(len(df)):
            demo_sentiments.append(base_sents[i % 5])
            demo_keywords.append(base_keys[i % 5])
            
        df['AI情緒'] = demo_sentiments
        df['關鍵重點'] = demo_keywords
        
        return df, None 
        
    # 真實 AI 分析
    model = genai.GenerativeModel('gemini-1.5-flash')
    titles_text = "\n".join([f"{i+1}. {t}" for i, t in enumerate(df['標題'].tolist())])
    
    prompt = f"""
    你是專業的房地產分析師。請分析以下來自 Mobile01 的討論標題：
    {titles_text}
    
    請針對每一個標題，回傳 Python list of dictionaries 格式（不要 Markdown）：
    [
        {{"sentiment": "正面/負面/中立/焦慮", "keyword": "關鍵字1, 關鍵字2"}}
    ]
    確保回傳的 list 長度與標題數量一致。
    """
    
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        
        try:
            result_json = json.loads(clean_text)
        except:
            start = clean_text.find('[')
            end = clean_text.rfind(']') + 1
            result_json = json.loads(clean_text[start:end])

        sentiments = []
        keywords = []
        
        for item in result_json:
            sentiments.append(item.get('sentiment', '未知'))
            keywords.append(item.get('keyword', '無'))
        
        # 補齊長度
        while len(sentiments) < len(df):
            sentiments.append("未知")
            keywords.append("無")
            
        df['AI情緒'] = sentiments[:len(df)]
        df['關鍵重點'] = keywords[:len(df)]
        return df, None 
        
    except Exception as e:
        error_msg = str(e)
        df['AI情緒'] = "連線失敗"
        df['關鍵重點'] = "API Error"
        return df, error_msg

# --- 5. 主程式介面 ---
st.title("🏠 房市輿情雷達 + AI 分析")

# 初始化 session state
if 'data' not in st.session_state:
    st.session_state.data = []

# --- 搜尋區塊 (Search Area) ---
st.write("### 🔍 關鍵字搜尋")
col_input, col_btn = st.columns([3, 1])

with col_input:
    # 讓使用者輸入想查的字，預設為「大安區」
    keyword = st.text_input("輸入關鍵字 (例如：大安區、預售屋、建案名稱)", "大安區")

with col_btn:
    # 為了排版美觀，加一點空白往下推
    st.write("") 
    st.write("")
    if st.button("🚀 搜尋真實資料", type="primary"):
        with st.spinner(f'正在 Google 尋找 Mobile01 上關於「{keyword}」的文章...'):
            st.session_state.data = search_mobile01_via_google(keyword)
            if not st.session_state.data:
                st.warning("找不到相關資料，請換個關鍵字試試")

# 備用按鈕放在下面
if st.button("📂 載入測試資料 (Demo Mode)", help="如果搜尋壞掉可以用這個"):
    st.session_state.data = get_demo_data()
    st.success("已載入模擬數據！")

# --- 6. 顯示內容區 ---

if st.session_state.data:
    df = pd.DataFrame(st.session_state.data)
    
    st.divider()
    st.write(f"### 📋 搜尋結果: {len(df)} 筆")
    
    display_col1, display_col2 = st.columns([3, 1])
    
    with display_col1:
        st.dataframe(
            df[['標題', '連結']], 
            column_config={"連結": st.column_config.LinkColumn()},
            use_container_width=True
        )
    
    with display_col2:
        st.info("💡 取得資料後，請點擊下方按鈕進行 AI 解讀")
        
        if st.button("🤖 AI 情緒分析"):
            with st.spinner("AI 正在閱讀標題並分析情緒..."):
                result, error = analyze_with_gemini(df, use_fake=force_demo_ai)
                
                st.session_state.analyzed_data = result
                
                if error:
                    st.session_state.error_msg = error
                else:
                    st.session_state.error_msg = None
                    
                st.rerun()

    # 顯示分析結果
    if 'analyzed_data' in st.session_state:
        st.divider()
        st.subheader("📊 AI 洞察報告")
        
        if st.session_state.get('error_msg'):
            st.error(f"AI 連線異常: {st.session_state.error_msg}")

        result_df = st.session_state.analyzed_data
        if 'AI情緒' in result_df.columns:
            st.dataframe(
                result_df[['標題', 'AI情緒', '關鍵重點']],
                use_container_width=True
            )
            
            st.write("#### 情緒分佈")
            st.bar_chart(result_df['AI情緒'].value_counts())
        else:
            st.error("資料格式異常")
