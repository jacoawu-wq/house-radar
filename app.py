import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import google.generativeai as genai

# --- 設定頁面 ---
st.set_page_config(page_title="房市輿情雷達 AI 版", page_icon="🏠", layout="wide")

# --- 側邊欄：設定 API Key ---
with st.sidebar:
    st.header("⚙️ 設定")
    # 優先讀取 Secrets，如果沒有則讓使用者輸入
    api_key = st.secrets.get("GEMINI_API_KEY", None)
    
    if not api_key:
        api_key = st.text_input("請輸入 Google Gemini API Key", type="password")
    
    if api_key:
        genai.configure(api_key=api_key)
        st.success("✅ API Key 已設定")
    else:
        st.warning("⚠️ 請輸入 API Key 才能使用 AI 分析")

# --- 爬蟲函數 ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}

def scrape_mobile01_taipei():
    url = "https://www.mobile01.com/topiclist.php?f=356"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        # 顯示狀態碼以供除錯
        if response.status_code != 200:
            st.error(f"無法存取 Mobile01，伺服器回應代碼: {response.status_code} (可能是雲端 IP 被擋)")
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
        st.error(f"爬蟲連線錯誤: {e}")
        return []

# --- 測試資料生成函數 (救命丹) ---
def get_demo_data():
    return [
        {"標題": "大安區預售屋開價破百萬合理嗎？最近看的心很累", "連結": "#", "來源": "Demo"},
        {"標題": "請問 XX 建案的施工品質如何？聽說之前有漏水案例", "連結": "#", "來源": "Demo"},
        {"標題": "分享：終於簽約了！推薦大家去看這間，格局真的很棒", "連結": "#", "來源": "Demo"},
        {"標題": "現在進場是不是高點？想買房自住但怕被套牢", "連結": "#", "來源": "Demo"},
        {"標題": "信義區舊公寓 vs 新北重劃區新成屋 怎麼選？", "連結": "#", "來源": "Demo"},
    ]

# --- AI 分析函數 ---
def analyze_with_gemini(df):
    if not api_key:
        st.error("❌ 請先設定 API Key")
        return df

    model = genai.GenerativeModel('gemini-1.5-flash')
    titles_text = "\n".join([f"{i+1}. {t}" for i, t in enumerate(df['標題'].tolist())])
    
    prompt = f"""
    你是專業的房地產分析師。請分析以下標題：
    {titles_text}
    
    請針對每一個標題，回傳 Python list of dictionaries 格式（不要 Markdown）：
    [
        {{"sentiment": "正面/負面/中立/焦慮", "keyword": "關鍵字1, 關鍵字2"}}
    ]
    確保回傳的 list 長度與標題數量一致。
    """
    
    try:
        response = model.generate_content(prompt)
        # 簡單清洗回傳文字
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        import json
        
        # 嘗試解析 JSON
        try:
            result_json = json.loads(clean_text)
        except:
            # 如果 AI 回傳格式不乾淨，嘗試只抓取 [ ] 內容
            start = clean_text.find('[')
            end = clean_text.rfind(']') + 1
            if start != -1 and end != -1:
                result_json = json.loads(clean_text[start:end])
            else:
                st.error("AI 回傳格式錯誤，無法解析")
                return df

        sentiments = [item.get('sentiment', '未知') for item in result_json]
        keywords = [item.get('keyword', '無') for item in result_json]
        
        # 補齊長度防止錯誤
        while len(sentiments) < len(df):
            sentiments.append("未知")
            keywords.append("無")
            
        df['AI情緒'] = sentiments[:len(df)]
        df['關鍵重點'] = keywords[:len(df)]
            
        return df
        
    except Exception as e:
        st.error(f"AI 分析失敗: {e}")
        return df

# --- 主程式 ---
st.title("🏠 房市輿情雷達 + AI 分析")

# 初始化 session state
if 'data' not in st.session_state:
    st.session_state.data = []

# 按鈕區
col1, col2 = st.columns([1, 4])  # 我把變數名稱改簡單一點，比較不會錯

with col1:
    if st.button("🔄 抓取 Mobile01"): # 按鈕名字也改短一點
        with st.spinner('連線中...'):
            st.session_state.data = scrape_mobile01_taipei()
            if not st.session_state.data:
                st.warning("⚠️ 抓不到資料，請改用右邊的測試按鈕")

with col2:
    if st.button("📂 載入測試資料 (Demo Mode)"):
        st.session_state.data = get_demo_data()
        st.success("已載入模擬數據！")
