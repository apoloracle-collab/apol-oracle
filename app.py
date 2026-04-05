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

# ====================== 1. KRİTİK KÜTÜPHANE KONTROLÜ ======================
# Firebase / Firestore (Persistence/F5 Koruması için)
try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

# ReportLab (Profesyonel PDF üretimi için)
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
    except Exception as e:
        return None

db = get_db()
app_id = "apol-oracle"

def get_user_id():
    """Kullanıcıyı IP üzerinden tanıyarak F5 yapsa bile unutulmamasını sağlar."""
    try:
        # Streamlit Cloud üzerinde gerçek IP adresini yakalar
        user_ip = st.context.headers.get("X-Forwarded-For", "unknown_guest")
        # Gizlilik için IP'yi hash'ler (parmak izine dönüştürür)
        return hashlib.md5(user_ip.encode()).hexdigest()
    except:
        return "default_user_unique_id"

# ====================== 3. SİSTEM AYARLARI VE PREMİUM TASARIM (CSS) ======================
st.set_page_config(
    page_title="APOL 3.6 | Career Protection Shield", 
    page_icon="🛡️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* Ana Arka Plan ve Yazı Tipleri */
    .stApp { 
        background-color: #0B0E14; 
        color: #FFFFFF; 
        font-family: 'Inter', sans-serif; 
    }
    
    /* Rapor Kutusu Tasarımı */
    .report-box { 
        background-color: #12161F; 
        padding: 40px; 
        border-radius: 28px; 
        border: 1px solid #1E2533; 
        margin-top: 20px; 
        line-height: 1.9; 
        box-shadow: 0 15px 45px rgba(0,0,0,0.6); 
    }
    
    /* Büyük Skor Kartı */
    .score-card { 
        text-align: center; 
        background: radial-gradient(circle at top, #1E2533 0%, #0B0E14 100%); 
        padding: 60px 20px; 
        border-radius: 35px; 
        border: 1px solid #2A3347; 
        margin-bottom: 40px; 
        position: relative;
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
        padding: 10px 30px; 
        border-radius: 60px; 
        font-size: 1.5rem; 
        font-weight: 800; 
        letter-spacing: 5px; 
        margin-top: 25px; 
        text-transform: uppercase; 
        border: 2px solid;
    }
    
    /* Kota Bitiş Kartı */
    .premium-card { 
        background: linear-gradient(145deg, #1E2533 0%, #0B0E14 100%); 
        padding: 50px; 
        border-radius: 30px; 
        text-align: center; 
        border: 2px solid #00FFC2; 
        margin: 30px 0;
        box-shadow: 0 0 50px rgba(0, 255, 194, 0.1);
    }
    
    /* Motto Yazısı */
    .motto-text { 
        text-align: center; 
        font-style: italic; 
        font-size: 1.3rem; 
        opacity: 0.9; 
        margin-top: -15px; 
        margin-bottom: 40px; 
        color: #00FFC2; 
        font-weight: 300;
    }
    
    /* Sosyal Medya ve Aksiyon Butonları */
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
        transition: transform 0.2s, box-shadow 0.2s; 
    }
    
    .btn-x { background-color: #000000; border: 1px solid #333; }
    .btn-x:hover { transform: translateY(-3px); box-shadow: 0 5px 15px rgba(255,255,255,0.1); }
</style>
""", unsafe_allow_html=True)

# ====================== 4. VERİ YÜKLERİ VE LİSTELEME ======================
@st.cache_data
def load_anchor_db():
    try:
        with open("anchor_db.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Veritabanı Dosyası (anchor_db.json) Eksik! Hata: {e}")
        return {}

ANCHOR_DB = load_anchor_db()
PROFESSION_LIST = sorted(list(ANCHOR_DB.keys()))
OTHER_OPTION = "Other (Custom Entry)"
if ANCHOR_DB:
    PROFESSION_LIST.append(OTHER_OPTION)

# ====================== 5. KOTA YÖNETİMİ (3 HAK + PERSISTENCE) ======================
user_id = get_user_id()
MAX_FREE_QUERIES = 3  # Şenol Usta'nın isteğiyle hak 3 yapıldı

# Eğer veritabanı yoksa tarayıcı hafızasını kullan (Fallback)
if "fallback_usage" not in st.session_state:
    st.session_state.fallback_usage = 0

def get_current_usage():
    """Kullanıcının toplam sorgu sayısını veritabanından veya session'dan çeker."""
    if not db:
        return st.session_state.fallback_usage
    try:
        # PATH: artifacts/apol-oracle/public/data/usage/{userId}
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("usage").document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get("count", 0)
    except:
        pass
    return st.session_state.fallback_usage

def increment_usage():
    """Başarılı her sorgu sonrası sayacı 1 artırır ve kalıcı olarak kaydeder."""
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
    except:
        st.session_state.fallback_usage += 1

current_usage = get_current_usage()

# ====================== 6. PDF ÜRETİM MOTORU (REPORTLAB) ======================
def generate_pdf(job, sector, score, rank, report_text):
    if not PDF_AVAILABLE:
        return None
    
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Arka Plan ve Başlık Tasarımı
    p.setFillColorRGB(0.04, 0.05, 0.08)
    p.rect(0, height - 100, width, 100, fill=1, stroke=0)
    
    p.setFillColorRGB(0, 1, 0.76) # APOL Yeşili
    p.setFont("Helvetica-Bold", 26)
    p.drawString(50, height - 55, "APOL 3.6 | CAREER DOSSIER")
    
    p.setFillColorRGB(0.5, 0.5, 0.5)
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 75, "ORACLE STRATEGIC ANALYSIS REPORT")
    
    # Detay Bilgileri
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 130, f"PROFESSION: {job.upper()}")
    p.drawString(50, height - 150, f"INDUSTRY: {sector.upper()}")
    
    p.drawRightString(width - 50, height - 130, f"SURVIVAL SCORE: {score}/100")
    p.drawRightString(width - 50, height - 150, f"ORACLE RANK: {rank.upper()}")
    
    p.setStrokeColorRGB(0.8, 0.8, 0.8)
    p.line(50, height - 170, width - 50, height - 170)
    
    # Rapor Metni İşleme
    p.setFont("Helvetica", 11)
    y_position = height - 200
    
    # Markdown yıldızlarını temizle
    clean_text = report_text.replace('***', '• ').replace('**', '').replace('* ', '• ')
    
    for line in clean_text.split('\n'):
        if y_position < 70:
            p.showPage()
            y_position = height - 70
            p.setFont("Helvetica", 11)
        
        wrapped_lines = simpleSplit(line, "Helvetica", 11, width - 100)
        for w_line in wrapped_lines:
            p.drawString(50, y_position, w_line)
            y_position -= 16
        y_position -= 6
    
    p.save()
    buffer.seek(0)
    return buffer

# ====================== 7. GEMINI API VE GELİŞMİŞ PUANLAMA ======================
def call_gemini(prompt):
    """Sırayla tüm anahtarları dener, limit dolarsa sonrakine geçer."""
    keys = st.secrets.get("GEMINI_API_KEYS", [])
    if not isinstance(keys, list):
        keys = [keys] if keys else []
    
    # Kullanıcı kendi anahtarını girdiyse o en önceliklidir
    if st.session_state.get("user_api_key"):
        keys = [st.session_state.user_api_key]
    
    if not keys:
        raise Exception("API Anahtarı Bulunamadı! Lütfen sol menüye anahtar girin.")
    
    for key in keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel("models/gemini-2.0-flash")
            return model.generate_content(prompt).text
        except Exception as e:
            continue
    raise Exception("Tüm API anahtarları meşgul veya limitleri doldu.")

def calculate_oracle_score(job, experience):
    """Mimar Şenol Usta'nın özel katsayılarını içeren ana puanlama motoru."""
    anchor = ANCHOR_DB.get(job, list(ANCHOR_DB.values())[0] if ANCHOR_DB else {})
    job_lower = job.lower()
    
    # Şenol Usta'nın "İnsan Dokunuşu" ve "Hukuki İmza" Bonusları
    high_touch = ["driver", "nurse", "officer", "chef", "captain", "soldier", "police", "surgeon", "athlete", "courier", "doctor", "guard"]
    legal_roles = ["lawyer", "accountant", "cpa", "doctor", "judge", "attorney", "notary"]
    
    h_bonus = 14 if any(word in job_lower for word in high_touch) else 0
    l_bonus = 12 if any(word in job_lower for word in legal_roles) else 0
    
    # Gelişmiş Puanlama Algoritması
    weighted_fit = (
        anchor.get("zombie_risk", 0) * -20 +
        anchor.get("abyss_risk", 0) * -18 +
        anchor.get("hybrid_fit", 0) * 25 +
        anchor.get("captain_fit", 0) * 22 +
        anchor.get("cyber_oracle_fit", 0) * 18 +
        anchor.get("new_genesis_fit", 0) * 25 +
        h_bonus + l_bonus
    )
    
    # Deneyim Yılı Çarpanı (Max +9 Puan)
    exp_factor = min(experience * 1.1, 9)
    
    final_score = max(28, min(98, round(weighted_fit + 5.0 + exp_factor)))
    return {
        "score": final_score, 
        "rank": anchor.get("rank", "EVALUATING"), 
        "color": anchor.get("color", "#F1C40F"), 
        "matrix": anchor
    }

# ====================== 8. ANA ARAYÜZ (GÖVDE) ======================
# Logo Alanı
col_logo1, col_logo2, col_logo3 = st.columns([1, 1.3, 1])
with col_logo2:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)

