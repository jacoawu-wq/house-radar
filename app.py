import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai
import time
import json
import urllib.parse
import xml.etree.ElementTree as ET # 使用 Python 內建的 XML 解析器

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
        st.success("✅ API Key 已設定 (真實 AI 模式)")
    else:
        st.warning("⚠️ 未偵測到 Key (將使用模擬模式)")
    
    st.divider()
    force_demo_ai = st.checkbox("🔧 強制使用模擬 AI 結果 (Demo用)", value=False)

# --- 3. 定義函數：透過 Google News 搜尋 Mobile01 ---
def search_mobile01_via_google(keyword):
    if not keyword:
        keyword = "台北 房產"
        
    search_query = f"{keyword} site:mobile01.com"
    encoded_query = urllib.parse.quote(search_query)
    
    # Google RSS URL
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    try:
        response = requests.get(rss_url, timeout=10)
        
        # [核心修正] 改用 Python 內建的 ElementTree 解析 XML
        # 這能保證 <link> 裡面的網址不會被當成 HTML 丟掉
        root = ET.fromstring(response.content)
        
        articles = []
        # XML 結構通常是 channel -> item
        items = root.findall('.//item')
        
        for item in items[:10]:
            title_elem = item.find('title')
            link_elem = item.find('link')
            pub_elem = item.find('pubDate')
            
            title = title_elem.text if title_elem is not None else "無標題"
            link = link_elem.text if link_elem is not None else "#"
            pub_date = pub_elem.text if pub_elem is not None else ""
            
            # 清理標題
            title = title.replace("- Mobile01", "").strip()
