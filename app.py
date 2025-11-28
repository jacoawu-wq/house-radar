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

# --- 黑名單 ---
BLOCKED_FORUM_IDS = ["f=214", "f=260", "f=261", "f=565", "f=168", "f=738", "f=61", "f=37", "f=320"]
def is_blocked_link(link):
    if not link: return True
    for fid in BLOCKED_FORUM_IDS:
        if fid in link: return True
    return False

# --- Topic ID ---
def get_topic_id(link):
    match = re.search(r't=(\d+)', link)
    if match: return int(match.group(1))
    return 0

# --- [強力修復] 自動下載中文字型 ---
def download_font():
    # 改用 "文泉驛微米黑"，這是一個非常穩定且常用的開源中文字型
    font_filename = "WenQuanYiMicroHei.ttf"
    font_url = "https://github.com/anthonyhilyard/GitHub-Chinese-Fonts/raw/master/WenQuanYiMicroHei.ttf"
    
    # 檢查檔案是否存在
    if os.path.exists(font_filename):
        # 如果檔案太小 (小於 1MB)，代表上次下載失敗是壞檔，刪掉重抓
        if os.path.getsize(font_filename) < 1000000:
            os.remove(font_filename)
        else:
            return font_filename # 檔案正常，直接回傳
    
    # 開始下載
    try:
        with st.spinner("正在下載中文字型資源 (首次需時約 10 秒)..."):
            response = requests.get(font_url, timeout=30)
            if response.status_code == 200:
                with open(font_filename, "wb") as f:
                    f.write(response.content)
                return font_filename
            else:
                st.warning("字型下載連線失敗，文字雲將無法顯示中文。")
                return None
    except Exception as e:
        st.warning(f"字型下載錯誤: {e}")
        return None

# --- 產生文字雲 ---
def generate_wordcloud(titles_list):
    text = " ".join(titles_list)
    # 設定停用詞
    stopwords = {
        "的", "了", "在", "是", "我", "有", "和", "就", "人", "都", "一個", "上", "也", "很", "到", "說", "要", "去", "你",
        "會", "著", "沒有", "看", "好", "自己", "這", "請問", "請益", "討論", "分享", "問題", "大家", "知道", "Mobile01",
        "什麼", "怎麼", "可以", "真的", "因為", "所以", "如果", "但是", "比較", "覺得", "現在", "還是", "有沒有", "文章",
        "標題", "連結", "來源", "發布時間"
    }
    
    try:
        words = jieba.cut(text)
        filtered_words = [word for word in words if word not in stopwords and len(word) > 1]
        text_clean = " ".join(filtered_words)
        
        if not text_clean.strip(): return None 

        # 取得字型路徑
        font_path = download_font()
        
        if font_path:
            wc = WordCloud(
                font_path=font_path, # 指定中文字型
                background_color="white",
                width=800, height=400,
                max_words=80, 
                colormap="viridis",
                font_step=2,
                min_font_size=10
            ).generate(text_clean)
        else:
            # 沒字型就用預設 (會變方塊，但至少有圖)
            wc = WordCloud(
                background_color="white",
                width=800, height=400,
                max_words=80
            ).generate(text_clean)
        
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        return fig

    except Exception as e:
        print(f"文字雲繪製失敗: {e}") 
        return None

