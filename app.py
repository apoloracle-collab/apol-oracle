import streamlit as st
import urllib.parse
import json
import google.generativeai as genai
import pandas as pd
import plotly.graph_objects as go
import time
import os
import hashlib
from io import BytesIO

# Firebase / Firestore Kütüphaneleri (Persistence için)
try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

# ====================== 1. VERİTABANI BAĞLANTISI (FIRESTORE) ======================
def get_db():
    if not FIREBASE_AVAILABLE:
        return None
    try:
        if "FIREBASE_SERVICE_ACCOUNT" in st.secrets:
            key_dict = json.loads(st.secrets["FIREBASE_SERVICE_ACCOUNT"])
            creds = service_account.Credentials.from_service_account_info(key_dict)
            return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except:
        return None

db = get_db()
app_id = "apol-oracle"

def get_user_id():
    """Kullanıcının IP adresinden benzersiz bir kimlik (hash) üretir."""
    try:
        user_ip = st.context.headers.get("X-Forwarded-For", "unknown_guest")
        return hashlib.md5(user_ip.encode()).hexdigest()
    except:
        return "default_user"

# ====================== 2. SİSTEM AYARLARI & CSS ======================
st.set_page_config(page_title="APOL 3.6 | Kariyer Koruma Kalkanı", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0B0E14; color: #FFFFFF; font-family: 'Inter', sans-serif; }
    .report-box { background-color: #12161F; padding: 35px; border-radius: 24px; border: 1px solid #1E2533; margin-top: 15px; line-height: 1.8; }
    .score-card { text-align: center; background: radial-gradient(circle at top, #1E2533 0%, #0B0E14 100%); padding: 50px 20px; border-radius: 30px; border: 1px solid #2A3347; margin-bottom: 30px; }
    .score-value { font-size: 8rem; font-weight: 900; margin: 0; line-height: 0.9; background: linear-gradient(180deg, #FFFFFF 0%, #4B9BFF 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .rank-badge { display: inline-block; padding: 8px 25px; border-radius: 50px; font-size: 1.4rem; font-weight: 700; letter-spacing: 4px; margin-top: 20px; text-transform: uppercase; border: 1px solid; }
    .premium-card { background: linear-gradient(135deg, #1E2533 0%, #0B0E14 100%); padding: 40px; border-radius: 24px; text-align: center; border: 2px solid #00FFC2; margin: 20px 0; }
    .motto-text { text-align: center; font-style: italic; font-size: 1.2rem; opacity: 0.8; margin-top: -10px; margin-bottom: 30px; color: #00FFC2; }
</style>
""", unsafe_allow_html=True)

# ====================== 3. VERİ YÜKLEME ======================
@st.cache_data
def load_anchor_db():
    try:
        with open("anchor_db.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {}

ANCHOR_DB = load_anchor_db()
PROFESSION_LIST = sorted(list(ANCHOR_DB.keys()))
OTHER_OPTION = "Other (Custom Entry)"
if ANCHOR_DB: PROFESSION_LIST.append(OTHER_OPTION)

# ====================== 4. KOTA YÖNETİMİ (KALICI HAFIZA) ======================
user_id = get_user_id()
MAX_FREE_QUERIES = 3  # Şenol Usta'nın isteğiyle hak 3'e çıkarıldı

if "fallback_usage" not in st.session_state:
    st.session_state.fallback_usage = 0

def get_current_usage():
    if not db:
        return st.session_state.fallback_usage
    
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("usage").document(user_id)
        doc = doc_ref.get()
        return doc.to_dict().get("count", 0) if doc.exists else 0
    except:
        return st.session_state.fallback_usage

def increment_usage():
    if not db:
        st.session_state.fallback_usage += 1
        return

    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("usage").document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.update({"count": firestore.Increment(1), "last_access": time.time()})
        else:
            doc_ref.set({"count": 1, "last_access": time.time()})
    except:
        st.session_state.fallback_usage += 1

current_usage = get_current_usage()

# ====================== 5. GEMINI API ======================
def call_gemini(prompt):
    keys = []
    if "GEMINI_API_KEYS" in st.secrets:
        s_keys = st.secrets["GEMINI_API_KEYS"]
        keys = s_keys if isinstance(s_keys, list) else [s_keys]
    
    if not keys and st.session_state.get("user_api_key"):
        keys = [st.session_state.user_api_key]
    
    if not keys: raise Exception("API Key Bulunamadı!")
    
    for key in keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("models/gemini-2.0-flash")
            return model.generate_content(prompt).text
        except: continue
    raise Exception("API Hatası")

def calculate_score(job, experience):
    anchor = ANCHOR_DB.get(job, list(ANCHOR_DB.values())[0] if ANCHOR_DB else {})
    job_lower = job.lower()
    h_bonus = 14 if any(word in job_lower for word in ["şoför", "asker", "doktor", "kurye", "hemşire"]) else 0
    score = max(28, min(98, round(55 + experience * 1.2 + h_bonus)))
    return {"score": score, "rank": anchor.get("rank", "ANALYZING"), "color": anchor.get("color", "#F1C40F"), "matrix": anchor}

# ====================== 6. ANA ARAYÜZ ======================
st.markdown("<h1 style='text-align: center; font-weight: 900;'>APOL 3.6</h1>", unsafe_allow_html=True)
st.markdown("<p class='motto-text'>\"İşini yapay zekaya değil, yapay zekayı kullanan birine kaptıracaksın.\"</p>", unsafe_allow_html=True)

st.sidebar.markdown("### 🛡️ CONTROL PANEL")
st.sidebar.text_input("YOUR API KEY (UNLIMITED)", type="password", key="user_api_key")
st.sidebar.caption(f"Kalıcı Kota Durumu: {current_usage} / {MAX_FREE_QUERIES}")

if current_usage >= MAX_FREE_QUERIES and not st.session_state.get("user_api_key"):
    st.markdown(f"""
    <div class="premium-card">
        <h2 style="color:#00FFC2;">🛡️ Cihaz Kotası Doldu</h2>
        <p>Bu cihazdan yapılan {MAX_FREE_QUERIES} ücretsiz deneme hakkı kullanılmıştır.</p>
        <p style="opacity:0.6;">Kendi Gemini API anahtarınızı girerek sınırsız kullanıma devam edebilirsiniz.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        selected_job = st.selectbox("MESLEK SEÇİN", PROFESSION_LIST)
        final_job = selected_job
    with col_in2:
        exp_in = st.slider("DENEYİM (YIL)", 0, 40, 5)
        skills_in = st.text_area("BECERİLER", placeholder="Python, liderlik, vb.", height=68)

    if st.button("KEHANETİ BAŞLAT", use_container_width=True, type="primary"):
        with st.spinner("Oracle analiz ediyor..."):
            try:
                calc = calculate_score(final_job, exp_in)
                prompt = f"Analyze career for {final_job}. Score: {calc['score']}. Professional English output."
                report = call_gemini(prompt)
                
                increment_usage()
                
                st.markdown(f'<div class="score-card"><h1 class="score-value">{calc["score"]}</h1><div class="rank-badge" style="color:{calc["color"]};">{calc["rank"]}</div></div>', unsafe_allow_html=True)
                st.markdown(f'<div class="report-box">{report}</div>', unsafe_allow_html=True)
                
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Hata: {e}")

st.markdown("---")
st.caption("EST. 2026 | @ApolOracle | Kalıcı Koruma Altyapısı Hazır")