st.markdown("<h1 style='text-align: center; letter-spacing: 10px; font-weight: 900; margin-bottom: 0;'>APOL 3.6</h1>", unsafe_allow_html=True)
st.markdown("<p class='motto-text'>\"İşini yapay zekaya değil, yapay zekayı kullanan birine kaptıracaksın.\"</p>", unsafe_allow_html=True)

# Yan Panel (Control Panel)
st.sidebar.markdown("### 🛡️ CONTROL PANEL")
st.sidebar.text_input("YOUR API KEY (UNLIMITED)", type="password", key="user_api_key", help="Kendi Gemini API anahtarınızı girerek sınırsız sorgu yapabilirsiniz.")
st.sidebar.caption(f"Cihaz Kotası: {current_usage} / {MAX_FREE_QUERIES}")

# KOTA KONTROLÜ (F5'e Karşı Zırhlı Bölge)
if current_usage >= MAX_FREE_QUERIES and not st.session_state.get("user_api_key"):
    st.markdown(f"""
    <div class="premium-card">
        <h2 style="color:#00FFC2; letter-spacing: 3px;">🛡️ CİHAZ KOTASI DOLDU</h2>
        <p style="font-size: 1.2rem; margin-top: 15px;">Bu cihazdan yapılan <b>{MAX_FREE_QUERIES}</b> ücretsiz deneme hakkı kullanılmıştır.</p>
        <p style="opacity:0.7;">F5 yapmak veya sayfayı yenilemek hakkınızı geri getirmez.</p>
        <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 15px; margin: 20px 0;">
            <p>Devam etmek için sol menüdeki <b>YOUR API KEY</b> kutusuna kendi Gemini API anahtarınızı girebilirsiniz.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    # Giriş Alanları
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        selected_job = st.selectbox("SELECT PROFESSION / MESLEK SEÇİN", PROFESSION_LIST)
        if selected_job == OTHER_OPTION:
            final_job = st.text_input("Enter Profession (English Name)")
            final_sector = st.text_input("Enter Industry / Sector (English)")
        else:
            final_job = selected_job
            final_sector = ANCHOR_DB[selected_job]["sector"]
            st.info(f"📍 Industry: **{final_sector}**")
            
    with col_in2:
        exp_in = st.slider("EXPERIENCE (YEARS) / DENEYİM", 0, 40, 5)
        skills_in = st.text_area("KEY SKILLS / BECERİLER", placeholder="e.g. Leadership, Python, Crisis Management, Medical Diagnosis...", height=68)

    # ANA BUTON
    if st.button("KEHANETİ BAŞLAT / EXECUTE PROPHECY", use_container_width=True, type="primary"):
        if final_job and final_sector:
            with st.spinner("Oracle analiz katmanlarını çalıştırıyor..."):
                try:
                    calc = calculate_oracle_score(final_job, exp_in)
                    
                    # Gemini Analiz Prompt'u
                    prompt_text = f"""
                    Analyze career for '{final_job}' in '{final_sector}' with skills: '{skills_in}'. 
                    Score: {calc['score']}/100. Rank: {calc['rank']}. 
                    Provide 10-20 year projection. Use headers: 🚨 MARKET PULSE, 🛡️ PROTECTION SHIELD, ⚔️ HUMAN FORTRESS, 🔮 ASCENSION ROADMAP. 
                    Be professional, visionary and witty. English output only.
                    """
                    
                    report_result = call_gemini(prompt_text)
                    
                    # Veritabanı Sayacını Artır (F5 Kilidi burada kuruluyor!)
                    increment_usage()
                    
                    # Sonuçları Kaydet (Rerun sonrası kaybolmaması için)
                    st.session_state.last_calc = calc
                    st.session_state.last_report = report_result
                    st.session_state.last_job = final_job
                    st.session_state.last_sector = final_sector
                    
                    # Sayfayı tazeleyerek kullanım bilgisini yansıt
                    st.rerun()
                except Exception as e:
                    st.error(f"Sistem Hatası: {e}")
        else:
            st.warning("Lütfen meslek ve sektör bilgilerini eksiksiz girin.")

    # SONUÇ EKRANI (Analiz Bittiyse)
    if "last_report" in st.session_state:
        calc = st.session_state.last_calc
        report = st.session_state.last_report
        job = st.session_state.last_job
        sector = st.session_state.last_sector
        
        # Büyük Skor Kartı
        st.markdown(f"""
            <div class="score-card" style="border-color: {calc['color']}55;">
                <p style="opacity: 0.5; letter-spacing: 6px; font-size: 1rem;">SURVIVAL SCORE</p>
                <h1 class="score-value">{calc["score"]}</h1>
                <div class="rank-badge" style="color:{calc["color"]}; border-color:{calc["color"]}88;">{calc["rank"]}</div>
            </div>
        """, unsafe_allow_html=True)
        
        col_res1, col_res2 = st.columns([1.8, 1])
        with col_res1:
            st.markdown(f'<div class="report-box">{report}</div>', unsafe_allow_html=True)
        with col_res2:
            # Radar Grafiği (Matrix Verilerinden)
            matrix_data = {k: v*100 for k,v in calc['matrix'].items() if k.endswith("_risk") or k.endswith("_fit")}
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(
                r=list(matrix_data.values()), 
                theta=list(matrix_data.keys()), 
                fill='toself', 
                line_color=calc['color'],
                name=job
            ))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=False)), 
                template="plotly_dark", 
                margin=dict(l=30,r=30,t=30,b=30),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig, use_container_width=True)

        # AKSİYON BUTONLARI (PDF & SOSYAL MEDYA)
        st.markdown("<div style='text-align: center; margin-top: 35px;'>", unsafe_allow_html=True)
        
        # PDF Butonu
        pdf_file = generate_pdf(job, sector, calc['score'], calc['rank'], report)
        if pdf_file:
            st.download_button(
                label="📄 DOWNLOAD PDF REPORT", 
                data=pdf_file, 
                file_name=f"APOL_Report_{job.replace(' ', '_')}.pdf", 
                mime="application/pdf"
            )
        
        # X (Twitter) Paylaşımı
        x_tweet = f"APOL 3.6 Career Protection Score for {job}: {calc['score']}/100! @ApolOracle #APOL #AI"
        st.markdown(f'<a href="https://twitter.com/intent/tweet?text={urllib.parse.quote(x_tweet)}" target="_blank" class="action-btn btn-x">𝕏 SHARE ON X</a>', unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)

# Alt Bilgi
st.markdown("---")
st.caption("EST. 2026 | @ApolOracle | Persistence Mode (Firestore) Active | Built for Human Labor ❤️")
