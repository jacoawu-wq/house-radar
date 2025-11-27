import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import google.generativeai as genai
import time
import json

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

# --- 4. 定義函數：AI 分析 ---
def analyze_with_gemini(df, use_fake=False):
    # 模擬模式或無 Key 模式
    if use_fake or not api_key:
        time.sleep(1) 
        st.toast("使用模擬 AI 結果...")
        
        # 這裡改用最簡單的寫法
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
        
        # 補齊長度
        while len(demo_sentiments) < len(df):
            demo_sentiments.extend(demo_sentiments)
            demo_keywords.extend(demo_keywords)
            
        df['AI情緒'] = demo_sentiments[:len(df)]
        df['關鍵重點'] = demo_keywords[:len(df)]
        
        return df, None 
        
    # 真實 AI 模式
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
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        
        try:
            result_json = json.loads(clean_text)
        except:
            start = clean_text.find('[')
            end = clean_text.rfind(']') + 1
            result_json = json.loads(clean_text[start:end])

        # 這裡就是原本報錯的地方，我把它改成分行寫，絕對安全
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

# 按鈕區
col1, col2 = st.columns([1, 4])

with col1:
    if st.button("🔄 抓取 Mobile01"):
        with st.spinner('連線中...'):
            st.session_state.data = scrape_mobile01_taipei()
            if not st.session_state.data:
                st.warning("⚠️ 抓不到資料，請用測試按鈕")

with col2:
    if st.button("📂 載入測試資料 (Demo Mode)"):
        st.session_state.data = get_demo_data()
        st.success("已載入模擬數據！")

# --- 6. 顯示內容區 ---

if st.session_state.data:
    df = pd.DataFrame(st.session_state.data)
    
    st.divider()
    st.write(f"### 📋 監控列表 (共 {len(df)} 筆)")
    
    display_col1, display_col2 = st.columns([3, 1])
    
    with display_col1:
        st.dataframe(
            df[['標題', '連結']], 
            column_config={"連結": st.column_config.LinkColumn()},
            use_container_width=True
        )
    
    with display_col2:
        st.info("💡 準備好後點擊下方按鈕")
        
        if st.button("🤖 開始 AI 分析", type="primary"):
            with st.spinner("AI 正在閱讀中..."):
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
            st.error(f"AI 連線發生狀況，已顯示預設值。錯誤原因: {st.session_state.error_msg}")
            st.info("💡 提示：您可以勾選左側側邊欄的「強制使用模擬 AI 結果」來避開此問題。")

        result_df = st.session_state.analyzed_data
        if 'AI情緒' in result_df.columns:
            st.dataframe(
                result_df[['標題', 'AI情緒', '關鍵重點']],
                use_container_width=True
            )
            
            st.write("#### 情緒分佈")
            st.bar_chart(result_df['AI情緒'].value_counts())
        else:
            st.error("資料格式異常，無法顯示分析結果。")

else:
    st.info("👈 請點擊上方按鈕開始")
