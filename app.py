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

# ====================== 1. CRITICAL LIBRARY & PERSISTENCE CHECK ======================
# Firebase / Firestore (For F5 Protection / Persistence)
try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

# ReportLab (For Professional PDF Generation)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# ====================== 2. DATABASE & IDENTITY MANAGEMENT ======================
def get_db():
    """Establishes a secure connection to the Firestore database."""
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
    """Identifies the user via IP to prevent credit reset on page refresh (F5)."""
    try:
        user_ip = st.context.headers.get("X-Forwarded-For", "unknown_guest")
        return hashlib.md5(user_ip.encode()).hexdigest()
    except:
        return "default_user_unique_id"

# ====================== 3. STREAMLIT CONFIG & FULL PREMIUM CSS ======================
st.set_page_config(page_title="APOL 3.6 | Career Protection Shield", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    /* Main Theme */
    .stApp { background-color: #0B0E14; color: #FFFFFF; font-family: 'Inter', sans-serif; }
    
    /* Report Container */
    .report-box { 
        background-color: #12161F; 
        padding: 45px; 
        border-radius: 30px; 
        border: 1px solid #1E2533; 
        margin-top: 15px; 
        line-height: 2.0; 
        box-shadow: 0 20px 50px rgba(0,0,0,0.6); 
    }
    
    /* Massive Score Card */
    .score-card { 
        text-align: center; 
        background: radial-gradient(circle at top, #1E2533 0%, #0B0E14 100%); 
        padding: 70px 20px; 
        border-radius: 40px; 
        border: 1px solid #2A3347; 
        margin-bottom: 40px; 
        position: relative;
    }
    
    .score-value { 
        font-size: 9.5rem; 
        font-weight: 900; 
        margin: 0; 
        line-height: 0.8; 
        background: linear-gradient(180deg, #FFFFFF 0%, #4B9BFF 100%); 
        -webkit-background-clip: text; 
        -webkit-text-fill-color: transparent; 
        filter: drop-shadow(0 15px 30px rgba(75, 155, 255, 0.4));
    }
    
    .rank-badge { 
        display: inline-block; 
        padding: 12px 40px; 
        border-radius: 70px; 
        font-size: 1.6rem; 
        font-weight: 800; 
        letter-spacing: 6px; 
        margin-top: 30px; 
        text-transform: uppercase; 
        border: 2px solid; 
    }
    
    /* Lock Screen Style */
    .premium-card { 
        background: linear-gradient(135deg, #1E2533 0%, #0B0E14 100%); 
        padding: 60px; 
        border-radius: 35px; 
        text-align: center; 
        border: 2px solid #00FFC2; 
        margin: 40px 0; 
        box-shadow: 0 0 60px rgba(0, 255, 194, 0.1);
    }
    
    /* Typography & Deco */
    .motto-text { text-align: center; font-style: italic; font-size: 1.4rem; opacity: 0.9; margin-top: -15px; margin-bottom: 45px; color: #00FFC2; }
    .genesis-box { background-color: #12161F; padding: 35px; border-radius: 25px; border-left: 8px solid #00FFC2; margin: 40px 0; line-height: 1.8; }
    .expansion-text { text-align: center; font-size: 1.1rem; letter-spacing: 6px; opacity: 0.8; margin-top: -30px; margin-bottom: 30px; color: #4B9BFF; font-weight: 800; }
    
    /* Action Buttons */
    .action-btn { 
        display: inline-block; 
        padding: 16px 32px; 
        margin: 10px; 
        border-radius: 16px; 
        text-decoration: none !important; 
        font-weight: 800; 
        color: white !important; 
        text-align: center; 
        border: none; 
        cursor: pointer; 
        transition: transform 0.3s, box-shadow 0.3s;
    }
    .btn-x { background-color: #000000; border: 1px solid #333; }
    .btn-x:hover { transform: translateY(-4px); box-shadow: 0 10px 20px rgba(255,255,255,0.15); }
    
    /* Tabs Customization */
    .stTabs [data-baseweb="tab-list"] { gap: 24px; justify-content: center; }
    .stTabs [data-baseweb="tab"] { height: 60px; font-weight: 700; font-size: 1.1rem; }
    .footer-link { color: #4B9BFF; text-decoration: none; font-size: 0.9rem; margin: 0 10px; opacity: 0.6; }
    .footer-link:hover { opacity: 1; color: #00FFC2; }
</style>
""", unsafe_allow_html=True)

# ====================== 4. DATABASE LOADING ======================
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

# Session State Persistence
if "fallback_usage" not in st.session_state: st.session_state.fallback_usage = 0
if "last_query_time" not in st.session_state: st.session_state.last_query_time = 0

# ====================== 5. QUOTA MANAGEMENT (3 CREDITS + PERSISTENCE) ======================
user_id = get_user_id()
MAX_FREE_QUERIES = 3 

def get_current_usage():
    """Fetches the query count from the database based on the user's fingerprint."""
    if not db: return st.session_state.fallback_usage
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("usage").document(user_id)
        doc = doc_ref.get()
        return doc.to_dict().get("count", 0) if doc.exists else 0
    except: return st.session_state.fallback_usage

def increment_usage():
    """Increments and seals the query count permanently in the database."""
    if not db:
        st.session_state.fallback_usage += 1
        return
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("usage").document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.update({"count": firestore.Increment(1), "last_access": time.time()})
        else:
            doc_ref.set({"count": 1, "last_access": time.time(), "created_at": time.time()})
    except: st.session_state.fallback_usage += 1

current_usage = get_current_usage()

# ====================== 6. PDF GENERATION ENGINE (REPORTLAB) ======================
def generate_pdf(job, sector, score, rank, report_text):
    if not PDF_AVAILABLE: return None
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Header Banner
    p.setFillColorRGB(0.04, 0.05, 0.08)
    p.rect(0, height - 90, width, 90, fill=1, stroke=0)
    p.setFillColorRGB(0, 1, 0.76)
    p.setFont("Helvetica-Bold", 24)
    p.drawString(50, height - 45, "APOL 3.6 | CAREER DOSSIER")
    
    # Metadata Area
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, height - 120, f"PROFESSION: {job.upper()}")
    p.drawString(50, height - 140, f"INDUSTRY: {sector.upper()}")
    p.drawRightString(width - 50, height - 120, f"SURVIVAL SCORE: {score}/100")
    p.drawRightString(width - 50, height - 140, f"ORACLE RANK: {rank.upper()}")
    
    p.setStrokeColorRGB(0.8, 0.8, 0.8)
    p.line(50, height - 165, width - 50, height - 165)
    
    # Text Stream
    p.setFont("Helvetica", 10.5)
    y_pos = height - 200
    clean_report = report_text.replace('***', '• ').replace('**', '').replace('* ', '• ')
    
    for line in clean_report.split('\n'):
        if not line.strip(): y_pos -= 12; continue
        if y_pos < 70: p.showPage(); y_pos = height - 70; p.setFont("Helvetica", 10.5)
        wrapped = simpleSplit(line, "Helvetica", 10.5, width - 100)
        for wline in wrapped:
            p.drawString(50, y_pos, wline)
            y_pos -= 16
        y_pos -= 6
    
    p.save(); buffer.seek(0)
    return buffer

# ====================== 7. GEMINI API & SCORING ENGINE ======================
def call_gemini(prompt):
    keys = []
    if "GEMINI_API_KEYS" in st.secrets:
        s_keys = st.secrets["GEMINI_API_KEYS"]
        keys = s_keys if isinstance(s_keys, list) else [s_keys]
    if st.session_state.get("user_api_key"): keys = [st.session_state.user_api_key]
    
    if not keys: raise Exception("API Key Missing!")
    
    for key in keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("models/gemini-3.1-flash-lite-preview")
            return model.generate_content(prompt).text
        except: continue
    raise Exception("API Error: Rate limit reached.")

def calculate_oracle_score(job, experience):
    """The master scoring engine with specific human-factor coefficients."""
    anchor = ANCHOR_DB.get(job, list(ANCHOR_DB.values())[0] if ANCHOR_DB else {})
    job_lower = job.lower()
    
    # Human Touch & Legal Responsibility Bonuses
    high_touch = ["driver", "nurse", "officer", "chef", "captain", "soldier", "police", "surgeon", "athlete", "courier", "doctor", "guard"]
    legal_roles = ["lawyer", "accountant", "cpa", "doctor", "judge", "attorney", "notary"]
    
    h_bonus = 14 if any(word in job_lower for word in high_touch) else 0
    l_bonus = 12 if any(word in job_lower for word in legal_roles) else 0
    
    weighted = (
        anchor.get("zombie_risk", 0) * -20 +
        anchor.get("abyss_risk", 0) * -18 +
        anchor.get("hybrid_fit", 0) * 25 +
        anchor.get("captain_fit", 0) * 22 +
        anchor.get("cyber_oracle_fit", 0) * 18 +
        anchor.get("new_genesis_fit", 0) * 25 +
        h_bonus + l_bonus
    )
    
    final_score = max(28, min(98, round(weighted + 5.0 + min(experience * 1.1, 9))))
    return {"score": final_score, "rank": anchor.get("rank", "ANALYZING"), "color": anchor.get("color", "#F1C40F"), "matrix": anchor}

# ====================== 8. MAIN UI (BODY) ======================
# Logo Area
col_logo1, col_logo2, col_logo3 = st.columns([1, 1.3, 1])
with col_logo2:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)

st.markdown("<h1 style='text-align: center; letter-spacing: 12px; font-weight: 900; margin-bottom: 0;'>APOL 3.6</h1>", unsafe_allow_html=True)
st.markdown("<p class='expansion-text'>AI POLICY ORACLE LABS</p>", unsafe_allow_html=True)
st.markdown("<p class='motto-text'>\"AI won't replace you. Someone using AI will.\"</p>", unsafe_allow_html=True)

# Sidebar (Control Panel)
st.sidebar.markdown("### 🛡️ CONTROL PANEL")
st.sidebar.text_input("YOUR API KEY", type="password", key="user_api_key", help="Enter your Gemini key for unlimited mode.")
st.sidebar.markdown("<a href='https://aistudio.google.com/app/apikey' target='_blank' style='color:#00FFC2; font-size:0.85rem;'>🔑 Get FREE API Key Here</a>", unsafe_allow_html=True)
st.sidebar.caption(f"Device Credits: {current_usage} / {MAX_FREE_QUERIES}")

# TABS (Oracle & Roadmap)
tab_oracle, tab_roadmap = st.tabs(["🔮 THE ORACLE", "🗺️ ROADMAP"])

with tab_oracle:
    if current_usage >= MAX_FREE_QUERIES and not st.session_state.get("user_api_key"):
        # LOCK SCREEN
        st.markdown(f"""
        <div class="premium-card">
            <h2 style="color:#00FFC2; letter-spacing: 4px;">🛡️ DEVICE LIMIT REACHED</h2>
            <p style="font-size: 1.2rem; margin-top: 15px;">Your <b>{MAX_FREE_QUERIES}</b> free trial credits for this device have been used.</p>
            <p style="opacity:0.8;">Refreshing the page will not reset this.</p>
            <div style="background: rgba(255,255,255,0.05); padding: 25px; border-radius: 20px; margin: 30px 0;">
                <p>To continue, please enter your own Gemini API key in the sidebar to re-activate the Oracle.</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Inputs (Clean English)
        col_in1, col_in2 = st.columns(2)
        with col_in1:
            selected = st.selectbox("SELECT PROFESSION", PROFESSION_LIST)
            if selected == OTHER_OPTION:
                final_job = st.text_input("Enter Profession")
                final_sector = st.text_input("Enter Industry")
            else:
                final_job = selected
                final_sector = ANCHOR_DB[selected]["sector"]
                st.info(f"📍 Industry: **{final_sector}**")
        with col_in2:
            exp_in = st.slider("EXPERIENCE (YEARS)", 0, 40, 5)
            skills_in = st.text_area("KEY SKILLS", placeholder="e.g. Leadership, Python, Crisis Management...", height=68)

        # EXECUTE BUTTON
        if st.button("EXECUTE PROPHECY", use_container_width=True, type="primary"):
            if final_job and final_sector:
                with st.spinner("Oracle is processing..."):
                    try:
                        calc = calculate_oracle_score(final_job, exp_in)
                        prompt = f"Analyze career for {final_job} in {final_sector}. Score: {calc['score']}. Use headers: 🚨 MARKET PULSE, 🛡️ PROTECTION SHIELD, ⚔️ HUMAN FORTRESS, 🔮 ASCENSION ROADMAP. Professional English only."
                        report = call_gemini(prompt)
                        
                        # Persistent credit update
                        increment_usage()
                        st.session_state.last_calc, st.session_state.last_report = calc, report
                        st.session_state.last_job, st.session_state.last_sector = final_job, final_sector
                        st.rerun()
                    except Exception as e: st.error(f"Oracle Error: {e}")

    # RESULT DISPLAY
    if "last_report" in st.session_state:
        calc, report = st.session_state.last_calc, st.session_state.last_report
        job, sector = st.session_state.last_job, st.session_state.last_sector
        
        st.markdown(f"""
            <div class="score-card">
                <p style="opacity: 0.5; letter-spacing: 7px; font-size: 1rem;">SURVIVAL SCORE</p>
                <h1 class="score-value">{calc["score"]}</h1>
                <div class="rank-badge" style="color:{calc["color"]}; border-color:{calc["color"]}88;">{calc["rank"]}</div>
            </div>
        """, unsafe_allow_html=True)
        
        col_res1, col_res2 = st.columns([1.8, 1])
        with col_res1: st.markdown(f'<div class="report-box">{report}</div>', unsafe_allow_html=True)
        with col_res2:
            # Radar Chart
            m_data = {k: v*100 for k,v in calc['matrix'].items() if k.endswith("_risk") or k.endswith("_fit")}
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(r=list(m_data.values()), theta=list(m_data.keys()), fill='toself', line_color=calc['color']))
            fig.update_layout(polar=dict(radialaxis=dict(visible=False)), template="plotly_dark", margin=dict(l=30,r=30,t=30,b=30), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("<div style='text-align: center; margin-top: 35px;'>", unsafe_allow_html=True)
        st.download_button(label="📄 DOWNLOAD EXECUTIVE DOSSIER (PDF)", data=generate_pdf(job, sector, calc['score'], calc['rank'], report), file_name=f"APOL_Report_{job}.pdf", mime="application/pdf")
        
        # ADVANCED X SHARING LOGIC
        tweet_catchphrase = {
            "THE NEW GENESIS": "I am the future. Unstoppable, essential, and ready for the 2030s! 🚀",
            "CYBER-ORACLE": "Architecting the transition. Human intelligence meets AI mastery! 🔮",
            "CAPTAIN": "Holding the line with high-stakes human expertise. Unreplaceable! ⚔️",
            "HYBRID": "Adapting and evolving. AI is my co-pilot, not my replacement! ⚖️",
            "THE ABYSS": "At the edge of transformation. Strategic pivot is in progress! 🌊",
            "ZOMBIE": "Warning: High automation risk detected. Time to upgrade the human core! 🧟"
        }.get(calc['rank'], "Analyzing the future of labor.")
        
        x_tweet = f"🛡️ APOL 3.6 Career Protection Dossier: {job}\n\n📊 Score: {calc['score']}/100\n🏆 Rank: {calc['rank']}\n\n\"{tweet_catchphrase}\"\n\nCheck your shield: apol-oracle.streamlit.app @ApolOracle #APOL #AI #FutureOfWork"
        st.markdown(f'<a href="https://twitter.com/intent/tweet?text={urllib.parse.quote(x_tweet)}" target="_blank" class="action-btn btn-x">𝕏 SHARE YOUR DESTINY ON X</a>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # THE GENESIS (ABOUT US)
    st.markdown("---")
    st.markdown("""
    <div class="genesis-box">
        <h3 style="color: #00FFC2; margin-top: 0;">🛡️ The Genesis: Why APOL?</h3>
        <p>APOL was born from the world of a 19-year-old, shattered by his father's sudden unemployment. I personally witnessed the impossibility of finding a job after a certain age, the silence in the kitchen, and the harsh reality of money on human dignity.</p>
        <p>I saw how unemployment and financial anxiety can devastate a person's psychology and a family's peace. APOL is the first step taken to avoid being without a compass in this storm. My goal is to help you draw your own roadmap by recognizing the risks of professions against AI and automation today.</p>
        <p style="font-style: italic; opacity: 0.9; border-top: 1px solid #1E2533; padding-top: 12px; color: #00FFC2;">
            "Because I believe with all my heart: You won't lose your job to AI, but to someone who uses AI."
        </p>
    </div>
    """, unsafe_allow_html=True)

    # FUEL THE ORACLE SECTION
    st.markdown("""
    <div style="text-align: center; margin-bottom: 25px;">
        <h3 style="color: #00FFC2;">⚡ FUEL THE ORACLE</h3>
        <p style="opacity: 0.8; font-size: 0.95rem; max-width: 800px; margin: 0 auto; line-height: 1.6;">
            APOL is a fully independent, community-driven project built to protect human careers. 
            If this tool brought you clarity and you want to help us develop the next phases 
            (like the AI Interview Simulator and Live Market Integration), consider fueling the core. 
            Every contribution keeps the servers alive and the shields upgraded.
        </p>
    </div>
    """, unsafe_allow_html=True)
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1: st.caption("🟣 SOLANA"); st.code("7ptaMAHS6GZkJEAdeQv978gzdRCPMyor3wCxs5vxxYra", language="text")
    with col_c2: st.caption("🔵 BASE / ETH"); st.code("0x9C16DF26c08e31cB0Aa2A74837A2c24cD08BFDa5", language="text")
    with col_c3: st.caption("🟠 BITCOIN"); st.code("bc1q2ksa57gx7f7tt5euezyku9su972742fye0t2mt", language="text")

with tab_roadmap:
    # ASCENSION ROADMAP
    st.markdown("### 🗺️ APOL Ascension Roadmap")
    st.info("""
    **🚀 Phase 1 (Current):** Global Launch, Core Oracle, PDF Dossiers, Advanced Metrics.  
    **📄 Phase 2 (2-4 Months):** Deep Sector Analysis & AI Interview Simulator.  
    **🌍 Phase 3 (4+ Months):** Live Job Market Sync & Autonomous Career Agent.
    """)
    st.markdown("---")
    # LEGAL & PRIVACY
    st.markdown("### ⚖️ Legal & Privacy")
    with st.expander("Privacy Policy"):
        st.write("""
        **Data Collection:** APOL 3.6 does not store your personal identity. We only process the profession and skills you provide to generate the temporary AI risk report.  
        **Cookies:** We use essential technical cookies to ensure the application functions correctly.  
        **Third-Party:** AI analysis is powered by Google Gemini API. Your inputs are subject to Google's Privacy Policy during processing.  
        **Contact:** For any data inquiries, contact us at apoloracle@gmail.com.
        """)
    with st.expander("Terms of Service"):
        st.write("""
        **Usage:** This tool is for educational and estimation purposes only.  
        **Liability:** AI Policy Oracle Labs and its creator are not responsible for career decisions or financial outcomes based on these estimations.  
        **Accuracy:** AI predictions are based on current market trends and can change as technology evolves rapidly.  
        **Finality:** By using this tool, you acknowledge that its output is an estimation, not a professional legal or career advice.
        """)

# ====================== PROFESSIONAL FOOTER ======================
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns([1, 2, 1])
with col_f2:
    st.markdown("""
    <div style="text-align: center; opacity: 0.6; font-size: 0.9rem;">
        <p>© 2026 AI POLICY ORACLE LABS. All rights reserved.</p>
        <p>For questions: <b style="color: #00FFC2;">apoloracle@gmail.com</b></p>
        <div style="margin-top: 15px;">
            <a href="https://twitter.com/ApolOracle" target="_blank" class="footer-link">Twitter (X)</a>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.caption("""
    <div style="text-align: center; font-size: 0.75rem; margin-top: 25px; line-height: 1.4; opacity: 0.5;">
    Disclaimer: APOL 3.6 is an AI-driven career estimation tool. Results are based on projections and should not be considered absolute financial advice.
    </div>
    """, unsafe_allow_html=True)

st.markdown("<p style='text-align: center; opacity: 0.15; margin-top: 30px; font-size: 0.75rem; letter-spacing: 3px;'>v3.6.0-stable</p>", unsafe_allow_html=True)
