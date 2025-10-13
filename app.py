"""
Monaco Payroll System - Complete Consolidated Application
=========================================================
Système complet de gestion des paies pour Monaco
Version consolidée avec tous les modules intégrés

source monaco_paie/bin/activate
source .venv/bin/activate
streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import calendar
import os, json, io, hashlib, logging, time, base64, shutil, zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
from decimal import Decimal, ROUND_HALF_UP
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate
import traceback
import pyarrow
import pyarrow.parquet as pq
HAS_PYARROW = True
HAS_EXCEL = True

# Import all our custom modules
from services.data_mgt import (
    DataManager,
    DataConsolidation
) 
from services.auth import AuthManager
from services.payroll_calculations import (
    CalculateurPaieMonaco, 
    ValidateurPaieMonaco,
    GestionnaireCongesPayes,
    ChargesSocialesMonaco,
    MonacoPayrollConstants
)
from services.import_export import (
    ExcelImportExport,
    CrossBorderTaxation,
    DataConsolidation
)
from services.pdf_generation import PDFGeneratorService
from services.email_archive import (
    EmailDistributionService,
    EmailConfig,
    EmailConfigManager,
    PDFArchiveManager,
    ComplianceAuditLogger,
    EmailTemplate
)
from services.oauth2_integration import (
    OAuth2Config, 
    OAuth2EmailManager, 
    MicrosoftOAuth2Service
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create default admin user if no users exist
try:
    if len(AuthManager.list_users()) == 0:
        AuthManager.create_default_users()
        logger.info("Created default users")
except Exception as e:
    logger.error(f"Error checking/creating default users: {e}")

# ============================================================================
# CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Système de Paie Monaco",
    page_icon="🇲🇨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add custom CSS right after st.set_page_config():

st.markdown("""
<style>
    /* Import clean font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Main app styling */
    .stApp {
        font-family: 'Inter', sans-serif;
        background-color: #fafafa;
    }
    
    /* Remove default spacing and padding */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 1200px;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background-color: #ffffff;
        border-right: 1px solid #e8e8e8;
    }
    
    /* Clean sidebar spacing */
    .css-1d391kg .stSelectbox > div > div {
        margin-bottom: 1rem;
    }
    
    /* Button styling */
    .stButton > button {
        border-radius: 8px;
        border: 1px solid #e8e8e8;
        background-color: #ffffff;
        color: #2c3e50;
        font-weight: 500;
        padding: 0.5rem 1rem;
        transition: all 0.2s ease;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    .stButton > button:hover {
        background-color: #f8f9fa;
        border-color: #d0d7de;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    }
    
    /* Primary button styling */
    .stButton > button[kind="primary"] {
        background-color: #2c3e50;
        color: white;
        border-color: #2c3e50;
    }
    
    .stButton > button[kind="primary"]:hover {
        background-color: #1a252f;
        border-color: #1a252f;
    }
    
    /* Clean headers */
    h1, h2, h3 {
        color: #2c3e50;
        font-weight: 600;
        margin-top: 0;
        margin-bottom: 1.5rem;
    }
    
    h1 { font-size: 2rem; }
    h2 { font-size: 1.5rem; }
    h3 { font-size: 1.25rem; }
    
    /* Card-like containers */
    .stTabs {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        margin-bottom: 2rem;
    }
    
    /* Clean metrics */
    .metric-container {
        background-color: #ffffff;
        border-radius: 8px;
        padding: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #f0f0f0;
    }
    
    /* Form styling */
    .stForm {
        background-color: #ffffff;
        border-radius: 8px;
        padding: 1.5rem;
        border: 1px solid #e8e8e8;
    }
    
    /* Clean inputs */
    .stTextInput > div > div > input {
        border-radius: 6px;
        border: 1px solid #e8e8e8;
        font-size: 0.95rem;
    }
    
    .stSelectbox > div > div {
        border-radius: 6px;
        border: 1px solid #e8e8e8;
    }
    
    /* Success/warning/error styling */
    .stSuccess {
        background-color: #f0f9ff;
        border: 1px solid #38a169;
        border-radius: 6px;
        padding: 0.75rem;
    }
    
    .stWarning {
        background-color: #fffbeb;
        border: 1px solid #f59e0b;
        border-radius: 6px;
        padding: 0.75rem;
    }
    
    .stError {
        background-color: #fef2f2;
        border: 1px solid #ef4444;
        border-radius: 6px;
        padding: 0.75rem;
    }
    
    /* Clean spacing for columns */
    .row-widget.stHorizontal > div {
        padding-right: 0.75rem;
    }
    
    .row-widget.stHorizontal > div:last-child {
        padding-right: 0;
    }
    
    /* Premium dividers */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(to right, transparent, #e8e8e8, transparent);
        margin: 2rem 0;
    }
    
    /* Responsive design */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        
        h1 { font-size: 1.5rem; }
        h2 { font-size: 1.25rem; }
        h3 { font-size: 1.1rem; }
    }
</style>
""", unsafe_allow_html=True)

# Replace section headers throughout with:
# st.markdown("## Section Title") instead of st.header() or st.subheader()

# Constants
DATA_DIR = Path("data")
CONFIG_DIR = Path("config")
ARCHIVES_DIR = Path("archives")
TEMP_DIR = Path("temp")
USERS_FILE = DATA_DIR / "users.parquet"
COMPANIES_DIR = DATA_DIR / "companies"
PAYSTUBS_DIR = DATA_DIR / "paystubs"
CONSOLIDATED_DIR = DATA_DIR / "consolidated"

# Create directories
for directory in [DATA_DIR, CONFIG_DIR, ARCHIVES_DIR, TEMP_DIR, COMPANIES_DIR, PAYSTUBS_DIR, CONSOLIDATED_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.current_company = None
    st.session_state.current_period = None
    st.session_state.payroll_system = None
    st.session_state.generated_pdfs = {}


def require_login():
    if st.session_state.get("auth_ok"):
        return True

    with st.sidebar:
        st.subheader("Sign In")
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Enter"):
            info = AuthManager.verify_user(u, p)
            if info:
                st.session_state["auth_ok"] = True
                st.session_state["username"] = info["username"]
                st.session_state["role"] = info["role"]
                st.success(f"Welcome, {info['username']}!")
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
    st.stop()
    st.info("**Demo25:** admin/admin123 ou comptable/compta123")

def is_admin() -> bool:
    return st.session_state.get("role") == "admin"

def is_comptable() -> bool:
    return st.session_state.get("role") == "comptable"

# ============================================================================
# MAIN APPLICATION SYSTEM
# ============================================================================

class IntegratedPayrollSystem:
    """Système intégré de gestion de paie"""
    
    def __init__(self):
        """Initialiser le système complet"""
        self.calculator = CalculateurPaieMonaco()
        self.validator = ValidateurPaieMonaco()
        self.pto_manager = GestionnaireCongesPayes()
        self.excel_manager = ExcelImportExport()
        self.data_consolidator = DataConsolidation()
        self.company_info = self._load_company_info()
    
    def _load_company_info(self) -> Dict:
        """Charger les informations de l'entreprise"""
        config_file = CONFIG_DIR / "company_info.json"
        
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        default_info = {
            'name': 'Cabinet Comptable Monaco',
            'siret': '000000000',
            'address': '98000 MONACO',
            'phone': '+377 93 00 00 00',
            'email': 'contact@cabinet.mc'
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_info, f, indent=2)
        
        return default_info
    
    def process_monthly_payroll(self, company_id: str, period: str) -> Dict:
        """Traiter la paie mensuelle complète"""
        report = {
            'period': period,
            'company_id': company_id,
            'start_time': datetime.now(),
            'steps': []
        }
        
        try:
            month, year = map(int, period.split('-'))
            df = self.data_consolidator.load_period_data(company_id, month, year)

            if df.empty:
                report['error'] = "Aucune donnée trouvée pour cette période"
                return report
            
            report['steps'].append({
                'step': 'Chargement des données',
                'status': 'success',
                'count': len(df)
            })
            
            processed_data = []
            edge_cases = []
            
            for idx, row in df.iterrows():
                payslip = self.calculator.process_employee_payslip(row.to_dict())
                is_valid, issues = self.validator.validate_payslip(payslip)
                
                if not is_valid or pd.notna(row.get('remarques')) or pd.notna(row.get('date_sortie')):
                    edge_cases.append({
                        'matricule': row['matricule'],
                        'nom': row['nom'],
                        'prenom': row['prenom'],
                        'issues': issues,
                        'remarques': row.get('remarques'),
                        'date_sortie': row.get('date_sortie')
                    })
                    payslip['statut_validation'] = 'À vérifier'
                    payslip['edge_case_flag'] = True
                    payslip['edge_case_reason'] = '; '.join(issues) if issues else 'Remarques ou date de sortie'
                else:
                    payslip['statut_validation'] = True
                    payslip['edge_case_flag'] = False
                    payslip['edge_case_reason'] = ''
                
                # Keep original data
                for key in row.index:
                    if key not in payslip:
                        payslip[key] = row[key]
                
                processed_data.append(payslip)
            
            processed_df = pd.DataFrame(processed_data)
            self.data_consolidator.save_period_data(processed_df, company_id, month, year)
            
            report['steps'].append({
                'step': 'Calcul des paies',
                'status': 'success',
                'processed': len(processed_data),
                'validated': len(processed_data) - len(edge_cases),
                'edge_cases': len(edge_cases)
            })
            
            st.session_state['processed_data'] = processed_df
            st.session_state['edge_cases'] = edge_cases
            
            report['success'] = True
            report['end_time'] = datetime.now()
            report['duration'] = (report['end_time'] - report['start_time']).total_seconds()
            
        except Exception as e:
            report['error'] = str(e)
            report['success'] = False
            logger.error(f"Erreur traitement paie: {e}")
            logger.error(traceback.format_exc())
        
        return report


# ============================================================================
# STREAMLIT UI PAGES
# ============================================================================

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
        
        st.markdown("</div>", unsafe_allow_html=True)

def main_app():
    """Application principale"""
    
    with st.sidebar:
        st.markdown("""
            <div style="padding: 1rem 0; border-bottom: 1px solid #e8e8e8; margin-bottom: 1.5rem;">
                <h3 style="margin: 0; color: #2c3e50;">Navigation</h3>
                <div style="margin-top: 0.5rem; color: #6c757d; font-size: 0.9rem;">
                    <div>👤 {}</div>
                    <div>🔐 {}</div>
                </div>
            </div>
        """.format(st.session_state.user, st.session_state.role), unsafe_allow_html=True)
        
        st.markdown("**Entreprise**")
        companies = DataManager.get_companies_list()
        company_names = [c['name'] for c in companies]
        selected_company = st.selectbox("", company_names, label_visibility="collapsed")
        
        if selected_company:
            company = next((c for c in companies if c['name'] == selected_company), None)
            st.session_state.current_company = company['id'] if company else None

        st.markdown("**Période**")
        current_month = datetime.now().strftime("%m-%Y")
        st.session_state.current_period = st.selectbox("", options=[current_month], label_visibility="collapsed")

        st.markdown("---")
        
        pages = {
            "📊 Tableau de bord": "dashboard",
            "📥 Import des données": "import", 
            "💰 Traitement des paies": "processing",
            "✅ Validation": "validation",
            "📄 Génération PDF": "pdf_generation",
            "📄 Export des résultats": "export"
        }
        
        if st.session_state.role == "admin":
            pages["⚙️ Configuration"] = "config"
            pages["📋 Journal modifications"] = "audit_log"
        
        # Clean navigation
        st.markdown("**Menu**")
        selected_page = st.radio("", list(pages.keys()), label_visibility="collapsed")
        current_page = pages[selected_page]
        
        st.markdown("---")
        
        if st.button("Déconnexion", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # Main content header
    st.markdown(f"""
        <div style="margin-bottom: 2rem;">
            <h1 style="margin-bottom: 0.5rem;">{selected_company}</h1>
            <p style="color: #6c757d; margin: 0;">Période: {st.session_state.current_period}</p>
        </div>
    """, unsafe_allow_html=True)
        
    if current_page == "dashboard":
        dashboard_page()
    elif current_page == "import":
        import_page()
    elif current_page == "processing":
        processing_page()
    elif current_page == "validation":
        validation_page()
    elif current_page == "pdf_generation":
        pdf_generation_page()
    elif current_page == "export":
        export_page()
    elif current_page == "config":
        config_page()
    elif current_page == "audit_log":
        audit_log_page()

def dashboard_page():
    """Page tableau de bord"""
    st.markdown("## Tableau de bord")
    
    if not st.session_state.current_company or not st.session_state.current_period:
        st.warning("Sélectionnez une entreprise et une période")
        return
    
    system = st.session_state.payroll_system
    month, year = map(int, st.session_state.current_period.split('-'))
    
    df = system.data_consolidator.load_period_data(st.session_state.current_company, month, year)
    
    if df.empty:
        st.info("Aucune donnée pour cette période. Commencez par importer les données.")
        return
    
    # Premium metrics cards
    col1, col2, col3, col4 = st.columns(4)
    
    metrics_style = """
        <div style="background: white; padding: 1.5rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 1rem;">
            <div style="color: #6c757d; font-size: 0.85rem; font-weight: 500; margin-bottom: 0.5rem;">{}</div>
            <div style="color: #2c3e50; font-size: 1.5rem; font-weight: 600;">{}</div>
        </div>
    """
    
    with col1:
        st.markdown(metrics_style.format("SALARIÉS", len(df)), unsafe_allow_html=True)
    
    with col2:
        total_brut = df['salaire_brut'].sum() if 'salaire_brut' in df.columns else 0
        st.markdown(metrics_style.format("MASSE SALARIALE", f"{total_brut:,.0f} €"), unsafe_allow_html=True)
    
    with col3:
        edge_cases = df['edge_case_flag'].sum() if 'edge_case_flag' in df.columns else 0
        st.markdown(metrics_style.format("CAS À VÉRIFIER", edge_cases), unsafe_allow_html=True)
    
    with col4:
        validated = (df['statut_validation'] == True).sum() if 'statut_validation' in df.columns else 0
        st.markdown(metrics_style.format("VALIDÉES", f"{validated}/{len(df)}"), unsafe_allow_html=True)
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Répartition par statut")
        if 'statut_validation' in df.columns:
            status_counts = df['statut_validation'].value_counts()
            st.bar_chart(status_counts)
    
    with col2:
        st.subheader("Distribution des salaires nets")
        if 'salaire_net' in df.columns and not df['salaire_net'].isna().all():
            fig_data = df['salaire_net'].astype(float).dropna()
            # Create bins
            binned = pd.cut(fig_data, bins=10)
            counts = binned.value_counts().sort_index()
            
            # Create cleaner labels with K for thousands
            def format_salary(value):
                """Format salary with K for thousands"""
                if value >= 1000:
                    return f"{int(value/1000)}K"
                else:
                    return f"{int(value)}"
            
            clean_labels = [
                f"{format_salary(interval.left)}-{format_salary(interval.right)}€"
                for interval in counts.index
            ]
            
            # Create a new series with clean labels, maintaining order
            chart_data = pd.Series(counts.values, index=clean_labels)
            st.bar_chart(chart_data)
    
    st.markdown("---")
    st.subheader("Employés avec cas particuliers")
    
    if 'edge_case_flag' in df.columns:
        edge_cases_df = df[df['edge_case_flag'] == True]
        if not edge_cases_df.empty:
            display_cols = ['matricule', 'nom', 'prenom']
            if 'salaire_brut' in edge_cases_df.columns:
                display_cols.append('salaire_brut')
            if 'edge_case_reason' in edge_cases_df.columns:
                display_cols.append('edge_case_reason')
            
            st.dataframe(edge_cases_df[display_cols], use_container_width=True)
        else:
            st.success("Aucun cas particulier détecté")

def import_page():
    """Page d'import des données"""
    st.header("📥 Import des données")
    
    if not st.session_state.current_company or not st.session_state.current_period:
        st.warning("Sélectionnez une entreprise et une période")
        return
    
    system = st.session_state.payroll_system
    
    tab1, tab2 = st.tabs(["Import Excel", "Télécharger Template"])
    
    with tab1:
        st.subheader("Importer les données depuis Excel")
        
        uploaded_file = st.file_uploader(
            "Choisir un fichier Excel",
            type=['xlsx', 'xls', 'csv'],
            help="Le fichier doit respecter le format du template"
        )
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_import = pd.read_csv(uploaded_file)
                    df_import = df_import.rename(columns=system.excel_manager.EXCEL_COLUMN_MAPPING)
                else:
                    df_import = system.excel_manager.import_from_excel(uploaded_file)
                
                st.success(f"✅ {len(df_import)} employés importés avec succès")
                
                st.subheader("Aperçu des données importées")
                st.dataframe(df_import.head(10), use_container_width=True)
                
                if st.button("💾 Sauvegarder les données", type="primary", use_container_width=True):
                    month, year = map(int, st.session_state.current_period.split('-'))
                    
                    system.data_consolidator.save_period_data(
                        df_import,
                        st.session_state.current_company,
                        month,
                        year
                    )
                    
                    st.success("Données sauvegardées avec succès!")
                    
            except Exception as e:
                st.error(f"Erreur lors de l'import: {str(e)}")
    
    with tab2:
        st.subheader("Télécharger le fichier Excel")
        
        st.info("""
        Ce fichier Excel contient toutes les colonnes nécessaires pour l'import:
        - Informations des employés (Matricule, Nom, Prénom, Email)
        - Salaires et heures (Salaire de base, Base heures)
        - Primes et avantages
        - Absences et congés
        """)
        
        if st.button("📥 Générer le template", use_container_width=True):
            template_buffer = system.excel_manager.create_template()
            
            st.download_button(
                label="💾 Télécharger template.xlsx",
                data=template_buffer.getvalue(),
                file_name=f"template_paie_{st.session_state.current_period}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if HAS_EXCEL else "text/csv"
            )

def processing_page():
    """Page de traitement des paies"""
    st.markdown("## Traitement des paies")
    
    if not st.session_state.current_company or not st.session_state.current_period:
        st.warning("Sélectionnez une entreprise et une période")
        return
    
    system = st.session_state.payroll_system
    
    # Clean info box
    st.markdown("""
        <div style="background: #f8f9fa; border-left: 4px solid #2c3e50; padding: 1rem; border-radius: 0 8px 8px 0; margin-bottom: 2rem;">
            <div style="font-weight: 500; margin-bottom: 0.5rem;">Traitement automatique</div>
            <div style="color: #6c757d; font-size: 0.9rem;">
                • Calcul des salaires selon la législation monégasque<br>
                • Détection automatique des cas particuliers<br>
                • Préparation des données pour l'export
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    if st.button("Lancer le traitement", type="primary", use_container_width=False):
        with st.spinner("Traitement en cours..."):
            report = system.process_monthly_payroll(
                st.session_state.current_company,
                st.session_state.current_period
            )
            
        if report.get('success'):
            st.success("✅ Traitement terminé avec succès!")
                
            for step in report['steps']:
                if step['status'] == 'success':
                    st.write(f"✓ {step['step']}")
                
            st.markdown("---")
            st.subheader("Résultats du traitement")
                
            if 'processed_data' in st.session_state:
                df = st.session_state.processed_data
                    
                col1, col2, col3 = st.columns(3)
                    
                with col1:
                    st.metric("Fiches traitées", len(df))
                    
                with col2:
                    validated = (df['statut_validation'] == True).sum()
                    st.metric("Validées automatiquement", f"{validated} ({validated/len(df)*100:.1f}%)")
                    
                with col3:
                    edge_cases = df['edge_case_flag'].sum()
                    st.metric("Cas à vérifier", edge_cases)
        else:
            st.error(f"Erreur: {report.get('error', 'Erreur inconnue')}")

# ============================================================================
# PAYSLIP EDITING HELPERS
# ============================================================================

def get_salary_rubrics() -> List[Dict]:
    """Get salary element rubrics from pdf_generation"""
    from services.pdf_generation import PaystubPDFGenerator
    codes = PaystubPDFGenerator.RUBRIC_CODES
    
    return [
        {'code': codes['salaire_base'], 'label': 'Salaire Mensuel', 'field': 'salaire_base'},
        {'code': codes['prime_anciennete'], 'label': "Prime d'ancienneté", 'field': 'prime_anciennete'},
        {'code': codes['heures_sup_125'], 'label': 'Heures sup. 125%', 'field': 'heures_sup_125'},
        {'code': codes['heures_sup_150'], 'label': 'Heures sup. 150%', 'field': 'heures_sup_150'},
        {'code': codes['prime_performance'], 'label': 'Prime performance', 'field': 'prime'},
        {'code': codes['prime_autre'], 'label': 'Autre prime', 'field': 'prime_autre'},
        {'code': codes['jours_feries'], 'label': 'Jours fériés 100%', 'field': 'heures_jours_feries'},
        {'code': codes['absence_maladie'], 'label': 'Absence maladie', 'field': 'heures_absence'},
        {'code': codes['absence_cp'], 'label': 'Absence congés payés', 'field': 'heures_conges_payes'},
        {'code': codes['indemnite_cp'], 'label': 'Indemnité congés payés', 'field': 'jours_conges_pris'},
        {'code': codes['tickets_resto'], 'label': 'Tickets restaurant', 'field': 'tickets_restaurant'},
    ]

def get_charge_rubrics() -> Dict[str, List[Dict]]:
    """Get social charge rubrics from payroll_calculations"""
    from services.payroll_calculations import ChargesSocialesMonaco
    
    salariales = []
    for key, params in ChargesSocialesMonaco.COTISATIONS_SALARIALES.items():
        salariales.append({
            'code': key,
            'label': params['description'],
            'taux': params['taux'],
            'plafond': params['plafond']
        })
    
    patronales = []
    for key, params in ChargesSocialesMonaco.COTISATIONS_PATRONALES.items():
        patronales.append({
            'code': key,
            'label': params['description'],
            'taux': params['taux'],
            'plafond': params['plafond']
        })
    
    return {
        'salariales': salariales,
        'patronales': patronales
    }

def log_modification(matricule: str, field: str, old_value, new_value, user: str, reason: str):
    """Log paystub modification for audit trail"""
    
    log_dir = Path("data/audit_logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'user': user,
        'matricule': matricule,
        'field': field,
        'old_value': str(old_value),
        'new_value': str(new_value),
        'reason': reason,
        'period': st.session_state.current_period,
        'company': st.session_state.current_company
    }
    
    log_file = log_dir / f"modifications_{datetime.now().strftime('%Y%m')}.jsonl"
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

def recalculate_employee_payslip(employee_data: Dict, modifications: Dict) -> Dict:
    """Recalculate payslip after modifications"""

    # Apply modifications to employee_data
    updated_data = employee_data.copy()
    updated_data.update(modifications)
    
    # Recalculate
    calculator = CalculateurPaieMonaco()
    return calculator.process_employee_payslip(updated_data)

def validation_page():
    """Page de validation des cas particuliers avec édition"""
    st.header("✅ Validation et Modification des Paies")
    
    if 'edge_cases' not in st.session_state:
        st.session_state.edge_cases = []
    
    if 'processed_data' not in st.session_state or st.session_state.processed_data.empty:
        st.info("Aucune donnée traitée. Lancez d'abord le traitement des paies.")
        return
    
    df = st.session_state.processed_data
    edge_cases = st.session_state.edge_cases
    
    # Filter and search bar
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        search = st.text_input("🔍 Rechercher (matricule, nom, prénom)", "")
    with col2:
        status_filter = st.selectbox("Filtrer par statut", 
                                     ["Tous", "À vérifier", "Validés"])
    with col3:
        st.metric("Cas à vérifier", len(edge_cases))
    
    # Apply filters
    filtered_df = df.copy()
    if search:
        mask = (filtered_df['matricule'].astype(str).str.contains(search, case=False) |
                filtered_df['nom'].astype(str).str.contains(search, case=False) |
                filtered_df['prenom'].astype(str).str.contains(search, case=False))
        filtered_df = filtered_df[mask]
    
    if status_filter == "À vérifier":
        filtered_df = filtered_df[filtered_df['edge_case_flag'] == True]
    elif status_filter == "Validés":
        filtered_df = filtered_df[filtered_df['statut_validation'] == True]
    
    st.markdown("---")
    
    # Display employees
    if filtered_df.empty:
        st.info("Aucun employé trouvé avec ces critères")
        return
    
    for idx, row in filtered_df.iterrows():
        matricule = row['matricule']
        is_edge_case = row.get('edge_case_flag', False)
        is_validated = row.get('statut_validation', False) == True
        
        # Expander title with status indicator
        status_icon = "⚠️" if is_edge_case else ("✅" if is_validated else "⏳")
        title = f"{status_icon} {row['nom']} {row['prenom']} - {matricule}"
        
        with st.expander(title, expanded=is_edge_case):
            # Initialize edit mode state
            edit_key = f"edit_mode_{matricule}"
            if edit_key not in st.session_state:
                st.session_state[edit_key] = False
            
            # Show issues if any
            if is_edge_case:
                st.warning(f"**Raison:** {row.get('edge_case_reason', 'Non spécifiée')}")
            
            # Summary row
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Salaire brut", f"{row.get('salaire_brut', 0):,.2f} €")
            with col2:
                st.metric("Charges sal.", f"{row.get('total_charges_salariales', 0):,.2f} €")
            with col3:
                st.metric("Salaire net", f"{row.get('salaire_net', 0):,.2f} €")
            with col4:
                st.metric("Coût employeur", f"{row.get('cout_total_employeur', 0):,.2f} €")
            
            st.markdown("---")
            
            # Toggle edit mode
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                if st.button("✏️ Modifier" if not st.session_state[edit_key] else "❌ Annuler", 
                           key=f"toggle_edit_{matricule}"):
                    st.session_state[edit_key] = not st.session_state[edit_key]
                    st.rerun()
            
            # EDIT MODE
            if st.session_state[edit_key]:
                st.subheader("📝 Mode Édition")
                
                # Initialize modifications storage
                mod_key = f"modifications_{matricule}"
                if mod_key not in st.session_state:
                    st.session_state[mod_key] = {}
                
                tab1, tab2 = st.tabs(["💰 Éléments de Salaire", "📊 Charges Sociales"])
                
                # TAB 1: SALARY ELEMENTS
                with tab1:
                    st.markdown("##### Éléments de rémunération")
                    
                    salary_rubrics = get_salary_rubrics()
                    
                    # Create editable table
                    for rubric in salary_rubrics:
                        field = rubric['field']
                        current_value = row.get(field, 0)
                        
                        col1, col2, col3 = st.columns([3, 2, 2])
                        with col1:
                            st.markdown(f"**{rubric['label']}** `{rubric['code']}`")
                        with col2:
                            # Show field type based on name
                            if 'heures' in field or 'jours' in field:
                                new_value = st.number_input(
                                    f"Quantité",
                                    value=float(current_value),
                                    step=0.5,
                                    key=f"sal_{matricule}_{field}",
                                    label_visibility="collapsed"
                                )
                            else:
                                new_value = st.number_input(
                                    f"Montant (€)",
                                    value=float(current_value),
                                    step=10.0,
                                    key=f"sal_{matricule}_{field}",
                                    label_visibility="collapsed"
                                )
                        
                        with col3:
                            if new_value != current_value:
                                st.session_state[mod_key][field] = new_value
                                st.markdown(f"🔄 `{current_value}` → `{new_value}`")
                            else:
                                st.markdown(f"`{current_value}`")
                
                # TAB 2: SOCIAL CHARGES
                with tab2:
                    st.markdown("##### Cotisations sociales")
                    st.info("ℹ️ Les charges sont recalculées automatiquement. Modifications manuelles possibles si nécessaire.")
                    
                    charge_rubrics = get_charge_rubrics()
                    details_charges = row.get('details_charges', {})
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**Charges Salariales**")
                        charges_sal = details_charges.get('charges_salariales', {})
                        
                        for charge in charge_rubrics['salariales']:
                            current = charges_sal.get(charge['code'], 0)
                            
                            c1, c2 = st.columns([2, 1])
                            with c1:
                                st.markdown(f"**{charge['label']}** `{charge['code']}`")
                                st.caption(f"Taux: {charge['taux']}% | Plafond: {charge['plafond'] or 'Aucun'}")
                            with c2:
                                new_val = st.number_input(
                                    "€",
                                    value=float(current),
                                    step=1.0,
                                    key=f"charge_sal_{matricule}_{charge['code']}",
                                    label_visibility="collapsed"
                                )
                                if new_val != current:
                                    if 'charges_salariales' not in st.session_state[mod_key]:
                                        st.session_state[mod_key]['charges_salariales'] = {}
                                    st.session_state[mod_key]['charges_salariales'][charge['code']] = new_val
                    
                    with col2:
                        st.markdown("**Charges Patronales**")
                        charges_pat = details_charges.get('charges_patronales', {})
                        
                        for charge in charge_rubrics['patronales']:
                            current = charges_pat.get(charge['code'], 0)
                            
                            c1, c2 = st.columns([2, 1])
                            with c1:
                                st.markdown(f"**{charge['label']}** `{charge['code']}`")
                                st.caption(f"Taux: {charge['taux']}% | Plafond: {charge['plafond'] or 'Aucun'}")
                            with c2:
                                new_val = st.number_input(
                                    "€",
                                    value=float(current),
                                    step=1.0,
                                    key=f"charge_pat_{matricule}_{charge['code']}",
                                    label_visibility="collapsed"
                                )
                                if new_val != current:
                                    if 'charges_patronales' not in st.session_state[mod_key]:
                                        st.session_state[mod_key]['charges_patronales'] = {}
                                    st.session_state[mod_key]['charges_patronales'][charge['code']] = new_val
                
                # Action buttons
                st.markdown("---")
                col1, col2, col3 = st.columns([2, 2, 3])
                
                with col1:
                    if st.button("🔄 Recalculer", key=f"recalc_{matricule}", type="primary"):
                        if st.session_state[mod_key]:
                            try:
                                # Recalculate with modifications
                                updated = recalculate_employee_payslip(
                                    row.to_dict(), 
                                    st.session_state[mod_key]
                                )
                                
                                # Update DataFrame
                                for key, value in updated.items():
                                    df.at[idx, key] = value
                                
                                st.session_state.processed_data = df
                                st.success("✅ Recalcul effectué!")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Erreur lors du recalcul: {str(e)}")
                        else:
                            st.warning("Aucune modification à appliquer")
                
                with col2:
                    reason = st.text_input("Motif de modification", key=f"reason_{matricule}")
                    if st.button("💾 Sauvegarder", key=f"save_{matricule}"):
                        if not reason:
                            st.error("Le motif est obligatoire")
                        elif not st.session_state[mod_key]:
                            st.warning("Aucune modification à sauvegarder")
                        else:
                            # Log all modifications
                            for field, new_value in st.session_state[mod_key].items():
                                old_value = row.get(field, None)
                                log_modification(
                                    matricule, field, old_value, new_value,
                                    st.session_state.user, reason
                                )
                            
                            # Save to consolidated data
                            month, year = map(int, st.session_state.current_period.split('-'))
                            st.session_state.payroll_system.data_consolidator.save_period_data(
                                df, st.session_state.current_company, month, year
                            )
                            
                            st.success("✅ Modifications sauvegardées!")
                            st.session_state[mod_key] = {}
                            st.session_state[edit_key] = False
                            st.rerun()
            
            # VALIDATION BUTTONS (always visible)
            else:
                col1, col2 = st.columns([1, 3])
                with col1:
                    if not is_validated:
                        if st.button("✅ Valider", key=f"validate_{matricule}", type="primary"):
                            df.at[idx, 'statut_validation'] = True
                            df.at[idx, 'edge_case_flag'] = False
                            
                            # Remove from edge cases
                            st.session_state.edge_cases = [
                                ec for ec in edge_cases 
                                if ec['matricule'] != matricule
                            ]
                            
                            # Save
                            month, year = map(int, st.session_state.current_period.split('-'))
                            st.session_state.payroll_system.data_consolidator.save_period_data(
                                df, st.session_state.current_company, month, year
                            )
                            
                            st.success(f"✅ Fiche validée pour {row['nom']} {row['prenom']}")
                            st.rerun()
                    else:
                        st.success("✅ Déjà validé")

def audit_log_page():
    """View audit trail of modifications"""
    st.header("📋 Journal des Modifications")
    
    if st.session_state.role != 'admin':
        st.error("Accès réservé aux administrateurs")
        return
    
    import json
    from pathlib import Path
    from datetime import datetime
    
    log_dir = Path("data/audit_logs")
    if not log_dir.exists():
        st.info("Aucune modification enregistrée")
        return
    
    # Load all logs
    all_logs = []
    for log_file in log_dir.glob("*.jsonl"):
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    all_logs.append(json.loads(line))
                except:
                    pass
    
    if not all_logs:
        st.info("Aucune modification enregistrée")
        return
    
    # Convert to DataFrame
    logs_df = pd.DataFrame(all_logs)
    logs_df['timestamp'] = pd.to_datetime(logs_df['timestamp'])
    logs_df = logs_df.sort_values('timestamp', ascending=False)
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        user_filter = st.selectbox("Utilisateur", ["Tous"] + list(logs_df['user'].unique()))
    with col2:
        period_filter = st.selectbox("Période", ["Toutes"] + list(logs_df['period'].unique()))
    with col3:
        matricule_filter = st.text_input("Matricule")
    
    # Apply filters
    filtered = logs_df.copy()
    if user_filter != "Tous":
        filtered = filtered[filtered['user'] == user_filter]
    if period_filter != "Toutes":
        filtered = filtered[filtered['period'] == period_filter]
    if matricule_filter:
        filtered = filtered[filtered['matricule'].str.contains(matricule_filter, case=False)]
    
    st.metric("Total modifications", len(filtered))
    
    # Display
    st.dataframe(
        filtered[['timestamp', 'user', 'matricule', 'field', 'old_value', 'new_value', 'reason']],
        use_container_width=True
    )

def clean_employee_data_for_pdf(employee_dict: Dict) -> Dict:
    """Clean employee data to ensure numeric fields are not dicts"""
    import numpy as np
    
    numeric_fields = [
        'salaire_brut', 'salaire_base', 'salaire_net', 
        'total_charges_salariales', 'total_charges_patronales',
        'heures_sup_125', 'heures_sup_150', 'prime',
        'montant_hs_125', 'montant_hs_150', 'cout_total_employeur',
        'taux_horaire', 'base_heures', 'heures_payees',
        'retenue_absence', 'heures_absence', 'indemnite_cp',
        'heures_jours_feries', 'montant_jours_feries',
        'cumul_brut', 'cumul_base_ss', 'cumul_net_percu',
        'cumul_charges_sal', 'cumul_charges_pat',
        'jours_cp_pris', 'tickets_restaurant'
    ]
    
    cleaned = {}
    
    # Copy all fields
    for key, value in employee_dict.items():
        if key in numeric_fields:
            # Force numeric conversion
            if isinstance(value, dict):
                cleaned[key] = 0
            elif isinstance(value, (list, tuple)):
                cleaned[key] = 0
            elif pd.isna(value) or value is None:
                cleaned[key] = 0
            elif isinstance(value, (int, float, np.integer, np.floating)):
                cleaned[key] = float(value)
            else:
                try:
                    cleaned[key] = float(value)
                except (TypeError, ValueError, AttributeError):
                    cleaned[key] = 0
        else:
            # Keep non-numeric fields as-is
            cleaned[key] = value
    
    return cleaned

def pdf_generation_page():
    """Page de génération des PDFs"""
    st.header("📄 Génération des PDFs")
    
    if not st.session_state.current_company or not st.session_state.current_period:
        st.warning("Sélectionnez une entreprise et une période")
        return
    
    system = st.session_state.payroll_system
    period_parts = st.session_state.current_period.split('-')
    month = int(period_parts[0])
    year = int(period_parts[1])

    df = system.data_consolidator.load_period_data(st.session_state.current_company, month, year)

    if df.empty:
        st.warning("Aucune donnée pour cette période. Lancez d'abord l'import des données.")
        return
    
    # Check if data has been processed (has calculated fields)
    if 'salaire_brut' not in df.columns:
        st.warning("Les données n'ont pas été traitées. Lancez d'abord le traitement des paies.")
        return
    
    # Initialize PDF service
    company_info = system.company_info
    pdf_service = PDFGeneratorService(company_info)
    
    # Create unique key for current company/period
    pdf_key = f"{st.session_state.current_company}_{month:02d}_{year}"
    
    # Initialize PDF storage for this key if not exists
    if pdf_key not in st.session_state.generated_pdfs:
        st.session_state.generated_pdfs[pdf_key] = {}
    
    st.subheader("Options de génération PDF")
    st.info(f"**{len(df)} employés** traités pour la période {st.session_state.current_period}")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📄 Bulletin individuel", 
        "📚 Tous les bulletins", 
        "📊 Journal de paie", 
        "💰 Provision CP"
    ])
    
    with tab1:
        st.info("📄 Générer le bulletin de paie d'un employé spécifique")
        
        # Employee selection
        employees = df[['matricule', 'nom', 'prenom']].to_dict('records')
        employee_options = [f"{emp['matricule']} - {emp['nom']} {emp['prenom']}" for emp in employees]
        
        selected_employee = st.selectbox("Sélectionner un employé", employee_options)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📄 Générer bulletin individuel", type="primary", use_container_width=True):
                if selected_employee:
                    try:
                        # Extract matricule from selection
                        matricule = selected_employee.split(' - ')[0]
                        employee_data = clean_employee_data_for_pdf(
                            df[df['matricule'] == matricule].iloc[0].to_dict()
                        )
                    
                        # Add period information for PDF generation
                        last_day = calendar.monthrange(year, month)[1]

                        employee_data['period_start'] = f"01/{month:02d}/{year}"
                        employee_data['period_end'] = f"{last_day:02d}/{month:02d}/{year}"
                        employee_data['payment_date'] = f"{last_day:02d}/{month:02d}/{year}"
                        
                        # Generate PDF
                        with st.spinner("Génération du bulletin en cours..."):
                            pdf_buffer = pdf_service.generate_email_ready_paystub(
                                employee_data, 
                                f"{month:02d}-{year}"
                            )
                        
                        # Store in session state
                        st.session_state.generated_pdfs[pdf_key][f'bulletin_{matricule}'] = {
                            'buffer': pdf_buffer.getvalue(),
                            'filename': f"bulletin_{matricule}_{year}_{month:02d}.pdf",
                            'generated_at': datetime.now()
                        }
                        
                        st.success("✅ Bulletin généré avec succès!")
                        
                    except Exception as e:
                        st.error(f"Erreur lors de la génération: {str(e)}")
        
        with col2:
            # Check if individual bulletin exists in session state
            bulletin_key = f"bulletin_{selected_employee.split(' - ')[0]}" if selected_employee else None
            if bulletin_key and bulletin_key in st.session_state.generated_pdfs[pdf_key]:
                pdf_data = st.session_state.generated_pdfs[pdf_key][bulletin_key]
                st.download_button(
                    label="💾 Télécharger le bulletin",
                    data=pdf_data['buffer'],
                    file_name=pdf_data['filename'],
                    mime="application/pdf",
                    use_container_width=True
                )
    
    with tab2:
        st.info("📚 Générer tous les bulletins de paie")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Bulletins à générer", len(df))
        with col2:
            total_size_est = len(df) * 0.2  # Estimation 200KB par bulletin
            st.metric("Taille estimée", f"{total_size_est:.1f} MB")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📚 Générer tous les bulletins", type="primary", use_container_width=True):
                try:
                    with st.spinner("Génération de tous les bulletins en cours..."):
                        # Add period information to all employees
                        last_day = calendar.monthrange(year, month)[1]

                        df_copy = df.copy()
                        df_copy['period_start'] = f"01/{month:02d}/{year}"
                        df_copy['period_end'] = f"{last_day:02d}/{month:02d}/{year}"
                        df_copy['payment_date'] = f"{last_day:02d}/{month:02d}/{year}"
                        
                        # Clean each row before generating PDFs
                        cleaned_data = []
                        for _, row in df_copy.iterrows():
                            cleaned_data.append(clean_employee_data_for_pdf(row.to_dict()))
                        df_copy = pd.DataFrame(cleaned_data)
                        documents = pdf_service.generate_monthly_documents(df_copy, f"{month:02d}-{year}")
                        
                        if 'paystubs' in documents:
                            # Create a zip file with all paystubs
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                for paystub in documents['paystubs']:
                                    filename = f"bulletin_{paystub['matricule']}_{paystub['nom']}_{paystub['prenom']}.pdf"
                                    zip_file.writestr(filename, paystub['buffer'].getvalue())
                            
                            # Store in session state
                            st.session_state.generated_pdfs[pdf_key]['all_bulletins'] = {
                                'buffer': zip_buffer.getvalue(),
                                'filename': f"bulletins_{st.session_state.current_company}_{year}_{month:02d}.zip",
                                'generated_at': datetime.now(),
                                'count': len(documents['paystubs'])
                            }
                            
                            st.success(f"✅ {len(documents['paystubs'])} bulletins générés avec succès!")
                        else:
                            st.error("Erreur lors de la génération des bulletins")
                            
                except Exception as e:
                    st.error(f"Erreur lors de la génération: {str(e)}")
        
        with col2:
            # Check if all bulletins exist in session state
            if 'all_bulletins' in st.session_state.generated_pdfs[pdf_key]:
                pdf_data = st.session_state.generated_pdfs[pdf_key]['all_bulletins']
                st.download_button(
                    label=f"💾 Télécharger {pdf_data.get('count', '')} bulletins (ZIP)",
                    data=pdf_data['buffer'],
                    file_name=pdf_data['filename'],
                    mime="application/zip",
                    use_container_width=True
                )
    
    with tab3:
        st.info("📊 Générer le journal de paie")
        
        # Show summary stats
        col1, col2, col3 = st.columns(3)
        with col1:
            total_brut = df['salaire_brut'].sum()
            st.metric("Masse salariale brute", f"{total_brut:,.0f} €")
        with col2:
            total_net = df['salaire_net'].sum()
            st.metric("Total net à payer", f"{total_net:,.0f} €")
        with col3:
            total_charges_pat = df['total_charges_patronales'].sum()
            st.metric("Charges patronales", f"{total_charges_pat:,.0f} €")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 Générer journal de paie", type="primary", use_container_width=True):
                try:
                    with st.spinner("Génération du journal en cours..."):
                        employees_data = df.to_dict('records')
                        journal_buffer = pdf_service.journal_generator.generate_pay_journal(
                            employees_data, 
                            f"{month:02d}-{year}"
                        )
                    
                    # Store in session state
                    st.session_state.generated_pdfs[pdf_key]['journal'] = {
                        'buffer': journal_buffer.getvalue(),
                        'filename': f"journal_paie_{st.session_state.current_company}_{month:02d}_{year}.pdf",
                        'generated_at': datetime.now()
                    }
                    
                    st.success("✅ Journal de paie généré avec succès!")
                    
                except Exception as e:
                    st.error(f"Erreur lors de la génération: {str(e)}")
        
        with col2:
            # Check if journal exists in session state
            if 'journal' in st.session_state.generated_pdfs[pdf_key]:
                pdf_data = st.session_state.generated_pdfs[pdf_key]['journal']
                st.download_button(
                    label="💾 Télécharger le journal de paie",
                    data=pdf_data['buffer'],
                    file_name=pdf_data['filename'],
                    mime="application/pdf",
                    use_container_width=True
                )
    
    with tab4:
        st.info("💰 Générer la provision pour congés payés")
        
        st.markdown("""
        **Informations sur la provision CP:**
        - Calcul basé sur les droits acquis et non pris
        - Inclut les charges sociales estimées (45% de majoration)
        - Document comptable pour l'arrêté des comptes
        """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💰 Générer provision CP", type="primary", use_container_width=True):
                try:
                    with st.spinner("Génération de la provision en cours..."):
                        # Prepare provisions data
                        period_date = datetime(year, month, 1)
                        provisions_data = pdf_service._prepare_provisions_data(df, period_date)
                        
                        pto_buffer = pdf_service.pto_generator.generate_pto_provision(
                            provisions_data, 
                            f"{month:02d}-{year}"
                        )
                    
                    # Calculate total provision for display
                    total_provision = sum(p.get('provision_amount', 0) for p in provisions_data)
                    
                    # Store in session state
                    st.session_state.generated_pdfs[pdf_key]['provision_cp'] = {
                        'buffer': pto_buffer.getvalue(),
                        'filename': f"provision_cp_{st.session_state.current_company}_{year}_{month:02d}.pdf",
                        'generated_at': datetime.now(),
                        'total': total_provision
                    }
                    
                    st.success(f"✅ Provision générée avec succès!")
                    st.info(f"**Provision totale:** {total_provision:,.2f} €")
                    
                except Exception as e:
                    st.error(f"Erreur lors de la génération: {str(e)}")
        
        with col2:
            # Check if provision exists in session state
            if 'provision_cp' in st.session_state.generated_pdfs[pdf_key]:
                pdf_data = st.session_state.generated_pdfs[pdf_key]['provision_cp']
                if 'total' in pdf_data:
                    st.info(f"**Provision totale:** {pdf_data['total']:,.2f} €")
                st.download_button(
                    label="💾 Télécharger provision CP",
                    data=pdf_data['buffer'],
                    file_name=pdf_data['filename'],
                    mime="application/pdf",
                    use_container_width=True
                )
    
    # Add some helpful information at the bottom
    st.markdown("---")
    
    # Show status of generated PDFs
    if pdf_key in st.session_state.generated_pdfs and st.session_state.generated_pdfs[pdf_key]:
        st.success(f"📁 **PDFs disponibles pour téléchargement:**")
        for doc_type, doc_data in st.session_state.generated_pdfs[pdf_key].items():
            if isinstance(doc_data, dict) and 'generated_at' in doc_data:
                st.write(f"- {doc_data['filename']} (généré à {doc_data['generated_at'].strftime('%H:%M:%S')})")
    
    st.info("""
    💡 **Conseils pour la génération PDF:**
    - Les bulletins individuels sont générés au format réglementaire Monaco
    - Le journal de paie contient les écritures comptables
    - La provision CP est calculée selon la législation sociale monégasque  
    - Tous les documents sont horodatés et numérotés
    - Les PDFs générés restent disponibles jusqu'au changement de période
    """)

def export_page():
    """Page d'export des résultats"""
    st.header("📄 Exporter les résultats")
    
    if not st.session_state.current_company or not st.session_state.current_period:
        st.warning("Sélectionnez une entreprise et une période")
        return
    
    system = st.session_state.payroll_system
    year, month = map(int, st.session_state.current_period.split('-'))
    
    df = system.data_consolidator.load_period_data(st.session_state.current_company, year, month)
    
    if df.empty:
        st.warning("Aucune donnée à exporter. Lancez d'abord le traitement des paies.")
        return

    tab1, tab2 = st.tabs(["Exporter par Excel", "Voir le Rapport"])

    with tab1:
        st.info("📊 **Export Excel**")
        if st.button("Générer Excel", use_container_width=True):
            output = io.BytesIO()
            
            if HAS_EXCEL:
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, sheet_name='Paies', index=False)
                    
                    summary_data = {
                        'Statistiques': ['Nombre de salariés', 'Masse salariale brute', 
                                       'Total charges salariales', 'Total charges patronales'],
                        'Valeurs': [
                            len(df),
                            df['salaire_brut'].sum() if 'salaire_brut' in df.columns else 0,
                            df['total_charges_salariales'].sum() if 'total_charges_salariales' in df.columns else 0,
                            df['total_charges_patronales'].sum() if 'total_charges_patronales' in df.columns else 0
                        ]
                    }
                    
                    summary_df = pd.DataFrame(summary_data)
                    summary_df.to_excel(writer, sheet_name='Synthèse', index=False)
            else:
                df.to_csv(output, index=False)
            
            st.download_button(
                label="📥 Télécharger",
                data=output.getvalue(),
                file_name=f"paies_{st.session_state.current_company}_{st.session_state.current_period}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if HAS_EXCEL else "text/csv"
            )
    
    with tab2:
        st.info("📋 **Rapport de synthèse**")
        if st.button("Voir rapport", use_container_width=True):
            st.markdown("---")
            st.subheader("Rapport de synthèse")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Statistiques générales:**")
                st.write(f"- Nombre total d'employés: {len(df)}")
                st.write(f"- Fiches validées: {(df['statut_validation'] == 'Validé').sum() if 'statut_validation' in df.columns else 0}")
                st.write(f"- Cas à vérifier: {df['edge_case_flag'].sum() if 'edge_case_flag' in df.columns else 0}")
            
            with col2:
                st.write("**Statistiques financières:**")
                if 'salaire_brut' in df.columns:
                    st.write(f"- Masse salariale brute: {df['salaire_brut'].sum():,.2f} €")
                if 'salaire_net' in df.columns:
                    st.write(f"- Total net à payer: {df['salaire_net'].sum():,.2f} €")
                if 'total_charges_patronales' in df.columns:
                    st.write(f"- Charges patronales: {df['total_charges_patronales'].sum():,.2f} €")

# ============================================================================
# ADMIN USER MANAGEMENT
# ============================================================================
def admin_panel():
    if st.session_state.get("role") != "admin":
        st.error("Accès réservé aux administrateurs.")
        return

    st.title("Admin • Users")

    # List users
    with st.expander("Current users", expanded=True):
        users = AuthManager.list_users()
        if not users:
            st.info("No users yet.")
        else:
            c1,c2,c3,c4 = st.columns([2,2,1,2])
            c1.markdown("**Username**")
            c2.markdown("**Name**")
            c3.markdown("**Role**")
            c4.markdown("**Created**")
            for u in sorted(users, key=lambda x: x["username"]):
                c1.write(u["username"])
                c2.write(u.get("name",""))
                c3.write(u.get("role","comptable"))
                c4.write(u.get("created_at",""))

    st.divider()

    # Add / reset user
    st.subheader("Ajouter / Réinitialiser un utilisateur")
    with st.form("add_reset_user", clear_on_submit=False):
        username = st.text_input("Nom d'utilisateur")
        name     = st.text_input("Nom (facultatif)")
        role     = st.selectbox("Rôle", options=["comptable","admin"])
        password = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Enregistrer / Mettre à jour"):
            if not username or not password:
                st.error("Le nom d'utilisateur et le mot de passe sont requis.")
            else:
                try:
                    AuthManager.add_or_update_user(username, password, role, name)
                    st.success(f"Utilisateur '{username}' enregistré.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    # Remove users
    st.subheader("Supprimer des utilisateurs")
    existing = [u["username"] for u in AuthManager.list_users()]
    sel = st.multiselect("Sélectionner les utilisateurs à supprimer", options=existing)
    if st.button("Supprimer la sélection"):
        if not sel:
            st.warning("Aucun utilisateur sélectionné.")
        else:
            AuthManager.remove_users(sel)
            st.success(f"Supprimé : {', '.join(sel)}")
            st.rerun()

def config_page():
    """Page de configuration (admin seulement)"""
    st.header("⚙️ Configuration")
    
    if st.session_state.role != 'admin':
        st.error("Accès réservé aux administrateurs")
        return
    
    system = st.session_state.payroll_system
    
    tab1, tab2, tab3, tab4 = st.tabs(["Entreprise", "Utilisateurs", "Paramètres", "Admin"])
    
    with tab1:
        st.subheader("Informations de l'entreprise")
        
        with st.form("company_form"):
            name = st.text_input("Nom de l'entreprise", value=system.company_info.get('name', ''))
            siret = st.text_input("SIRET", value=system.company_info.get('siret', ''))
            address = st.text_area("Adresse", value=system.company_info.get('address', ''))
            phone = st.text_input("Téléphone", value=system.company_info.get('phone', ''))
            email = st.text_input("Email", value=system.company_info.get('email', ''))
            
            if st.form_submit_button("💾 Sauvegarder"):
                updated_info = {
                    'name': name,
                    'siret': siret,
                    'address': address,
                    'phone': phone,
                    'email': email
                }
                
                config_file = CONFIG_DIR / "company_info.json"
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(updated_info, f, indent=2)
                
                system.company_info = updated_info
                st.success("Informations mises à jour")
    
    with tab2:
        st.subheader("Gestion des utilisateurs")
        
        # Use the new AuthManager
        users = AuthManager.list_users()
        if users:
            users_df = pd.DataFrame(users)
            st.dataframe(users_df[['username', 'name', 'role']], use_container_width=True)
        else:
            st.info("Aucun utilisateur trouvé")
            
        # Show security stats
        stats = AuthManager.get_stats()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total utilisateurs", stats.get('total_users', 0))
        with col2:
            st.metric("Administrateurs", stats.get('admin_users', 0))
        with col3:
            st.metric("Comptables", stats.get('comptable_users', 0))

    
    with tab3:
        st.subheader("Paramètres système")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Paramètres de calcul Monaco**")
            plafond_ss = st.number_input("Plafond Sécurité Sociale T1", value=3428.00)
            smic_horaire = st.number_input("SMIC horaire", value=11.65)
            base_heures = st.number_input("Base heures légale", value=169.00)
        
        with col2:
            st.write("**Taux de cotisations**")
            st.info("Les taux sont définis selon la législation monégasque 2024")
            st.write("CAR Salarial: 6.85%")
            st.write("CAR Patronal: 8.35%")
            st.write("CCSS: 14.75%")
            st.write("CMRC: 5.22%")

    with tab4:
        # Include the full admin panel in the configuration
        admin_panel()

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    if not st.session_state.authenticated:
        login_page()
    else:
        main_app()
