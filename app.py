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

# ====================== 1. KRİTİK KÜTÜPHANE VE PERSISTENCE KONTROLÜ ======================
# Firebase / Firestore (F5 Koruması için)
try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

# ReportLab (Profesyonel PDF Üretimi için)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# ====================== 2. VERİTABANI VE KİMLİK YÖNETİMİ ======================
def get_db():
    """Firestore veritabanına güvenli bağlantı kurar."""
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
    """Kullanıcıyı IP üzerinden tanıyarak F5 yapsa bile unutulmamasını sağlar."""
    try:
        user_ip = st.context.headers.get("X-Forwarded-For", "unknown_guest")
        return hashlib.md5(user_ip.encode()).hexdigest()
    except:
        return "default_user_unique_id"

# ====================== 3. STREAMLIT AYARLARI VE FULL PREMIUM CSS ======================
st.set_page_config(page_title="APOL 3.6 | Career Protection Shield", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    /* Karargah Teması */
    .stApp { background-color: #0B0E14; color: #FFFFFF; font-family: 'Inter', sans-serif; }
    
    /* Rapor Kutusu */
    .report-box { 
        background-color: #12161F; 
        padding: 40px; 
        border-radius: 28px; 
        border: 1px solid #1E2533; 
        margin-top: 15px; 
        line-height: 1.9; 
        box-shadow: 0 15px 40px rgba(0,0,0,0.5);
    }
    
    /* Dev Skor Kartı */
    .score-card { 
        text-align: center; 
        background: radial-gradient(circle at top, #1E2533 0%, #0B0E14 100%); 
        padding: 60px 20px; 
        border-radius: 35px; 
        border: 1px solid #2A3347; 
        margin-bottom: 40px; 
    }
    
    .score-value { 
        font-size: 9rem; 
        font-weight: 900; 
        margin: 0; 
        line-height: 0.8; 
        background: linear-gradient(180deg, #FFFFFF 0%, #4B9BFF 100%); 
        -webkit-background-clip: text; 
        -webkit-text-fill-color: transparent; 
        filter: drop-shadow(0 10px 20px rgba(75, 155, 255, 0.4));
    }
    
    .rank-badge { 
        display: inline-block; 
        padding: 10px 35px; 
        border-radius: 60px; 
        font-size: 1.5rem; 
        font-weight: 800; 
        letter-spacing: 5px; 
        margin-top: 25px; 
        text-transform: uppercase; 
        border: 2px solid; 
    }
    
    /* Kilit Ekranı (Premium Card) */
    .premium-card { 
        background: linear-gradient(135deg, #1E2533 0%, #0B0E14 100%); 
        padding: 50px; 
        border-radius: 30px; 
        text-align: center; 
        border: 2px solid #00FFC2; 
        margin: 30px 0; 
    }
    
    /* Motto ve Süslemeler */
    .motto-text { text-align: center; font-style: italic; font-size: 1.3rem; opacity: 0.9; margin-top: -15px; margin-bottom: 40px; color: #00FFC2; }
    .genesis-box { background-color: #12161F; padding: 30px; border-radius: 20px; border-left: 6px solid #00FFC2; margin: 30px 0; line-height: 1.7; }
    .expansion-text { text-align: center; font-size: 1rem; letter-spacing: 5px; opacity: 0.7; margin-top: -25px; margin-bottom: 25px; color: #4B9BFF; font-weight: 700; }
    
    /* Butonlar */
    .action-btn { 
        display: inline-block; 
        padding: 14px 28px; 
        margin: 8px; 
        border-radius: 14px; 
        text-decoration: none !important; 
        font-weight: 800; 
        color: white !important; 
        text-align: center; 
        border: none; 
        cursor: pointer; 
        transition: 0.3s;
    }
    .btn-x { background-color: #000000; border: 1px solid #333; }
    .btn-x:hover { background-color: #1A1A1A; transform: translateY(-3px); }
</style>
""", unsafe_allow_html=True)

# ====================== 4. VERİ YÜKLEME VE BAŞLATMA ======================
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

# Session State Hafızası
if "fallback_usage" not in st.session_state: st.session_state.fallback_usage = 0
if "last_query_time" not in st.session_state: st.session_state.last_query_time = 0

# ====================== 5. KOTA YÖNETİMİ (3 HAK + PERSISTENCE) ======================
user_id = get_user_id()
MAX_FREE_QUERIES = 3  # Usta'nın isteği üzerine 3 Hak

def get_current_usage():
    if not db: return st.session_state.fallback_usage
    try:
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

# ====================== 6. PDF ÜRETİMİ (REPORTLAB) ======================
def generate_pdf(job, sector, score, rank, report_text):
    if not PDF_AVAILABLE: return None
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Kapak Bandı
    p.setFillColorRGB(0.04, 0.05, 0.08)
    p.rect(0, height - 90, width, 90, fill=1, stroke=0)
    p.setFillColorRGB(0, 1, 0.76)
    p.setFont("Helvetica-Bold", 24)
    p.drawString(40, height - 45, "APOL 3.6 | CAREER DOSSIER")
    
    # Bilgi Alanı
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(40, height - 120, f"PROFESSION: {job.upper()}")
    p.drawString(40, height - 140, f"INDUSTRY: {sector.upper()}")
    p.drawRightString(width - 40, height - 120, f"SURVIVAL SCORE: {score}/100")
    p.drawRightString(width - 40, height - 140, f"ORACLE RANK: {rank.upper()}")
    
    p.line(40, height - 160, width - 40, height - 160)
    
    # Metin Akışı
    p.setFont("Helvetica", 10)
    y = height - 190
    clean_report = report_text.replace('***', '• ').replace('**', '')
    for line in clean_report.split('\n'):
        if not line.strip(): y -= 10; continue
        if y < 60: p.showPage(); y = height - 60; p.setFont("Helvetica", 10)
        wrapped = simpleSplit(line, "Helvetica", 10, width - 80)
        for wline in wrapped:
            p.drawString(40, y, wline)
            y -= 14
        y -= 5
    p.save(); buffer.seek(0)
    return buffer

# ====================== 7. GEMINI API VE PUANLAMA ======================
def call_gemini(prompt):
    keys = []
    if "GEMINI_API_KEYS" in st.secrets:
        s_keys = st.secrets["GEMINI_API_KEYS"]
        keys = s_keys if isinstance(s_keys, list) else [s_keys]
    
    if st.session_state.get("user_api_key"): keys = [st.session_state.user_api_key]
    if not keys: raise Exception("API Key Bulunamadı!")
    
    for key in keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("models/gemini-3.1-flash-lite-preview")
            return model.generate_content(prompt).text
        except: continue
    raise Exception("API Hatası")

def calculate_oracle_score(job, experience, is_custom):
    anchor = ANCHOR_DB.get(job, list(ANCHOR_DB.values())[0] if ANCHOR_DB else {})
    job_lower = job.lower()
    
    # Şenol Usta'nın Meşhur Bonusları
    high_touch = ["driver", "nurse", "officer", "chef", "captain", "soldier", "police", "surgeon", "athlete", "courier", "doctor"]
    legal_roles = ["lawyer", "accountant", "cpa", "doctor", "judge", "attorney"]
    
    h_bonus = 14 if any(word in job_lower for word in high_touch) else 0
    l_bonus = 12 if any(word in job_lower for word in legal_roles) else 0
    
    weighted = (anchor.get("zombie_risk",0)*-20 + anchor.get("abyss_risk",0)*-18 + anchor.get("hybrid_fit",0)*25 + 
                anchor.get("captain_fit",0)*22 + anchor.get("cyber_oracle_fit",0)*18 + anchor.get("new_genesis_fit",0)*25 + h_bonus + l_bonus)
    
    score = max(28, min(98, round(weighted + 5.0 + min(experience * 1.1, 9))))
    return {"score": score, "rank": anchor.get("rank", "EVALUATING"), "color": anchor.get("color", "#F1C40F"), "matrix": anchor}

# ====================== 8. ANA ARAYÜZ (LOGO VE GÖVDE) ======================
col_logo1, col_logo2, col_logo3 = st.columns([1, 1.2, 1])
with col_logo2:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)

st.markdown("<h1 style='text-align: center; letter-spacing: 10px; font-weight: 900;'>APOL 3.6</h1>", unsafe_allow_html=True)
st.markdown("<p class='expansion-text'>AI POLICY ORACLE LABS</p>", unsafe_allow_html=True)
st.markdown("<p class='motto-text'>\"AI won't replace you. Someone using AI will.\"</p>", unsafe_allow_html=True)

# Yan Panel
st.sidebar.markdown("### 🛡️ CONTROL PANEL")
st.sidebar.text_input("YOUR API KEY", type="password", key="user_api_key")
st.sidebar.markdown("<a href='https://aistudio.google.com/app/apikey' target='_blank' style='color:#00FFC2; font-size:0.8rem;'>🔑 Get FREE API Key</a>", unsafe_allow_html=True)
st.sidebar.caption(f"Cihaz Kotası: {current_usage} / {MAX_FREE_QUERIES}")

tab_oracle, tab_roadmap = st.tabs(["🔮 THE ORACLE", "🗺️ ROADMAP"])

with tab_oracle:
    if current_usage >= MAX_FREE_QUERIES and not st.session_state.get("user_api_key"):
        # KİLİT EKRANI
        st.markdown(f"""
        <div class="premium-card">
            <h2 style="color:#00FFC2;">🛡️ Cihaz Kotası Doldu</h2>
            <p>Ücretsiz hakkınız tamamlanmıştır ({MAX_FREE_QUERIES}/{MAX_FREE_QUERIES}).</p>
            <p style="opacity:0.8;">F5 yapmak hakkınızı sıfırlamaz. Devam etmek için kendi Gemini API anahtarınızı giriniz.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        col_in1, col_in2 = st.columns(2)
        with col_in1:
            selected = st.selectbox("SELECT PROFESSION", PROFESSION_LIST)
            if selected == OTHER_OPTION:
                final_job = st.text_input("Enter Profession")
                final_sector = st.text_input("Enter Industry")
                is_custom = True
            else:
                final_job, final_sector, is_custom = selected, ANCHOR_DB[selected]["sector"], False
                st.info(f"📍 Industry: **{final_sector}**")
        with col_in2:
            exp_in = st.slider("EXPERIENCE (YEARS)", 0, 40, 5)
            skills_in = st.text_area("KEY SKILLS", height=68)

        if st.button("EXECUTE PROPHECY", use_container_width=True, type="primary"):
            elapsed = time.time() - st.session_state.last_query_time
            if elapsed < 25 and not st.session_state.get("user_api_key"):
                st.warning(f"⏳ Soğuma süresi: {int(25 - elapsed)} saniye.")
            elif final_job and final_sector:
                with st.spinner("Oracle analiz ediyor..."):
                    try:
                        calc = calculate_oracle_score(final_job, exp_in, is_custom)
                        prompt = f"Analyze career for {final_job}. Score: {calc['score']}. Use headers: 🚨 MARKET PULSE, 🛡️ PROTECTION SHIELD, ⚔️ HUMAN FORTRESS, 🔮 ASCENSION ROADMAP. English only."
                        report = call_gemini(prompt)
                        increment_usage()
                        st.session_state.last_query_time = time.time()
                        st.session_state.last_calc, st.session_state.last_report = calc, report
                        st.session_state.last_job, st.session_state.last_sector = final_job, final_sector
                        st.rerun()
                    except Exception as e: st.error(f"Hata: {e}")

    # Sonuçların Görüntülenmesi
    if "last_report" in st.session_state:
        calc, report = st.session_state.last_calc, st.session_state.last_report
        job, sector = st.session_state.last_job, st.session_state.last_sector
        
        st.markdown(f'<div class="score-card"><h1 class="score-value">{calc["score"]}</h1><div class="rank-badge" style="color:{calc["color"]}; border-color:{calc["color"]}88;">{calc["rank"]}</div></div>', unsafe_allow_html=True)
        
        col_res1, col_res2 = st.columns([1.8, 1])
        with col_res1: st.markdown(f'<div class="report-box">{report}</div>', unsafe_allow_html=True)
        with col_res2:
            # Radar Grafiği
            m = {k: v*100 for k,v in calc['matrix'].items() if k.endswith("_risk") or k.endswith("_fit")}
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(r=list(m.values()), theta=list(m.keys()), fill='toself', line_color=calc['color']))
            fig.update_layout(polar=dict(radialaxis=dict(visible=False)), template="plotly_dark", margin=dict(l=25,r=25,t=25,b=25), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("<div style='text-align: center; margin-top: 30px;'>", unsafe_allow_html=True)
        st.download_button(label="📄 DOWNLOAD EXECUTIVE DOSSIER (PDF)", data=generate_pdf(job, sector, calc['score'], calc['rank'], report), file_name=f"APOL_Report_{job}.pdf", mime="application/pdf")
        x_tweet = f"APOL 3.6 Career Protection Score for {job}: {calc['score']}/100! @ApolOracle #APOL"
        st.markdown(f'<a href="https://twitter.com/intent/tweet?text={urllib.parse.quote(x_tweet)}" target="_blank" class="action-btn btn-x">𝕏 SHARE ON X</a>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # 🛡️ THE GENESIS (HAKKIMIZDA)
    st.markdown("---")
    st.markdown("""
    <div class="genesis-box">
        <h3 style="color: #00FFC2; margin-top: 0;">🛡️ The Genesis: Why APOL?</h3>
        <p>APOL was born from the world of a 19-year-old, shattered by his father's sudden unemployment. I personally witnessed the impossibility of finding a job after a certain age, the silence in the kitchen, and the harsh reality of money on human dignity.</p>
        <p>I saw how unemployment and financial anxiety can devastate a person's psychology and a family's peace. APOL is the first step taken to avoid being without a compass in this storm. My goal is to help you draw your own roadmap by recognizing the risks of professions against AI and automation today.</p>
        <p style="font-style: italic; opacity: 0.8; border-top: 1px solid #1E2533; padding-top: 10px;">
            "Because I believe with all my heart: You won't lose your job to AI, but to someone who uses AI."
        </p>
    </div>
    """, unsafe_allow_html=True)

    # DESTEK BÖLÜMÜ
    st.markdown("<div style='text-align: center;'><h3 style='color: #00FFC2;'>⚡ FUEL THE ORACLE</h3></div>", unsafe_allow_html=True)
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1: st.caption("🟣 SOLANA"); st.code("7ptaMAHS6GZkJEAdeQv978gzdRCPMyor3wCxs5vxxYra", language="text")
    with col_c2: st.caption("🔵 BASE / ETH"); st.code("0x9C16DF26c08e31cB0Aa2A74837A2c24cD08BFDa5", language="text")
    with col_c3: st.caption("🟠 BITCOIN"); st.code("bc1q2ksa57gx7f7tt5euezyku9su972742fye0t2mt", language="text")

with tab_roadmap:
    st.markdown("### 🗺️ APOL Strategic Roadmap")
    st.info("**🚀 Phase 1:** Global Launch & Oracle Core. **📄 Phase 2:** Interview Simulator. **🌍 Phase 3:** Live Market Data Sync.")

st.markdown("---")
st.caption("EST. 2026 | @ApolOracle | Persistence Mode Active | Human Rights ❤️")
