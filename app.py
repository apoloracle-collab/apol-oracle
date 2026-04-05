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

# Firebase / Firestore (Persistence için)
try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

# ReportLab (PDF üretimi için)
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

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
st.set_page_config(page_title="APOL 3.6 | Career Protection Shield", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0B0E14; color: #FFFFFF; font-family: 'Inter', sans-serif; }
    .report-box { background-color: #12161F; padding: 35px; border-radius: 24px; border: 1px solid #1E2533; margin-top: 15px; line-height: 1.8; }
    .score-card { text-align: center; background: radial-gradient(circle at top, #1E2533 0%, #0B0E14 100%); padding: 50px 20px; border-radius: 30px; border: 1px solid #2A3347; margin-bottom: 30px; }
    .score-value { font-size: 8rem; font-weight: 900; margin: 0; line-height: 0.9; background: linear-gradient(180deg, #FFFFFF 0%, #4B9BFF 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .rank-badge { display: inline-block; padding: 8px 25px; border-radius: 50px; font-size: 1.4rem; font-weight: 700; letter-spacing: 4px; margin-top: 20px; text-transform: uppercase; border: 1px solid; }
    .premium-card { background: linear-gradient(135deg, #1E2533 0%, #0B0E14 100%); padding: 40px; border-radius: 24px; text-align: center; border: 2px solid #00FFC2; margin: 20px 0; }
    .motto-text { text-align: center; font-style: italic; font-size: 1.2rem; opacity: 0.8; margin-top: -10px; margin-bottom: 30px; color: #00FFC2; }
    .action-btn { display: inline-block; padding: 12px 24px; margin: 5px; border-radius: 12px; text-decoration: none !important; font-weight: 800; color: white !important; text-align: center; border: none; cursor: pointer; }
    .btn-x { background-color: #000000; border: 1px solid #333; }
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

# ====================== 4. KOTA YÖNETİMİ (PERSISTENCE) ======================
user_id = get_user_id()
MAX_FREE_QUERIES = 3 

if "fallback_usage" not in st.session_state:
    st.session_state.fallback_usage = 0

def get_current_usage():
    if not db: return st.session_state.fallback_usage
    try:
        # PATH: artifacts/{appId}/public/data/usage/{userId}
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("usage").document(user_id)
        doc = doc_ref.get()
        return doc.to_dict().get("count", 0) if doc.exists else 0
    except: return st.session_state.fallback_usage

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
    except: st.session_state.fallback_usage += 1

current_usage = get_current_usage()

# ====================== 5. PDF ÜRETİM MOTORU ======================
def generate_pdf(job, sector, score, rank, report_text):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    p.setFillColorRGB(0.04, 0.05, 0.08)
    p.rect(0, height - 90, width, 90, fill=1, stroke=0)
    p.setFillColorRGB(0, 1, 0.76)
    p.setFont("Helvetica-Bold", 24)
    p.drawString(40, height - 45, "APOL 3.6 | CAREER DOSSIER")
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(40, height - 120, f"PROFESSION: {job.upper()}")
    p.drawString(40, height - 140, f"INDUSTRY: {sector.upper()}")
    p.drawString(width - 220, height - 120, f"SCORE: {score}/100")
    p.drawString(width - 220, height - 140, f"RANK: {rank}")
    p.line(40, height - 160, width - 40, height - 160)
    y = height - 190
    p.setFont("Helvetica", 10)
    for line in report_text.replace('***', '• ').replace('**', '').split('\n'):
        if y < 60:
            p.showPage()
            y = height - 60
            p.setFont("Helvetica", 10)
        wrapped = simpleSplit(line, "Helvetica", 10, width - 80)
        for wline in wrapped:
            p.drawString(40, y, wline)
            y -= 14
        y -= 5
    p.save()
    buffer.seek(0)
    return buffer

# ====================== 6. GEMINI API & PUANLAMA ======================
def call_gemini(prompt):
    keys = st.secrets.get("GEMINI_API_KEYS", [])
    if not isinstance(keys, list): keys = [keys] if keys else []
    if not keys and st.session_state.get("user_api_key"): keys = [st.session_state.user_api_key]
    if not keys: raise Exception("API Key Error")
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
    h_bonus = 14 if any(word in job_lower for word in ["driver", "nurse", "officer", "chef", "captain", "soldier", "police"]) else 0
    l_bonus = 12 if any(word in job_lower for word in ["lawyer", "accountant", "cpa", "doctor"]) else 0
    score = max(28, min(98, round(52 + experience * 1.2 + h_bonus + l_bonus)))
    return {"score": score, "rank": anchor.get("rank", "ANALYZING"), "color": anchor.get("color", "#F1C40F"), "matrix": anchor}

# ====================== 7. ANA ARAYÜZ ======================
# Logo Alanı
col_logo1, col_logo2, col_logo3 = st.columns([1, 1, 1])
with col_logo2:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)

st.markdown("<h1 style='text-align: center; letter-spacing: 8px; font-weight: 900;'>APOL 3.6</h1>", unsafe_allow_html=True)
st.markdown("<p class='motto-text'>\"İşini yapay zekaya değil, yapay zekayı kullanan birine kaptıracaksın.\"</p>", unsafe_allow_html=True)

# Yan Panel
st.sidebar.markdown("### 🛡️ CONTROL PANEL")
st.sidebar.text_input("YOUR API KEY (UNLIMITED)", type="password", key="user_api_key")
st.sidebar.caption(f"Cihaz Kotası: {current_usage} / {MAX_FREE_QUERIES}")

# KOTA KONTROLÜ
if current_usage >= MAX_FREE_QUERIES and not st.session_state.get("user_api_key"):
    st.markdown(f"""
    <div class="premium-card">
        <h2 style="color:#00FFC2;">🛡️ Cihaz Kotası Doldu</h2>
        <p>Bu cihazdan yapılan {MAX_FREE_QUERIES} ücretsiz sorgu hakkı kullanılmıştır.</p>
        <p style="opacity:0.6;">F5 yapmak hakkınızı yenilemez. Kendi Gemini API anahtarınızı girerek sınırsız kullanıma devam edebilirsiniz.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        selected_job = st.selectbox("MESLEK SEÇİN / SELECT PROFESSION", PROFESSION_LIST)
        if selected_job == OTHER_OPTION:
            final_job = st.text_input("Enter Profession (English)")
            final_sector = st.text_input("Enter Industry (English)")
        else:
            final_job = selected_job
            final_sector = ANCHOR_DB[selected_job]["sector"]
            st.info(f"📍 Sektör: **{final_sector}**")
    with col_in2:
        exp_in = st.slider("DENEYİM / EXPERIENCE (YEARS)", 0, 40, 5)
        skills_in = st.text_area("BECERİLER / SKILLS", placeholder="e.g. Leadership, Python, Crisis Management", height=68)

    if st.button("KEHANETİ BAŞLAT / EXECUTE", use_container_width=True, type="primary"):
        with st.spinner("Oracle analiz ediyor..."):
            try:
                calc = calculate_score(final_job, exp_in)
                prompt = f"""
                Analyze the career protection for '{final_job}' in '{final_sector}'. Score: {calc['score']}. 
                Use headers: 🚨 MARKET PULSE, 🛡️ PROTECTION SHIELD, ⚔️ HUMAN FORTRESS, 🔮 ASCENSION ROADMAP. 
                Be witty and professional. English output only.
                """
                report = call_gemini(prompt)
                increment_usage()
                
                # Sonuçları Kaydet
                st.session_state.last_calc = calc
                st.session_state.last_report = report
                st.session_state.last_job = final_job
                st.session_state.last_sector = final_sector
                st.rerun()
            except Exception as e: st.error(f"Hata: {e}")

    # Sonuçların Görüntülenmesi
    if "last_report" in st.session_state:
        calc, report = st.session_state.last_calc, st.session_state.last_report
        job, sector = st.session_state.last_job, st.session_state.last_sector
        
        st.markdown(f'<div class="score-card"><h1 class="score-value">{calc["score"]}</h1><div class="rank-badge" style="color:{calc["color"]};">{calc["rank"]}</div></div>', unsafe_allow_html=True)
        
        col_res1, col_res2 = st.columns([2, 1])
        with col_res1:
            st.markdown(f'<div class="report-box">{report}</div>', unsafe_allow_html=True)
        with col_res2:
            m = {k: v*100 for k,v in calc['matrix'].items() if k.endswith("_risk") or k.endswith("_fit")}
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(r=list(m.values()), theta=list(m.keys()), fill='toself', line_color=calc['color']))
            fig.update_layout(polar=dict(radialaxis=dict(visible=False)), template="plotly_dark", margin=dict(l=20,r=20,t=20,b=20))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("<div style='text-align: center; margin-top: 20px;'>", unsafe_allow_html=True)
        st.download_button(label="📄 DOWNLOAD PDF REPORT", data=generate_pdf(job, sector, calc['score'], calc['rank'], report), file_name=f"APOL_Report_{job}.pdf", mime="application/pdf")
        
        x_text = f"APOL 3.6 Career Shield: {job} Score {calc['score']}/100! @ApolOracle #APOL"
        st.markdown(f'<a href="https://twitter.com/intent/tweet?text={urllib.parse.quote(x_text)}" target="_blank" class="action-btn btn-x">𝕏 SHARE ON X</a>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

st.caption("EST. 2026 | @ApolOracle | Kalıcı Koruma Altyapısı Aktif")
