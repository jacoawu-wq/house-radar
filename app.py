import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai
import time
import json
import urllib.parse
import xml.etree.ElementTree as ET
import re
import jieba 
from wordcloud import WordCloud 
import matplotlib.pyplot as plt 
import os
import altair as alt 

# --- 1. 設定頁面 ---
st.set_page_config(page_title="房市輿情雷達 AI 版", page_icon="🏠", layout="wide")

# --- 2. 側邊欄設定 ---
with st.sidebar:
    st.header("⚙️ 設定")
    if 'valid_api_key' not in st.session_state:
        st.session_state.valid_api_key = st.secrets.get("GEMINI_API_KEY", None)
    if not st.session_state.valid_api_key:
        user_input_key = st.text_input("請輸入 Google Gemini API Key", type="password")
        if st.button("✅ 驗證並設定", type="primary"):
            if not user_input_key: st.error("❌ 請輸入內容")
            else:
                try:
                    genai.configure(api_key=user_input_key)
                    list(genai.list_models()) 
                    st.session_state.valid_api_key = user_input_key
                    st.success("驗證成功！")
                    time.sleep(1)
                    st.rerun()
                except Exception as e: st.error(f"❌ 無效: {e}")
    else:
        st.success("✅ API Key 已設定")
        if st.secrets.get("GEMINI_API_KEY") is None:
            if st.button("🔄 清除/更換 Key"):
                st.session_state.valid_api_key = None
                st.rerun()
    st.divider()
    force_demo_ai = st.checkbox("🔧 強制使用模擬 AI 結果 (Demo用)", value=False)

# --- 模型智慧選擇 ---
def get_best_model_name(api_key):
    try:
        genai.configure(api_key=api_key)
        all_models = list(genai.list_models())
        text_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
        for m in text_models:
            if 'gemini-1.5-flash' in m: return m
        for m in text_models:
            if 'gemini-pro' in m: return m
        if text_models: return text_models[0]
        return "gemini-pro"
    except: return "gemini-pro"

# --- 黑名單與標題過濾 ---
BLOCKED_FORUM_IDS = [
    "f=214", "f=260", "f=261", # 汽車
    "f=565", "f=168", "f=738", # 家電
    "f=61", "f=37", "f=320",   # 3C、相機
    "f=566", "f=770", "f=132"  # 穿戴
]

# [修正] 擴充負面關鍵字，包含政治與非房產雜訊
NEGATIVE_KEYWORDS = [
    "相機", "鏡頭", "開箱", "手機", "耳機", "音響", "喇叭", "儲存裝置", "硬碟", 
    "顯卡", "筆電", "螢幕", "滑鼠", "鍵盤", "牛肉麵", "食記", "遊記", "攝影", "拍攝",
    "Nikon", "Sony", "Canon", "Samsung", "iPhone", "Android",
    "菜單", "交車", "保養", "試駕", "維修", "徵求", "車友",
    "柯文哲", "蔣萬安", "弊案", "圖利", "選舉", "黨部", "政治"
]

def is_blocked_link(link):
    if not link: return True
    for fid in BLOCKED_FORUM_IDS:
        if fid in link: return True
    return False

def is_irrelevant_title(title):
    for kw in NEGATIVE_KEYWORDS:
        if kw.lower() in title.lower():
            return True
    return False

def get_topic_id(link):
    match = re.search(r't=(\d+)', link)
    if match: return int(match.group(1))
    return 0

# --- 自動下載中文字型 ---
def download_font():
    font_filename = "ChineseFont.ttf" 
    if os.path.exists(font_filename):
        if os.path.getsize(font_filename) < 1000000: 
            os.remove(font_filename) 
        else:
            return font_filename 
    urls = [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanstc/NotoSansTC-Regular.ttf",
        "https://raw.githubusercontent.com/justfont/open-huninn-font/master/font/jf-openhuninn-1.1.ttf",
        "https://github.com/anthonyhilyard/GitHub-Chinese-Fonts/raw/master/WenQuanYiMicroHei.ttf"
    ]
    progress_text = "正在下載中文字型資源... (嘗試多個來源)"
    my_bar = st.progress(0, text=progress_text)
    for i, url in enumerate(urls):
        try:
            my_bar.progress((i + 1) * 33, text=f"正在嘗試下載字型來源 {i+1}/3 ...")
            response = requests.get(url, timeout=60) 
            if response.status_code == 200:
                with open(font_filename, "wb") as f:
                    f.write(response.content)
                if os.path.getsize(font_filename) > 1000000:
                    my_bar.empty() 
                    return font_filename
        except: continue
    my_bar.empty()
    st.warning("所有字型下載來源均失敗，文字雲將無法顯示中文。")
    return None

