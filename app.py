"""
Monaco Payroll System - Main Application
=========================================
Système complet de gestion des paies pour Monaco

source .venv/bin/activate
streamlit run app.py
"""

import streamlit as st
from services.auth import AuthManager
from services.payroll_system import IntegratedPayrollSystem
from services.data_mgt import DataManager
import duckdb
from pathlib import Path
from datetime import datetime

# ========================
# Styling and Configuration
# ========================

st.set_page_config(
    page_title="Monaco Payroll System",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS - hide sidebar before login
hide_sidebar = ""
if not st.session_state.get('authenticated', False):
    hide_sidebar = """
    [data-testid="stSidebar"] {
        display: none;
    }
    [data-testid="collapsedControl"] {
        display: none;
    }
    """

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    }}

    .stApp {{
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    }}

    .block-container {{
        padding-top: 2rem;
        padding-bottom: 2rem;
    }}

    h1, h2, h3 {{
        color: #2c3e50;
        font-weight: 600;
    }}

    .stButton>button {{
        border-radius: 6px;
        font-weight: 500;
        transition: all 0.2s ease;
    }}

    .stButton>button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}

    div[data-testid="stMetricValue"] {{
        font-size: 1.8rem;
        font-weight: 600;
        color: #2c3e50;
    }}

    .stDataFrame {{
        border-radius: 8px;
        overflow: hidden;
    }}

    {hide_sidebar}
    </style>
""", unsafe_allow_html=True)

# ========================
# Session State Init
# ========================

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user' not in st.session_state:
    st.session_state.user = None
if 'role' not in st.session_state:
    st.session_state.role = None
if 'current_company' not in st.session_state:
    st.session_state.current_company = None
if 'current_period' not in st.session_state:
    st.session_state.current_period = None
if 'payroll_system' not in st.session_state:
    st.session_state.payroll_system = None

# ========================
# Cached Data Loading
# ========================

@st.cache_data(ttl=600)
def load_companies_cached():
    """Load companies from DB (cached 10min)"""
    try:
        return DataManager.get_companies_list()
    except Exception as e:
        if "WAL" in str(e) or "Catalog Error" in str(e):
    
            db_path = Path("data/payroll.duckdb")
            wal_path = Path("data/payroll.duckdb.wal")

            # Remove corrupted WAL
            if wal_path.exists():
                wal_path.unlink()

            # Reconnect and retry
            return DataManager.get_companies_list()
        else:
            raise

# ========================
# Login Page
# ========================

def login_page():
    """Page de connexion"""
    st.markdown("""
        <div style="text-align: center; margin: 2rem 0;">
            <h1 style="color: #2c3e50; font-weight: 700; margin-bottom: 0.5rem;">Logiciel de Paie Monégasque</h1>
            <p style="color: #6c757d; font-size: 1.1rem; margin-bottom: 3rem;">Système professionnel de gestion des paies</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("#### Connexion")

        with st.form("login_form"):
            username = st.text_input("Nom d'utilisateur", placeholder="Saisissez votre nom d'utilisateur")
            password = st.text_input("Mot de passe", type="password", placeholder="Saisissez votre mot de passe")
            submit = st.form_submit_button("Se connecter", use_container_width=True, type="primary")

            if submit:
                user = AuthManager.verify_user(username, password)
                if user:
                    st.session_state.authenticated = True
                    st.session_state.user = user['username']
                    st.session_state.role = user['role']
                    st.session_state.payroll_system = IntegratedPayrollSystem()
                    st.success(f"Bienvenue, {user['name']}!")
                    st.rerun()
                else:
                    st.error("Nom d'utilisateur ou mot de passe incorrect")

# ========================
# Main App with Sidebar
# ========================

def main_app():
    """Application principale avec navigation sidebar"""

    with st.sidebar:
        st.markdown("""
            <div style="padding: 1rem 0; border-bottom: 1px solid #e8e8e8; margin-bottom: 1.5rem;">
                <h3 style="margin: 0; color: #2c3e50;">Paie Monégasque</h3>
                <div style="margin-top: 0.5rem; color: #6c757d; font-size: 0.9rem;">
                    <div>👤 {}</div>
                    <div>🔐 {}</div>
                </div>
            </div>
        """.format(st.session_state.user, st.session_state.role), unsafe_allow_html=True)

        st.markdown("**Entreprise**")
        companies = load_companies_cached()
        company_names = [c['name'] for c in companies]

        # Find current selection index
        current_company_name = None
        if st.session_state.current_company:
            company = next((c for c in companies if c['id'] == st.session_state.current_company), None)
            current_company_name = company['name'] if company else None

        selected_index = company_names.index(current_company_name) if current_company_name in company_names else 0
        selected_company = st.selectbox(
            "company_select",
            company_names,
            index=selected_index,
            label_visibility="collapsed",
            key="sidebar_company_selector"
        )

        if selected_company:
            company = next((c for c in companies if c['name'] == selected_company), None)
            st.session_state.current_company = company['id'] if company else None

        st.markdown("**Période**")
        # Generate last 12 months
        periods = []
        now = datetime.now()
        for i in range(12):
            month = now.month - i
            year = now.year
            if month <= 0:
                month += 12
                year -= 1
            periods.append(f"{month:02d}-{year}")

        current_period_idx = 0
        if st.session_state.current_period and st.session_state.current_period in periods:
            current_period_idx = periods.index(st.session_state.current_period)

        st.session_state.current_period = st.selectbox(
            "period_select",
            options=periods,
            index=current_period_idx,
            label_visibility="collapsed",
            key="sidebar_period_selector"
        )

        st.markdown("---")

        if st.button("Déconnexion", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # Main content area
    st.markdown("## Bienvenue dans le système de paie Monaco")

    if st.session_state.current_company and st.session_state.current_period:
        st.success(f"**Société:** {selected_company} | **Période:** {st.session_state.current_period}")
    else:
        st.warning("Veuillez sélectionner une entreprise et une période dans la barre latérale")

    st.markdown("---")

    st.markdown("### Navigation")
    st.info("""
    Utilisez le menu des pages à gauche pour naviguer:

    📊 **Dashboard** - Vue d'ensemble des métriques et tendances
    📥 **Import** - Importer les données depuis Excel/CSV
    ⚙️ **Traitement** - Traiter les paies avec agent intelligent
    ✅ **Validation** - Valider et modifier les bulletins
    📄 **PDF Generation** - Générer bulletins, journaux, provisions
    📧 **Email** - Envoyer les bulletins par email
    📤 **Export** - Exporter les résultats vers Excel
    📋 **DSM** - Déclarations sociales Monaco (XML)
    ⚙️ **Config** - Configuration (admin)
    """)

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        ### 📊 Tableau de bord
        Vue d'ensemble de vos paies:
        - Métriques clés
        - Évolution des salaires
        - Cas particuliers
        """)

    with col2:
        st.markdown("""
        ### 💼 Traitement
        Processus complet:
        - Import Excel
        - Calculs automatiques
        - Validation
        - Génération PDFs
        """)

    with col3:
        st.markdown("""
        ### 📋 Déclarations
        Conformité Monaco:
        - DSM XML
        - Charges sociales
        - Archivage
        """)

# ========================
# Main Entry Point
# ========================

if __name__ == "__main__":
    if not st.session_state.authenticated:
        login_page()
    else:
        main_app()