# --- 3. 搜尋函數 ---
def search_mobile01_via_google(keyword):
    if not keyword: keyword = "台北 房產"
    real_estate_terms = "預售 OR 建案 OR 房價 OR 坪數 OR 格局 OR 公寓 OR 大樓 OR 豪宅 OR 置產 OR 買房"
    search_query = f"{keyword} ({real_estate_terms}) site:mobile01.com when:1y"
    encoded_query = urllib.parse.quote(search_query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        response = requests.get(rss_url, timeout=10)
        root = ET.fromstring(response.content)
        articles = []
        items = root.findall('.//item')
        for item in items[:50]:
            title = item.find('title').text if item.find('title') is not None else "無標題"
            link = item.find('link').text if item.find('link') is not None else "#"
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            title = title.replace("- Mobile01", "").strip()
            if is_blocked_link(link): continue
            tid = get_topic_id(link)
            articles.append({"標題": title, "連結": link, "來源": "Mobile01", "發布時間": pub_date, "topic_id": tid})
        articles.sort(key=lambda x: x['topic_id'], reverse=True)
        return articles[:15] 
    except Exception as e:
        st.error(f"搜尋錯誤: {e}"); return []

def get_demo_data():
    return [{"標題": "北士科預售屋開價破百萬合理嗎？心很累", "連結": "https://www.mobile01.com/t=999"},
            {"標題": "請問 XX 建案的施工品質如何？有漏水案例嗎", "連結": "https://www.mobile01.com/t=888"},
            {"標題": "分享：終於簽約了！格局真的很棒，但價格硬", "連結": "https://www.mobile01.com/t=777"},
            {"標題": "現在進場北士科是不是高點？怕被套牢", "連結": "https://www.mobile01.com/t=666"},
            {"標題": "信義區舊公寓 vs 北士科新成屋 怎麼選？", "連結": "https://www.mobile01.com/t=555"}]

# --- 4. AI 分析 ---
def analyze_with_gemini(df, use_fake=False):
    current_key = st.session_state.valid_api_key
    is_simulated = use_fake or (not current_key)

    if is_simulated:
        time.sleep(1)
        fake_summary = f"【模擬快報】針對本次搜尋結果，整體市場氛圍偏向觀望與焦慮。網友討論焦點集中在「價格過高」與「建商品牌信任度」。部分討論提及「施工品質」與「漏水」疑慮，顯示買方對風險意識提高。"
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
        
        請執行兩項任務：
        任務一：撰寫「市場輿情快報」(約 3-5 句話)。綜合分析這些標題反映出的整體市場情緒、網友最關注的熱點議題。
        任務二：針對每一個標題進行詳細分析。

        請直接回傳一個 JSON 格式的資料，格式如下（不要 Markdown 標記）：
        {{
            "summary_report": "在這裡填寫你的市場輿情快報內容...",
            "details": [
                {{"sentiment": "正面/負面/中立/焦慮/觀望", "keyword": "關鍵字1, 關鍵字2"}}
            ]
        }}
        確保 "details" 列表的長度與輸入的標題數量完全一致。
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
        return df, summary_report, None, False 
        
    except Exception as e:
        return df, "", str(e), False

# --- 5. 主程式介面 ---
st.title("🏠 房市輿情雷達 + AI 洞察") 

if 'data' not in st.session_state: st.session_state.data = []
if 'analyzed_data' not in st.session_state: st.session_state.analyzed_data = None
if 'summary_report' not in st.session_state: st.session_state.summary_report = ""

st.write("### 🔍 輿情關鍵字搜尋")
col_input, col_btn = st.columns([3, 1])
with col_input:
    keyword = st.text_input("輸入關鍵字 (例如：北士科、預售屋、某某建案)", "北士科")
with col_btn:
    st.write(""); st.write("")
    if st.button("🚀 搜尋最新話題", type="primary"):
        with st.spinner(f'正在蒐集關於「{keyword}」的最新討論...'):
            st.session_state.data = search_mobile01_via_google(keyword)
            st.session_state.analyzed_data = None
            st.session_state.summary_report = ""
            if not st.session_state.data: st.warning(f"找不到相關討論。")

if st.button("📂 載入範例資料 (Demo)", help="搜尋不到時使用"):
    st.session_state.data = get_demo_data()
    st.session_state.analyzed_data = None 
    st.success("已載入模擬數據！")

# --- 6. 顯示內容區 ---
if st.session_state.data:
    df = pd.DataFrame(st.session_state.data)
    st.divider()
    
    tab1, tab2 = st.tabs(["📊 AI 洞察報告 & 文字雲", "📋 原始話題列表"])
    
    with tab2: 
        st.write(f"共蒐集 {len(df)} 則最新話題")
        st.dataframe(df[['標題', '連結']], 
                     column_config={"連結": st.column_config.LinkColumn("文章連結")},
                     use_container_width=True)
        st.info("💡 請切換到「AI 洞察報告」分頁進行分析")

    with tab1: 
        st.write("### 🧠 AI 輿情分析中心")
        
        if st.session_state.analyzed_data is None: 
            if st.button("🤖 啟動 AI 全面解讀 (包含文字雲)", type="primary"):
                with st.spinner("AI 正在閱讀標題、產生摘要並繪製文字雲..."):
                    result_df, summary, error, is_sim = analyze_with_gemini(df, use_fake=force_demo_ai)
                    st.session_state.analyzed_data = result_df
                    st.session_state.summary_report = summary
                    st.session_state.is_simulated = is_sim
                    st.session_state.error_msg = error
                    st.rerun()
        
        if st.session_state.analyzed_data is not None:
            if st.session_state.is_simulated:
                st.warning("⚠️ 目前為「模擬演示模式」(無 API Key)")
            else:
                st.success("✅ AI 真實分析完成")
            if st.session_state.error_msg: st.error(f"異常: {st.session_state.error_msg}")
            
            st.markdown("""---""")
            st.subheader("📝 AI 市場輿情快報")
            if st.session_state.summary_report:
                st.info(st.session_state.summary_report, icon="💡")
            
            st.markdown("""---""")
            col_wc, col_chart = st.columns([3, 2])
            
            with col_wc:
                st.subheader("☁️ 話題熱點文字雲")
                try:
                    wc_fig = generate_wordcloud(st.session_state.data[i]['標題'] for i in range(len(st.session_state.data)))
                    if wc_fig:
                        st.pyplot(wc_fig)
                    else:
                        st.warning("文字雲產生失敗 (可能字型下載不完全)，但不影響其他功能。")
                except Exception as wc_error:
                     st.warning(f"文字雲暫時無法顯示: {wc_error}")

            with col_chart:
                st.subheader("📈 情緒分佈指標")
                st.bar_chart(st.session_state.analyzed_data['AI情緒'].value_counts())

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
