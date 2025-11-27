import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import google.generativeai as genai
import time

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

# --- 3. 定義函數：爬蟲與模擬數據 ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def scrape_mobile01_taipei():
    url = "https://www.mobile01.com/topiclist.php?f=356"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            st.error(f"無法存取 Mobile01 (代碼: {response.status_code})")
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

def get_demo_data():
    return [
        {"標題": "大安區預售屋開價破百萬合理嗎？最近看的心很累", "連結": "#", "來源": "Demo"},
        {"標題": "請問 XX 建案的施工品質如何？聽說之前有漏水案例", "連結": "#", "來源": "Demo"},
        {"標題": "分享：終於簽約了！推薦大家去看這間，格局真的很棒", "連結": "#", "來源": "Demo"},
        {"標題": "現在進場是不是高點？想買房自住但怕被套牢", "連結": "#", "來源": "Demo"},
        {"標題": "信義區舊公寓 vs 新北重劃區新成屋 怎麼選？", "連結": "#", "來源": "Demo"},
    ]

# --- 4. 定義函數：AI 分析 (已修復錯誤) ---
def analyze_with_gemini(df, use_fake=False):
    # 如果開啟強制模擬，或者沒有 API Key，就直接回傳假結果
    if use_fake or not api_key:
        time.sleep(1) 
        st.toast("使用模擬 AI 結果...")
        
        # 產生假情緒數據
        demo_sentiments = ["焦慮", "負面", "正面", "觀望", "中立"]
        demo_keywords = ["價格過高, CP值低", "漏水, 施工品質", "格局方正, 採光好", "升息,