# --- 產生文字雲 ---
def generate_wordcloud(titles_list, user_keywords_str=""):
    text = " ".join(titles_list)
    stopwords = {
        "的", "了", "在", "是", "我", "有", "和", "就", "人", "都", "一個", "上", "也", "很", "到", "說", "要", "去", "你",
        "會", "著", "沒有", "看", "好", "自己", "這", "請問", "請益", "討論", "分享", "問題", "大家", "知道", 
        "Mobile01", "mobile01", "MOBILE01", "Moible01", 
        "什麼", "怎麼", "可以", "真的", "因為", "所以", "如果", "但是", "比較", "覺得", "現在", "還是", "有沒有", "文章",
        "標題", "連結", "來源", "發布時間", "房產", "台北", "台灣", "討論區", "專區", "新聞", "報導", "表示", "指出"
    }
    
    if user_keywords_str:
        for k in user_keywords_str.split():
            stopwords.add(k)
            
    try:
        hot_terms = [
            "黃仁勳", "輝達", "NVIDIA", "台積電", "北士科", "科學園區", "軟體園區", 
            "預售屋", "新青安", "高鐵", "捷運", "AI", "半導體", "單價", "總價"
        ]
        for term in hot_terms:
            jieba.add_word(term)

        words = jieba.cut(text)
        filtered_words = [word for word in words if word not in stopwords and len(word) > 1]
        text_clean = " ".join(filtered_words)
        if not text_clean.strip(): return None 
        font_path = download_font()
        if font_path:
            wc = WordCloud(
                font_path=font_path, background_color="white", width=800, height=400, max_words=80, colormap="viridis", font_step=2, min_font_size=10
            ).generate(text_clean)
        else:
            wc = WordCloud(background_color="white", width=800, height=400, max_words=80).generate(text_clean)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        return fig
    except Exception as e:
        print(f"文字雲繪製失敗: {e}") 
        return None

