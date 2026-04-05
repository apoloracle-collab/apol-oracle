import streamlit as st
import urllib.parse
import json
import google.generativeai as genai
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import os
from io import BytesIO

# ReportLab Kütüphaneleri (PDF üretimi için)
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

# ====================== STREAMLIT AYARLARI & CSS ======================
st.set_page_config(page_title="APOL 3.6 | Career Protection Shield", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0B0E14; color: #FFFFFF; font-family: 'Inter', sans-serif; }
    .report-box { background-color: #12161F; padding: 35px; border-radius: 24px; border: 1px solid #1E2533; margin-top: 15px; line-height: 1.8; }
    .score-card { text-align: center; background: radial-gradient(circle at top, #1E2533 0%, #0B0E14 100%); padding: 50px 20px; border-radius: 30px; border: 1px solid #2A3347; margin-bottom: 30px; }
    .score-value { font-size: 8rem; font-weight: 900; margin: 0; line-height: 0.9; background: linear-gradient(180deg, #FFFFFF 0%, #4B9BFF 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .rank-badge { display: inline-block; padding: 8px 25px; border-radius: 50px; font-size: 1.4rem; font-weight: 700; letter-spacing: 4px; margin-top: 20px; text-transform: uppercase; border: 1px solid; }
    .action-btn { display: inline-block; padding: 12px 24px; margin: 5px; border-radius: 12px; text-decoration: none !important; font-weight: 800; color: white !important; transition: all 0.3s ease; text-align: center; border: none; cursor: pointer; }
    .btn-x { background-color: #000000; border: 1px solid #333; }
    .premium-card { background: linear-gradient(135deg, #1E2533 0%, #0B0E14 100%); padding: 40px; border-radius: 24px; text-align: center; border: 2px solid #00FFC2; margin: 20px 0; }
    .motto-text { text-align: center; font-style: italic; font-size: 1.2rem; opacity: 0.8; margin-top: -10px; margin-bottom: 30px; color: #00FFC2; }
    .genesis-box { background-color: #12161F; padding: 25px; border-radius: 15px; border-left: 5px solid #00FFC2; margin: 20px 0; line-height: 1.6; }
    .expansion-text { text-align: center; font-size: 0.9rem; letter-spacing: 4px; opacity: 0.7; margin-top: -20px; margin-bottom: 20px; color: #4B9BFF; font-weight: 600; }
    .footer-link { color: #4B9BFF; text-decoration: none; font-size: 0.85rem; margin: 0 10px; opacity: 0.6; }
    .footer-link:hover { opacity: 1; color: #00FFC2; }
    .api-link { color: #00FFC2; font-size: 0.85rem; text-decoration: none; display: block; margin-top: -10px; margin-bottom: 10px; }
    .api-link:hover { text-decoration: underline; }
</style>
""", unsafe_allow_html=True)

# ====================== VERİ TABANI & BAŞLATMA ======================
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

if "query_count" not in st.session_state: st.session_state.query_count = 0
if "last_query_time" not in st.session_state: st.session_state.last_query_time = 0
MAX_FREE_QUERIES = 2
COOLDOWN_TIME = 25

# ====================== GEMINI API BAĞLANTISI ======================
def call_gemini(prompt, temperature=0.2):
    keys = []
    try:
        if "GEMINI_API_KEYS" in st.secrets:
            s_keys = st.secrets["GEMINI_API_KEYS"]
            keys = s_keys if isinstance(s_keys, list) else [s_keys]
    except: pass
    
    if not keys and st.session_state.get("user_api_key"):
        keys = [st.session_state.user_api_key]
    
    if not keys: raise Exception("API Key not found!")
    
    for key in keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("models/gemini-3.1-flash-lite-preview")
            return model.generate_content(prompt).text
        except: continue
    raise Exception("API Limit reached. Try again later.")

# ====================== PUANLAMA MOTORU ======================
def calculate_score(job, experience, is_custom):
    if is_custom:
        anchor = {
            "zombie_risk": 0.10, "abyss_risk": 0.10, "hybrid_fit": 0.70, 
            "captain_fit": 0.60, "cyber_oracle_fit": 0.50, "new_genesis_fit": 0.40,
            "rank": "EVALUATING", "color": "#95A5A6"
        }
    else:
        anchor = ANCHOR_DB.get(job, list(ANCHOR_DB.values())[0] if ANCHOR_DB else {})
        
    job_lower = job.lower()
    
    # Mimarın Özel Dokunuşları
    high_touch = ["driver", "courier", "officer", "nurse", "doctor", "guard", "athlete", "chef", "teacher", "surgeon", "dentist", "psychologist", "veterinarian"]
    legal_roles = ["accountant", "lawyer", "doctor", "officer", "cpa", "judge", "attorney"]
    
    h_bonus = 14 if any(word in job_lower for word in high_touch) else 0
    l_bonus = 12 if any(word in job_lower for word in legal_roles) else 0
    
    weighted = (anchor.get("zombie_risk",0)*-20 + anchor.get("abyss_risk",0)*-18 + anchor.get("hybrid_fit",0)*25 + 
                anchor.get("captain_fit",0)*22 + anchor.get("cyber_oracle_fit",0)*18 + anchor.get("new_genesis_fit",0)*25 + h_bonus + l_bonus)
    
    score = max(28, min(98, round(weighted + 5.0 + min(experience * 1.1, 9))))
    
    final_rank = anchor.get("rank", "EVALUATING")
    final_color = anchor.get("color", "#F1C40F")
    
    if is_custom:
        if score < 45: 
            final_rank = "ZOMBIE"
            final_color = "#7F8C8D"
        elif score < 55: 
            final_rank = "THE ABYSS"
            final_color = "#E67E22"
        elif score < 75: 
            final_rank = "HYBRID"
            final_color = "#F1C40F"
        elif score < 85: 
            final_rank = "CAPTAIN"
            final_color = "#2ECC71"
        else: 
            final_rank = "CYBER-ORACLE"
            final_color = "#9B59B6"

    return {"score": score, "rank": final_rank, "color": final_color, "matrix": anchor}

# ====================== PDF ÜRETİMİ ======================
def generate_pdf(job, sector, score, rank, report_text):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    c.setFillColorRGB(0.04, 0.05, 0.08)
    c.rect(0, height - 90, width, 90, fill=1, stroke=0)
    c.setFillColorRGB(0, 1, 0.76)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(40, height - 45, "APOL 3.6 | CAREER DOSSIER")
    
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height - 120, f"PROFESSION: {job.upper()}")
    c.drawString(40, height - 140, f"INDUSTRY: {sector.upper()}")
    c.drawString(width - 220, height - 120, f"SURVIVAL SCORE: {score}/100")
    c.drawString(width - 220, height - 140, f"ORACLE RANK: {rank.upper()}")
    
    c.line(40, height - 160, width - 40, height - 160)

    clean_report = report_text.encode('latin-1', 'ignore').decode('latin-1').replace('***', '• ').replace('**', '')
    
    c.setFont("Helvetica", 10)
    y = height - 190
    
    for line in clean_report.split('\n'):
        line = line.strip()
        if not line:
            y -= 10
            continue
        if y < 60:
            c.showPage()
            y = height - 60
            c.setFont("Helvetica", 10)
            
        if line.isupper() or "MARKET PULSE" in line or "SHIELD" in line or "FORTRESS" in line or "ROADMAP" in line:
            c.setFont("Helvetica-Bold", 10)
        else:
            c.setFont("Helvetica", 10)

        wrapped = simpleSplit(line, "Helvetica", 10, width - 80)
        for wline in wrapped:
            c.drawString(40, y, wline)
            y -= 14
        y -= 5
        
    c.save()
    buffer.seek(0)
    return buffer

# ====================== LOGO & BAŞLIK ======================
col_logo1, col_logo2, col_logo3 = st.columns([1, 1, 1])
with col_logo2:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)

st.markdown("<h1 style='text-align: center; letter-spacing: 8px; font-weight: 900;'>APOL 3.6</h1>", unsafe_allow_html=True)
st.markdown("<p class='expansion-text'>AI POLICY ORACLE LABS</p>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; opacity: 0.4; margin-bottom: 5px;'>CAREER PROTECTION SHIELD | GLOBAL EDITION</p>", unsafe_allow_html=True)
st.markdown("<p class='motto-text'>\"AI won't replace you. Someone using AI will.\"</p>", unsafe_allow_html=True)

# YAN MENÜ (SIDEBAR)
st.sidebar.markdown("### 🛡️ CONTROL PANEL")
st.sidebar.text_input("YOUR API KEY", type="password", key="user_api_key", help="Enter your Google Gemini API key to unlock unlimited mode.")
st.sidebar.markdown("<a href='https://aistudio.google.com/app/apikey' target='_blank' class='api-link'>🔑 Get your FREE API Key here</a>", unsafe_allow_html=True)
st.sidebar.caption(f"Free Queries: {st.session_state.query_count} / {MAX_FREE_QUERIES}")

# SEKMELER (TABS)
tab_oracle, tab_roadmap = st.tabs(["🔮 THE ORACLE", "🗺️ ROADMAP"])

with tab_oracle:
    if st.session_state.query_count >= MAX_FREE_QUERIES and not st.session_state.get("user_api_key"):
        # KİLİT EKRANI
        st.markdown(f"""
        <div class="premium-card">
            <h2 style="color:#00FFC2;">🛡️ API Key Required</h2>
            <p>Your free credits have expired ({MAX_FREE_QUERIES}/{MAX_FREE_QUERIES}).</p>
            <p style="opacity:0.8; font-size:1rem; margin-bottom: 0;">To continue using the Oracle, please enter your own Gemini API Key in the sidebar control panel.</p>
            <p style="opacity:0.6; font-size:0.9rem; margin-top: 5px;">(Don't have one? <a href="https://aistudio.google.com/app/apikey" target="_blank" style="color:#00FFC2;">Click here to get it for free</a>)</p>
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
            
            if is_custom and (not final_job.strip() or not final_sector.strip() or len(skills_in.strip()) < 3):
                st.error("🚨 PROTOCOL ERROR: Please fill in all custom fields (Profession, Industry, Skills) to execute the prophecy.")
            elif elapsed < COOLDOWN_TIME and not st.session_state.get("user_api_key"):
                st.warning(f"⏳ Cooling down. Wait {int(COOLDOWN_TIME - elapsed)}s.")
            elif final_job and final_sector:
                with st.spinner("Oracle analyzing..."):
                    calc = calculate_score(final_job, exp_in, is_custom)
                    
                    # --- ŞENOL USTA'NIN GİZLİ ESPRİ PROMPTU BURAYA EKLENDİ ---
                    prompt = f"""
                    Analyze the career protection for Profession: '{final_job}' in Industry: '{final_sector}' with Skills: '{skills_in}'. Score: {calc['score']}. 
                    
                    CRITICAL INSTRUCTION:
                    If the profession, industry, or skills seem completely fictional, absurd, sci-fi, or fantasy (e.g., 'Galactic Tomato Hunter', 'Telepathic Cat Translator'), YOU MUST start your response with a fun, witty introductory paragraph IN ENGLISH acknowledging this. For example: "Wow, I didn't know this job existed on Earth! Are we operating in a parallel universe? If so, let's analyze your otherworldly skills."
                    After this brief humorous intro, proceed with the serious analysis as if it were a real Wall Street asset. 
                    If the job is a normal, real-world job, DO NOT include this intro.

                    Use exactly these headers: 🚨 MARKET PULSE, 🛡️ PROTECTION SHIELD, ⚔️ HUMAN FORTRESS, 🔮 ASCENSION ROADMAP. THE ENTIRE RESPONSE, INCLUDING THE HUMOROUS INTRO, MUST BE STRICTLY IN ENGLISH ONLY.
                    """
                    
                    try:
                        report = call_gemini(prompt)
                        st.session_state.query_count += 1
                        st.session_state.last_query_time = time.time()
                        st.session_state.current_calc, st.session_state.current_report = calc, report
                        st.session_state.current_job, st.session_state.current_sector = final_job, final_sector
                    except Exception as e: st.error(f"Error: {e}")

        if "current_report" in st.session_state:
            calc, report = st.session_state.current_calc, st.session_state.current_report
            job, sector = st.session_state.current_job, st.session_state.current_sector
            st.markdown(f'<div class="score-card"><h1 class="score-value">{calc["score"]}</h1><div class="rank-badge" style="color:{calc["color"]};">{calc["rank"]}</div></div>', unsafe_allow_html=True)
            col_rep1, col_rep2 = st.columns([2, 1])
            with col_rep1: st.markdown(f'<div class="report-box">{report}</div>', unsafe_allow_html=True)
            with col_rep2:
                m = {k: v*100 for k,v in calc['matrix'].items() if k.endswith("_risk") or k.endswith("_fit")}
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(r=[40,30,60,50,40,50], theta=list(m.keys()), fill='toself', name='Global Baseline', line_color='rgba(255,60,60,0.5)'))
                fig.add_trace(go.Scatterpolar(r=list(m.values()), theta=list(m.keys()), fill='toself', name=job, line_color=calc['color']))
                fig.update_layout(polar=dict(radialaxis=dict(visible=False)), template="plotly_dark", margin=dict(l=20,r=20,t=20,b=20))
                st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("<div style='text-align: center; margin-top: 20px;'>", unsafe_allow_html=True)
            st.download_button(label="📄 DOWNLOAD EXECUTIVE DOSSIER (PDF)", data=generate_pdf(job, sector, calc['score'], calc['rank'], report), file_name=f"APOL_Dossier_{job.replace(' ','_')}.pdf", mime="application/pdf", type="primary")
            st.markdown("</div>", unsafe_allow_html=True)

    # 🛡️ THE GENESIS: WHY APOL?
    st.markdown("---")
    st.markdown("""
    <div class="genesis-box">
        <h3 style="color: #00FFC2; margin-top: 0;">🛡️ The Genesis: Why APOL?</h3>
        <p>APOL was born from the world of a 19-year-old, shattered by his father's sudden unemployment. I personally witnessed the impossibility of finding a job after a certain age, the silence in the kitchen, and the harsh reality of money on human dignity.</p>
        <p>I saw how unemployment and financial anxiety can devastate a person's psychology and a family's peace. APOL is not a miraculous solution for today; it is a <b>first step taken to avoid being without a compass in this storm</b>. My goal is to help you draw your own roadmap by recognizing the risks of professions against AI and automation today. As APOL evolves into a shield built with AI, it aims to become an ecosystem that offers concrete solutions and strategic ideas against these risks in the future.</p>
        <p style="font-style: italic; opacity: 0.8; border-top: 1px solid #1E2533; padding-top: 10px;">
            "Because I believe with all my heart: You won't lose your job to AI, but to someone who uses AI."
        </p>
    </div>
    """, unsafe_allow_html=True)

    # CÜZDAN ADRESLERİ & DESTEK ÇAĞRISI
    st.markdown("""
    <div style="text-align: center; margin-bottom: 20px;">
        <h3 style="color: #00FFC2;">⚡ FUEL THE ORACLE</h3>
        <p style="opacity: 0.8; font-size: 0.95rem; max-width: 700px; margin: 0 auto;">
            APOL is a fully independent, community-driven project built to protect human careers. 
            If this tool brought you clarity and you want to help us develop the next phases 
            (like the AI Interview Simulator and Live Market Integration), consider fueling the core. 
            Every contribution keeps the servers alive and the shields upgraded.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        st.caption("🟣 SOLANA")
        st.code("7ptaMAHS6GZkJEAdeQv978gzdRCPMyor3wCxs5vxxYra", language="text")
    with col_c2:
        st.caption("🔵 ETHEREUM / BASE")
        st.code("0x9C16DF26c08e31cB0Aa2A74837A2c24cD08BFDa5", language="text")
    with col_c3:
        st.caption("🟠 BITCOIN")
        st.code("bc1q2ksa57gx7f7tt5euezyku9su972742fye0t2mt", language="text")

with tab_roadmap:
    st.markdown("### 🗺️ APOL Ascension Roadmap")
    st.info("""
    **🚀 Phase 1 (Current):** Global Launch, Core Oracle, PDF Dossiers, Advanced Metrics.
    **📄 Phase 2 (2-4 Months):** Deep Sector Analysis & AI Interview Simulator.
    **🌍 Phase 3 (4+ Months):** Live Job Market Sync & Autonomous Career Agent.
    """)
    
    # ⚖️ LEGAL & PRIVACY BÖLÜMÜ
    st.markdown("---")
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

# ====================== PROFESYONEL FOOTER ======================
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns([1, 2, 1])
with col_f2:
    st.markdown(f"""
    <div style="text-align: center; opacity: 0.5; font-size: 0.85rem;">
        <p>© 2026 AI POLICY ORACLE LABS. All rights reserved.</p>
        <p>For questions, partnerships, or sponsorships: <b style="color: #00FFC2;">apoloracle@gmail.com</b></p>
        <div style="margin-top: 10px;">
            <a href="https://twitter.com/ApolOracle" target="_blank" class="footer-link">Twitter (X)</a>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.caption("""
    <div style="text-align: center; font-size: 0.7rem; margin-top: 20px; line-height: 1.2;">
    Disclaimer: APOL 3.6 is an AI-driven career estimation tool. The results provided are based on current market trends 
    and architectural projections. These should not be considered as absolute financial or legal advice.
    </div>
    """, unsafe_allow_html=True)

st.markdown("<p style='text-align: center; opacity: 0.1; margin-top: 20px; font-size: 0.7rem;'>v3.6.0-stable</p>", unsafe_allow_html=True)