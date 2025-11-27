import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai
import time
import json
import urllib.parse
import xml.etree.ElementTree as ET
import re

# --- 1. 設定頁面 ---
st.set_page_config(page_title="房市輿情雷達 AI 版", page_icon="🏠", layout="wide")

# --- 2. 側邊欄：設定 API Key ---
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.secrets.get("GEMINI_API_KEY", None)
    
    if not api_key:
        api_key = st.text_input("請輸入 Google Gemini API Key", type="password")
    
    target_model_name = "尚未偵測"

    if api_key:
        genai.configure(api_key=api_key)
        try:
            valid_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    valid_models.append(m.name)
            
            preferred_models = [m for m in valid_models if 'flash' in m]
            if not preferred_models:
                preferred_models = [m for m in valid_models if 'pro' in m]
            
            if preferred_models:
                target_model_name = preferred_models[0]
            elif valid_models:
                target_model_name = valid_models[0]
            else:
                target_model_name = "gemini-1.5-flash"
            
            st.success(f"✅ 連線成功 ({target_model_name})")
            
        except Exception as e:
            st.warning(f"⚠️ API Key 可能無效: {e}")
            target_model_name = "gemini-1.5-flash"

    else:
        st.warning("⚠️ 未偵測到 Key (將使用模擬模式)")
    
    st.divider()
    force_demo_ai = st.checkbox("🔧 強制使用模擬 AI 結果 (Demo用)", value=False)

# --- [修正] 改用黑名單機制 ---
# 我們只封鎖明顯不相關的版塊，其他全部放行，避免資料太少
BLOCKED_FORUM_IDS = [
    "f=214", # Toyota (汽車)
    "f=260", # Ford (汽車)
    "f=261", # Honda (汽車)
    "f=565", # 空調家電 (你提到的家電版)
    "f=168", # 生活家電
    "f=738", # 清潔家電
    "f=61",  # 手機
    "f=37",  # 相機
    "f=320", # 旅遊美食
]

def is_blocked_link(link):
    """檢查連結是否屬於黑名單版塊"""
    if not link:
        return True # 空連結視為不安全
    
    for fid in BLOCKED_FORUM_IDS:
        if fid in link:
            return True # 抓到了，是黑名單
    return False

