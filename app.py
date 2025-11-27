import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import google.generativeai as genai
import time
import json
import urllib.parse 

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
    if not keyword:
        keyword = "台北 房產"
        
    search_query = f"{keyword} site:mobile01.com"
    encoded_query = urllib.parse.quote(search_query)
    
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    try:
        response = requests.get(rss_url, timeout=10)
        
        # [關鍵修正] 改用 'html.parser'，因為雲端不一定有 lxml，這樣寫最穩
        soup = BeautifulSoup(response.text, 'html.parser') 
        items = soup.find_all('item')
        
        articles = []
        for item in items[:10]:
            # 使用 getattr 防呆，避免找不到標籤時報錯
            title = item.title.text if item.title else "無標題"
            link = item.link.text if item.link else "#"
            pub_date = item.pubDate.text if item.pubDate else ""
            
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

# --- 4. 定義函數：AI 分析 ---
def analyze_with_gemini(df, use_fake=False):
    if use_fake or not api_key:
        time.sleep(1) 
        st.toast("使用模擬 AI 結果...")
        
        demo_sentiments = []
        demo_sentiments.append("焦慮")
        demo_sentiments.append("負面")
        demo_sentiments.append("正面")
        demo_sentiments.append("觀望")
        demo_sentiments.append("中立")
        
        demo_keywords = []
        demo_keywords.append("價格過高, CP值低")
        demo_keywords.append("漏水, 施工品質")
        demo_keywords.append("格局方正, 採光好")
        demo_keywords.append("升息, 房市高點")
        demo_keywords.append("老屋翻修, 重劃區")
        
        while len(demo_sentiments) < len(df):
            demo_sentiments.extend(demo_sentiments)
            demo_keywords.extend(demo_keywords)
            
        df['AI情緒'] = demo_sentiments[:len(df)]
        df['關鍵重點'] = demo_keywords[:len(df)]
        
        return df, None 
        
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
        for item in result_json:
            sentiments.append(item.get('sentiment', '未知'))
            
        keywords = []
        for item in result_json:
            keywords.append(item.get('keyword', '無'))
        
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

# --- 搜尋區塊 ---
st.write("### 🔍 關鍵字搜尋")
col_input, col_btn = st.columns([3, 1])

with col_input:
    keyword = st.text_input("輸入關鍵字 (例如：大安區、預售屋、建案名稱)", "大安區")

with col_btn:
    st.write("") 
    st.write("")
    if st.button("🚀 搜尋真實資料", type="primary"):
        with st.spinner(f'正在 Google 尋找 Mobile01 上關於「{keyword}」的文章...'):
            st.session_state.data = search_mobile01_via_google(keyword)
            if not st.session_state.data:
                st.warning("找不到相關資料，請換個關鍵字試試")

# 備用按鈕
if st.button("📂 載入測試資料 (Demo Mode)", help="如果搜尋壞掉可以用這個"):
    st.session_state.data = get_demo_data()
    st.success("已載入模擬數據！")

# --- 6. 顯示內容區 ---

if st.session_state.data:
    df = pd.DataFrame(st.session_state.data)
    
    st.divider()
    st.write(f"###
