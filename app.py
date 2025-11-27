import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import google.generativeai as genai
import os

# --- 設定頁面 ---
st.set_page_config(page_title="房市輿情雷達 AI 版", page_icon="🏠", layout="wide")

# --- 設定 API Key (在本機測試時使用，上傳雲端後會改用 Secrets) ---
# 這裡有一個防呆機制：如果雲端設定了就用雲端的，沒設定就嘗試讀取環境變數或讓使用者輸入
api_key = st.secrets.get("GEMINI_API_KEY") 

# 如果沒有在 secrets 找到 key，就在側邊欄讓使用者輸入（方便你本機測試）
if not api_key:
    with st.sidebar:
        api_key = st.text_input("請輸入 Google Gemini API Key", type="password")

if api_key:
    genai.configure(api_key=api_key)

# --- 爬蟲函數 (保持不變) ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def scrape_mobile01_taipei():
    url = "https://www.mobile01.com/topiclist.php?f=356"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []
        rows = soup.find_all('div', class_='c-listTableTd__title')
        for row in rows:
            link_tag = row.find('a', class_='c-link')
            if link_tag:
                title = link_tag.text.strip()
                link = "https://www.mobile01.com/" + link_tag['href']
                if "公告" in title: continue
                articles.append({"標題": title, "連結": link, "來源": "Mobile01"})
        return articles
    except Exception as e:
        st.error(f"爬蟲錯誤: {e}")
        return []

# --- AI 分析函數 (新功能) ---
def analyze_with_gemini(df):
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # 為了省錢省時間，我們把標題打包成一個字串一次問 AI
    titles_text = "\n".join([f"{i+1}. {t}" for i, t in enumerate(df['標題'].tolist())])
    
    prompt = f"""
    你是專業的房地產分析師。請分析以下 Mobile01 房地產討論區的標題：
    
    {titles_text}
    
    請針對每一個標題，回傳以下資訊：
    1. 情緒：(正面/負面/中立/觀望)
    2. 關鍵字：(提取1-2個核心關鍵字，如：房價、大安區、漏水)
    
    請直接給我一個 Python list of dictionaries 格式的回覆，不要有 markdown 標記，格式如下：
    [
        {{"id": 1, "sentiment": "負面", "keyword": "房價過高"}},
        ...
    ]
    """
    
    try:
        response = model.generate_content(prompt)
        # 清理回傳格式，確保是純文字
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        import json
        result_json = json.loads(clean_text)
        
        # 將 AI 結果合併回 DataFrame
        sentiments = []
        keywords = []
        for item in result_json:
            sentiments.append(item.get('sentiment', '未知'))
            keywords.append(item.get('keyword', '無'))
            
        # 確保長度一致（防呆）
        if len(sentiments) == len(df):
            df['AI情緒'] = sentiments
            df['關鍵重點'] = keywords
        else:
            st.warning("AI 分析數量與文章數不符，顯示原始資料")
            
        return df
        
    except Exception as e:
        st.error(f"AI 分析失敗: {e}")
        return df

# --- 主程式 ---
st.title("🏠 房市輿情雷達 + AI 分析")

# 爬取資料
if 'data' not in st.session_state:
    with st.spinner('正在抓取資料...'):
        st.session_state.data = scrape_mobile01_taipei()

if st.session_state.data:
    df = pd.DataFrame(st.session_state.data)
    
    # 操作區
    col1, col2 = st.columns([3, 1])
    with col1:
        st.dataframe(
            df[['標題', '連結']], 
            column_config={"連結": st.column_config.LinkColumn()},
            use_container_width=True,
            height=300
        )
    
    with col2:
        st.write("### AI 控制台")
        if not api_key:
            st.warning("請先在側邊欄輸入 API Key")
        else:
            if st.button("🤖 AI 分析本頁面", type="primary"):
                with st.spinner("AI 正在閱讀這些標題..."):
                    df_analyzed = analyze_with_gemini(df)
                    st.session_state.analyzed_data = df_analyzed
                    st.rerun() # 重新整理頁面以顯示結果

    # 顯示分析結果
    if 'analyzed_data' in st.session_state:
        st.write("---")
        st.subheader("📊 AI 分析報告")
        st.dataframe(
            st.session_state.analyzed_data[['標題', 'AI情緒', '關鍵重點']],
            use_container_width=True
        )
        
        # 簡單圖表
        st.bar_chart(st.session_state.analyzed_data['AI情緒'].value_counts())

else:
    st.write("無資料")