# --- 3. 定義函數：透過 Google News 搜尋 Mobile01 ---
def search_mobile01_via_google(keyword):
    if not keyword:
        keyword = "台北 房產"
        
    # [修正] 簡化搜尋語法
    # 移除負面關鍵字（如 -食記），避免 Google 找不到結果
    # 只保留最核心的房地產關鍵字，確保命中率
    real_estate_terms = "預售 OR 建案 OR 房價 OR 坪數 OR 格局 OR 公寓 OR 大樓 OR 豪宅 OR 置產 OR 買房"
    
    # 組合搜尋語法
    search_query = f"{keyword} ({real_estate_terms}) site:mobile01.com"
    
    encoded_query = urllib.parse.quote(search_query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    try:
        response = requests.get(rss_url, timeout=10)
        root = ET.fromstring(response.content)
        articles = []
        items = root.findall('.//item')
        
        # 抓取前 30 筆來過濾
        for item in items[:30]:
            title_elem = item.find('title')
            link_elem = item.find('link')
            pub_elem = item.find('pubDate')
            
            title = title_elem.text if title_elem is not None else "無標題"
            link = link_elem.text if link_elem is not None else "#"
            pub_date = pub_elem.text if pub_elem is not None else ""
            title = title.replace("- Mobile01", "").strip()
            
            # [核心過濾邏輯] 改為黑名單檢查
            if is_blocked_link(link):
                continue # 如果是汽車、家電版，跳過
            
            articles.append({
                "標題": title,
                "連結": link,
                "來源": "Mobile01",
                "發布時間": pub_date
            })
            
            if len(articles) >= 10:
                break
            
        return articles
    except Exception as e:
        st.error(f"搜尋發生錯誤: {e}")
        return []

def get_demo_data():
    return [
        {"標題": "大安區預售屋開價破百萬合理嗎？最近看的心很累", "連結": "https://www.mobile01.com/topicdetail.php?f=356&t=123456", "來源": "Demo"},
        {"標題": "請問 XX 建案的施工品質如何？聽說之前有漏水案例", "連結": "https://www.mobile01.com/topicdetail.php?f=356&t=123457", "來源": "Demo"},
        {"標題": "分享：終於簽約了！推薦大家去看這間，格局真的很棒", "連結": "https://www.mobile01.com/topicdetail.php?f=356&t=123458", "來源": "Demo"},
        {"標題": "現在進場是不是高點？想買房自住但怕被套牢", "連結": "https://www.mobile01.com/topicdetail.php?f=356&t=123459", "來源": "Demo"},
        {"標題": "信義區舊公寓 vs 新北重劃區新成屋 怎麼選？", "連結": "https://www.mobile01.com/topicdetail.php?f=356&t=123460", "來源": "Demo"},
    ]

# --- 4. 定義函數：AI 分析 ---
def analyze_with_gemini(df, use_fake=False):
    is_simulated = use_fake or (not api_key)

    if is_simulated:
        time.sleep(1) 
        demo_sentiments = ["焦慮", "負面", "正面", "觀望", "中立"]
        demo_keywords = ["價格過高, CP值低", "漏水, 施工品質", "格局方正, 採光好", "升息, 房市高點", "老屋翻修, 重劃區"]
        
        while len(demo_sentiments) < len(df):
            demo_sentiments.extend(demo_sentiments)
            demo_keywords.extend(demo_keywords)
            
        df['AI情緒'] = demo_sentiments[:len(df)]
        df['關鍵重點'] = demo_keywords[:len(df)]
        return df, None, True 
        
    clean_model_name = target_model_name.replace("models/", "")
    model = genai.GenerativeModel(clean_model_name)
    
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
        
        while len(sentiments) < len(df):
            sentiments.append("未知")
            keywords.append("無")
            
        df['AI情緒'] = sentiments[:len(df)]
        df['關鍵重點'] = keywords[:len(df)]
        return df, None, False 
        
    except Exception as e:
        error_msg = str(e)
        df['AI情緒'] = "連線失敗"
        df['關鍵重點'] = "API Error"
        return df, error_msg, False

# --- 5. 主程式介面 ---
st.title("🏠 房市輿情雷達 + AI 分析")

if 'data' not in st.session_state:
    st.session_state.data = []

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
                # 如果還是找不到，這次顯示更溫和的提示
                st.warning(f"Google 搜尋結果較少，請嘗試縮短關鍵字（例如：將『大安區預售屋』改為『大安區』）。")

if st.button("📂 載入測試資料 (Demo Mode)", help="如果搜尋壞掉可以用這個"):
    st.session_state.data = get_demo_data()
    st.success("已載入模擬數據！")

if st.session_state.data:
    df = pd.DataFrame(st.session_state.data)
    
    st.divider()
    st.write(f"### 📋 搜尋結果: {len(df)} 筆 (排除車版、家電版)")
    
    display_col1, display_col2 = st.columns([3, 1])
    
    with display_col1:
        st.dataframe(
            df[['標題', '連結']], 
            column_config={
                "連結": st.column_config.LinkColumn("文章連結") 
            },
            use_container_width=True
        )
    
    with display_col2:
        st.info("💡 取得資料後，請點擊下方按鈕進行 AI 解讀")
        
        if st.button("🤖 AI 情緒分析"):
            with st.spinner("AI 正在閱讀標題並分析情緒..."):
                result, error, is_sim = analyze_with_gemini(df, use_fake=force_demo_ai)
                st.session_state.analyzed_data = result
                st.session_state.is_simulated = is_sim 
                if error:
                    st.session_state.error_msg = error
                else:
                    st.session_state.error_msg = None
                st.rerun()

    if 'analyzed_data' in st.session_state:
        st.divider()
        st.subheader("📊 AI 洞察報告")
        
        if st.session_state.get('is_simulated'):
            st.warning("⚠️ 注意：目前未輸入 API Key，以下為「模擬數據」範例。")
        else:
            st.success(f"✅ 以下為 Gemini 真實分析結果 ({target_model_name})")

        if st.session_state.get('error_msg'):
            st.error(f"AI 連線異常: {st.session_state.error_msg}")

        result_df = st.session_state.analyzed_data
        
        if 'AI情緒' in result_df.columns:
            st.dataframe(
                result_df[['連結', '標題', 'AI情緒', '關鍵重點']], 
                column_config={
                    "連結": st.column_config.LinkColumn("文章連結"), 
                    "AI情緒": st.column_config.TextColumn("情緒"),
                },
                use_container_width=True
            )
            st.write("#### 情緒分佈")
            st.bar_chart(result_df['AI情緒'].value_counts())
        else:
            st.error("資料格式異常")