# --- 3.1 搜尋 Mobile01 ---
def search_mobile01_via_google(keyword_input):
    if not keyword_input: 
        keyword_input = "台北 房產"
        keywords = ["台北", "房產"]
    else:
        keywords = keyword_input.split()

    real_estate_terms = "預售 OR 建案 OR 房價 OR 坪數 OR 格局 OR 公寓 OR 大樓 OR 豪宅 OR 置產 OR 買房"
    
    if len(keywords) > 1:
        keyword_part = f"({' OR '.join(keywords)})"
    else:
        keyword_part = keyword_input
        
    search_query = f"{keyword_part} ({real_estate_terms}) site:mobile01.com when:1y"
    encoded_query = urllib.parse.quote(search_query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        response = requests.get(rss_url, timeout=10)
        root = ET.fromstring(response.content)
        articles = []
        items = root.findall('.//item')
        
        for item in items[:60]: 
            title = item.find('title').text if item.find('title') is not None else "無標題"
            link = item.find('link').text if item.find('link') is not None else "#"
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            title = re.sub(r'(?i)\s*[-|]\s*mobile01', '', title).strip()
            
            if is_irrelevant_title(title): continue
            if not any(k in title for k in keywords): continue
            
            tid = get_topic_id(link)
            articles.append({"標題": title, "連結": link, "來源": "Mobile01", "發布時間": pub_date, "topic_id": tid})
            
        articles.sort(key=lambda x: x['topic_id'], reverse=True)
        return articles[:10]
    except Exception as e:
        st.error(f"Mobile01 搜尋錯誤: {e}"); return []

# --- 3.2 搜尋一般新聞 ---
def search_general_news_via_google(keyword_input):
    if not keyword_input: return []
    keywords = keyword_input.split()
    
    if len(keywords) > 1:
        keyword_part = f"({' OR '.join(keywords)})"
    else:
        keyword_part = keyword_input
        
    search_query = f"{keyword_part} -site:mobile01.com -site:ptt.cc when:1y"
    encoded_query = urllib.parse.quote(search_query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    try:
        response = requests.get(rss_url, timeout=10)
        root = ET.fromstring(response.content)
        articles = []
        items = root.findall('.//item')
        
        for item in items[:20]:
            title = item.find('title').text if item.find('title') is not None else ""
            title = re.sub(r'\s*-\s*.*', '', title).strip()
            # 這裡也要過濾掉政治雜訊
            if title and not is_irrelevant_title(title):
                articles.append(title)
        return articles
    except:
        return []

def get_demo_data():
    return [{"標題": "北士科預售屋開價破百萬合理嗎？心很累", "連結": "https://www.mobile01.com/t=999"}]

# --- 4. AI 分析 ---
def analyze_with_gemini(df, use_fake=False):
    current_key = st.session_state.valid_api_key
    is_simulated = use_fake or (not current_key)

    if is_simulated:
        time.sleep(1)
        fake_summary = f"【模擬快報】針對本次搜尋結果，整體市場氛圍偏向觀望與焦慮..."
        demo_sentiments = ["焦慮", "負面", "正面", "觀望", "中立"] * 3
        demo_keywords = ["價格過高", "漏水疑慮", "格局方正", "高點套牢", "重劃區發展"] * 3
        df['AI情緒'] = demo_sentiments[:len(df)]
        df['關鍵重點'] = demo_keywords[:len(df)]
        return df, fake_summary, None, True
    
    try:
        genai.configure(api_key=current_key)
        best_model = get_best_model_name(current_key)
        model = genai.GenerativeModel(best_model) 
        titles_text = "\n".join([f"{i+1}. {t}" for i, t in enumerate(df['標題'].tolist())])
        
        prompt = f"""
        你是專業的房地產輿情分析師。請閱讀以下 Mobile01 討論區的標題：
        {titles_text}
        
        請執行以下任務：
        1. 判斷每一個標題是否與「房地產、購屋、建案、裝潢、居住」相關。
        2. 如果標題與房地產無關，請將情緒設為「非房產」，關鍵字設為「無」。
        3. 撰寫「市場輿情快報」(約 3-5 句話)，只總結與房地產相關的內容。
        
        請直接回傳一個 JSON 格式的資料，格式如下（不要 Markdown 標記）：
        {{
            "summary_report": "在這裡填寫你的市場輿情快報內容...",
            "details": [
                {{"sentiment": "正面/負面/中立/焦慮/觀望/非房產", "keyword": "關鍵字1, 關鍵字2"}}
            ]
        }}
        """
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        try:
            result_json = json.loads(clean_text)
            summary_report = result_json.get("summary_report", "AI 無法產生總結報告。")
            details = result_json.get("details", [])
        except:
            summary_report = "AI 回傳格式異常，無法解析總結報告。"
            details = []
        sentiments = [item.get('sentiment', '未知') for item in details]
        keywords = [item.get('keyword', '無') for item in details]
        while len(sentiments) < len(df):
            sentiments.append("未知"); keywords.append("無")
        df['AI情緒'] = sentiments[:len(df)]
        df['關鍵重點'] = keywords[:len(df)]
        
        df_filtered = df[df['AI情緒'] != '非房產'].reset_index(drop=True)
        return df_filtered, summary_report, None, False 
    except Exception as e:
        return df, "", str(e), False

# --- 5. 主程式介面 ---
st.title("🏠 房市輿情雷達 + AI 洞察") 

if 'data' not in st.session_state: st.session_state.data = []
if 'news_data' not in st.session_state: st.session_state.news_data = [] 
if 'analyzed_data' not in st.session_state: st.session_state.analyzed_data = None
if 'summary_report' not in st.session_state: st.session_state.summary_report = ""

st.write("### 🔍 輿情關鍵字搜尋")
col_input, col_btn = st.columns([3, 1])
with col_input:
    keyword = st.text_input("輸入關鍵字 (可多組，例如：北士科 士林)", "北士科")
with col_btn:
    st.write(""); st.write("")
    if st.button("🚀 搜尋最新話題", type="primary"):
        with st.spinner(f'正在進行雙軌搜尋：Mobile01 討論 + 相關新聞...'):
            st.session_state.data = search_mobile01_via_google(keyword)
            st.session_state.news_data = search_general_news_via_google(keyword)
            st.session_state.analyzed_data = None
            st.session_state.summary_report = ""
            if not st.session_state.data: 
                st.warning(f"Mobile01 找不到相關討論，但我們嘗試抓取新聞。")

if st.button("📂 載入範例資料 (Demo)", help="搜尋不到時使用"):
    st.session_state.data = get_demo_data()
    st.session_state.news_data = ["北士科房價創新高", "黃仁勳來台帶動AI園區發展", "輝達設廠地點曝光"] 
    st.session_state.analyzed_data = None 
    st.success("已載入模擬數據！")

# --- 6. 顯示內容區 ---
if st.session_state.data or st.session_state.news_data:
    df = pd.DataFrame(st.session_state.data) if st.session_state.data else pd.DataFrame()
    st.divider()
    
    tab1, tab2 = st.tabs(["📋 原始話題列表", "📊 AI 洞察報告 & 文字雲"])
    
    with tab1: 
        if not df.empty:
            st.write(f"共蒐集 {len(df)} 則 Mobile01 話題")
            st.dataframe(df[['標題', '連結']], 
                         column_config={"連結": st.column_config.LinkColumn("文章連結")},
                         use_container_width=True)
        else:
            st.info("Mobile01 暫無資料。")
        st.info("👉 點擊上方「📊 AI 洞察報告」分頁，啟動 AI 分析功能")

    with tab2: 
        st.write("### 🧠 AI 輿情分析中心")
        
        if st.session_state.analyzed_data is None: 
            if st.button("🤖 啟動 AI 全面解讀 (包含文字雲)", type="primary"):
                with st.spinner("AI 正在閱讀討論串、並根據「相關新聞」繪製文字雲..."):
                    if not df.empty:
                        result_df, summary, error, is_sim = analyze_with_gemini(df, use_fake=force_demo_ai)
                        st.session_state.analyzed_data = result_df
                        st.session_state.summary_report = summary
                        st.session_state.is_simulated = is_sim
                        st.session_state.error_msg = error
                    else:
                        st.session_state.analyzed_data = pd.DataFrame()
                        st.session_state.summary_report = "無 Mobile01 討論數據，僅提供新聞文字雲參考。"
                        st.session_state.is_simulated = False
                        st.session_state.error_msg = None
                    st.rerun()
        
        if st.session_state.summary_report: 
            st.markdown("""---""")
            st.subheader("📝 AI 市場輿情快報 (基於 Mobile01)")
            st.info(st.session_state.summary_report, icon="💡")
            
            st.markdown("""---""")
            col_wc, col_chart = st.columns([3, 2])
            
            with col_wc:
                st.subheader("☁️ 趨勢熱點文字雲 (基於新聞)")
                try:
                    source_titles = st.session_state.news_data if st.session_state.news_data else df['標題']
                    if source_titles and len(source_titles) > 0:
                        wc_fig = generate_wordcloud(source_titles, keyword)
                        if wc_fig:
                            st.pyplot(wc_fig)
                            st.caption(f"資料來源：Google News ({len(source_titles)} 則)")
                        else:
                            st.warning("文字雲產生失敗。")
                    else:
                        st.warning("無足夠新聞資料可繪製文字雲。")
                except Exception as wc_error:
                     st.warning(f"文字雲暫時無法顯示")

            with col_chart:
                st.subheader("📈 情緒分佈 (基於 Mobile01)")
                if st.session_state.analyzed_data is not None and not st.session_state.analyzed_data.empty:
                    display_df = st.session_state.analyzed_data
                    if 'AI情緒' in display_df.columns:
                        chart_data = display_df['AI情緒'].value_counts().reset_index()
                        chart_data.columns = ['情緒', '數量']
                        chart = alt.Chart(chart_data).mark_bar().encode(
                            x=alt.X('情緒', axis=alt.Axis(labelAngle=0, title='情緒類型')), 
                            y=alt.Y('數量', axis=alt.Axis(title='文章數量')),
                            color=alt.value('#1f77b4'),
                            tooltip=['情緒', '數量']
                        ).properties(height=300)
                        st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("無討論數據顯示圖表")

            if st.session_state.analyzed_data is not None and not st.session_state.analyzed_data.empty:
                st.markdown("""---""")
                st.subheader("🔍 詳細分析數據")
                with st.expander("點擊展開查看逐筆分析結果"):
                    st.dataframe(
                        st.session_state.analyzed_data[['連結', '標題', 'AI情緒', '關鍵重點']], 
                        column_config={
                            "連結": st.column_config.LinkColumn("前往"), 
                            "AI情緒": st.column_config.TextColumn("情緒"),
                        },
                        use_container_width=True
                    )
else:
    st.info("👈 請先在左側輸入關鍵字並搜尋")
