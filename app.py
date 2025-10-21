"""
Monaco Payroll System - Complete Consolidated Application
=========================================================
Système complet de gestion des paies pour Monaco
Version consolidée avec tous les modules intégrés

source monaco_paie/bin/activate
source .venv/bin/activate
streamlit run app.py

modifier que les 2 dernieres paies sauf si nouvelle societe

ajouter un menu en dessous de la validation pour rajouter des lignes dans le bulletin de paie avec un drop down menu des rubriques
ajouter une ligne de regularisation pour les charges sociales, et base seulement pour les charges
"""

from duckdb import df
import streamlit as st
import polars as pl
from xlsxwriter import Workbook
import numpy as np
from datetime import datetime, date, timedelta, time
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
from services.auth import AuthManager
from services.pdf_generation import PDFGeneratorService
from services.payroll_system import IntegratedPayrollSystem
from services.dsm_xml_generator import DSMXMLGenerator
from services.data_mgt import (
    DataManager,
    DataConsolidation
)
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
from services.email_archive import (
    EmailDistributionService,
    EmailConfig,
    EmailConfigManager,
    PDFArchiveManager,
    ComplianceAuditLogger,
    EmailTemplate,
    create_email_distribution_system
)
from services.oauth2_integration import (
    OAuth2Config,
    OAuth2EmailManager,
    MicrosoftOAuth2Service
)
from services.payslip_helpers import (
    get_salary_rubrics,
    get_all_available_salary_rubrics,
    get_available_rubrics_for_employee,
    get_charge_rubrics,
    get_available_charges_for_employee,
    log_modification,
    recalculate_employee_payslip,
    clean_employee_data_for_pdf,
    safe_get_charge_value,
    safe_get_numeric,
    audit_log_page,
    _show_read_only_validation
)
from services.edge_case_agent import (
    EdgeCaseAgent,
    EdgeCaseReport,
    EdgeCaseModification,
    RemarkParser
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

DataManager.init_schema()

# Custom CSS
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
    st.session_state.polars_mode = True 

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
            "📄 Déclaration DSM Monaco": "dsm_declaration",
            "📧 Envoi Validation Client": "send_validation_email",
            "📄 Export des résultats": "export"
        }

        if st.session_state.role == "admin":
            pages["⚙️ Configuration Email"] = "email_config"
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
    elif current_page == "dsm_declaration":
        dsm_declaration_page()
    elif current_page == "send_validation_email":
        send_validation_email_page()
    elif current_page == "export":
        export_page()
    elif current_page == "email_config":
        email_config_page()
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
    df = pl.DataFrame(df) if not isinstance(df, pl.DataFrame) else df

    if df.is_empty():
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
        total_brut = df.select(pl.col('salaire_brut').sum()).item() if 'salaire_brut' in df.columns else 0
        st.markdown(metrics_style.format("MASSE SALARIALE", f"{total_brut:,.0f} €"), unsafe_allow_html=True)

    with col3:
        edge_cases = df.select(pl.col('edge_case_flag').sum()).item() if 'edge_case_flag' in df.columns else 0
        st.markdown(metrics_style.format("CAS À VÉRIFIER", edge_cases), unsafe_allow_html=True)

    with col4:
        validated = df.filter(pl.col('statut_validation') == True).height if 'statut_validation' in df.columns else 0
        st.markdown(metrics_style.format("VALIDÉES", f"{validated}/{len(df)}"), unsafe_allow_html=True)
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Répartition par statut")
        if 'statut_validation' in df.columns:
            status_counts = df.group_by('statut_validation').agg(pl.count()).to_pandas()
            st.bar_chart(status_counts.set_index('statut_validation')['count'])
    
    with col2:
        st.subheader("Distribution des salaires nets")
        if 'salaire_net' in df.columns and not df['salaire_net'].is_null().all():
            fig_data = df.select(pl.col('salaire_net').cast(pl.Float64).drop_nulls())

            # Create histogram using Polars with allow_duplicates to handle duplicate salary values
            try:
                hist_df = fig_data.select(
                    pl.col('salaire_net').qcut(10, labels=[f"{i}" for i in range(10)], allow_duplicates=True)
                    .alias('bin')
                ).group_by('bin').agg(pl.count().alias('count'))

                chart_data = hist_df.sort('bin').to_pandas().set_index('bin')['count']
                st.bar_chart(chart_data)
            except Exception as e:
                # Fallback to simple histogram if qcut fails
                st.info("Pas assez de données uniques pour créer un histogramme détaillé")
                st.write(fig_data.select(pl.col('salaire_net').describe()).to_pandas())
    
    st.markdown("---")
    st.subheader("Employés avec cas particuliers")
    
    if 'edge_case_flag' in df.columns:
        edge_cases_df = df.filter(pl.col('edge_case_flag') == True)
        if not edge_cases_df.is_empty():
            display_cols = ['matricule', 'nom', 'prenom']
            if 'salaire_brut' in edge_cases_df.columns:
                display_cols.append('salaire_brut')
            if 'edge_case_reason' in edge_cases_df.columns:
                display_cols.append('edge_case_reason')
            
            st.dataframe(edge_cases_df.select(display_cols).to_pandas(), use_container_width=True)
        else:
            st.success("Aucun cas particulier détecté")

def import_page():
    """Page d'import des données"""
    st.header("📥 Import des données")
    
    if not st.session_state.current_company or not st.session_state.current_period:
        st.warning("Sélectionnez une entreprise et une période")
        return
    
    system = st.session_state.payroll_system
    
    tab1, tab2 = st.tabs(["Importer un Excel", "Télécharger le Modèle"])
    
    with tab1:
        st.subheader("Importer les données depuis Excel")
        
        uploaded_file = st.file_uploader(
            "Choisir un fichier Excel",
            type=['xlsx', 'xls', 'csv'],
            help="Le fichier doit respecter le format du modèle",
        )
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    # Specify dtypes to preserve leading zeros in matricule
                    dtypes = {"Matricule": pl.Utf8}
                    df_import = pl.read_csv(uploaded_file, dtypes=dtypes)
                    # Apply column mapping
                    df_import = df_import.rename(system.excel_manager.EXCEL_COLUMN_MAPPING)
                else:
                    # Excel handling - specify schema to preserve leading zeros
                    schema_overrides = {"Matricule": pl.Utf8}
                    df_import = pl.read_excel(uploaded_file, schema_overrides=schema_overrides)

                # Ensure matricule is string after any processing
                if 'matricule' in df_import.columns:
                    df_import = df_import.with_columns(
                        pl.col('matricule').cast(pl.Utf8, strict=False)
                    )
                
                st.success(f"✅ {len(df_import)} employés importés avec succès")
                
                st.subheader("Aperçu des données importées")
                st.dataframe(df_import.head(10), use_container_width=True) # .to_pandas()
                
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
            <div style="font-weight: 500; margin-bottom: 0.5rem;">Traitement automatique intelligent</div>
            <div style="color: #6c757d; font-size: 0.9rem;">
                • Calcul des salaires selon la législation monégasque<br>
                • Analyse intelligente des remarques et cas particuliers<br>
                • Comparaison avec le mois précédent<br>
                • Corrections automatiques (confiance ≥95%)<br>
                • Détection d'anomalies et erreurs de saisie
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Edge case agent configuration
    st.markdown("### ⚙️ Configuration de l'agent")
    col1, col2 = st.columns(2)
    with col1:
        enable_agent = st.checkbox("Activer l'agent de traitement intelligent", value=True,
                                   help="L'agent analysera automatiquement les cas particuliers et effectuera des corrections avec haute confiance")
    with col2:
        send_email = st.checkbox("Envoyer le rapport par email", value=False,
                                help="Envoyer un résumé des modifications au comptable")

    if send_email:
        accountant_email = st.text_input("Email du comptable",
                                         value="comptable@example.com",
                                         help="Email pour recevoir le rapport de traitement")

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

            # Run edge case agent if enabled
            if enable_agent and 'processed_data' in st.session_state:
                with st.spinner("🤖 Analyse intelligente des cas particuliers..."):
                    df = st.session_state.processed_data
                    df = pl.DataFrame(df) if not isinstance(df, pl.DataFrame) else df

                    # Initialize agent
                    agent = EdgeCaseAgent(system.data_consolidator)

                    # Process payroll with agent
                    month, year = map(int, st.session_state.current_period.split('-'))
                    modified_df, agent_report = agent.process_payroll(df, st.session_state.current_company, month, year)

                    # Update processed data
                    st.session_state.processed_data = modified_df

                    # Save modified data
                    system.data_consolidator.save_period_data(
                        modified_df,
                        st.session_state.current_company,
                        month,
                        year
                    )

                    # Store agent report in session
                    st.session_state.edge_case_report = agent_report

                    # Show agent results
                    st.markdown("---")
                    st.subheader("🤖 Rapport de l'Agent Intelligent")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Modifications automatiques", agent_report.automatic_count,
                                 help="Corrections effectuées avec confiance ≥95%")
                    with col2:
                        st.metric("Cas signalés", agent_report.flagged_count,
                                 help="Cas nécessitant une révision manuelle")
                    with col3:
                        st.metric("Anomalies détectées", len(agent_report.anomalies),
                                 help="Variations importantes (>15%) détectées")

                    # Show automatic modifications
                    if agent_report.modifications:
                        with st.expander(f"📝 Modifications automatiques ({agent_report.automatic_count})", expanded=True):
                            auto_mods = [m for m in agent_report.modifications if m.automatic]
                            if auto_mods:
                                for mod in auto_mods:
                                    st.success(f"""
                                    **{mod.employee_name}** ({mod.matricule})
                                    {mod.field}: {mod.old_value:.2f} → {mod.new_value:.2f}
                                    ✓ {mod.reason} (Confiance: {mod.confidence*100:.0f}%)
                                    """)

                    # Show flagged cases
                    if agent_report.flagged_cases:
                        with st.expander(f"⚠️ Cas signalés pour révision ({agent_report.flagged_count})", expanded=True):
                            for case in agent_report.flagged_cases:
                                st.warning(f"""
                                **{case['employee_name']}** ({case['matricule']})
                                {case['reason']}
                                Remarque: {case.get('remark', 'N/A')}
                                """)

                    # Send email if requested
                    if send_email and accountant_email:
                        try:
                            # Try to get SMTP config from session or use defaults
                            smtp_config = st.session_state.get('smtp_config', {
                                'smtp_server': 'smtp.gmail.com',
                                'smtp_port': 587,
                                'sender_email': 'paie@example.com',
                                'sender_password': 'password',
                                'sender_name': 'Service Paie Monaco'
                            })

                            # Note: Email sending will need proper SMTP configuration
                            st.info("📧 Configuration email requise pour l'envoi automatique. Consultez la page de configuration.")

                            # Generate email preview
                            email_data = agent.generate_email_summary(accountant_email)
                            with st.expander("📧 Aperçu de l'email"):
                                st.markdown(f"**À:** {email_data['to']}")
                                st.markdown(f"**Sujet:** {email_data['subject']}")
                                st.markdown("---")
                                st.markdown(email_data['html_body'], unsafe_allow_html=True)
                        except Exception as e:
                            st.warning(f"Impossible de générer l'email: {e}")


            st.markdown("---")
            st.subheader("Résultats du traitement")

            if 'processed_data' in st.session_state:
                df = st.session_state.processed_data
                df = pl.DataFrame(df) if not isinstance(df, pl.DataFrame) else df
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Fiches traitées", len(df))

                with col2:
                    validated = df.filter(pl.col('statut_validation') == True).height
                    st.metric("Validées automatiquement", f"{validated} ({validated/len(df)*100:.1f}%)")

                with col3:
                    edge_cases = df.select(pl.col('edge_case_flag').sum()).item()
                    st.metric("Cas à vérifier", edge_cases)
        else:
            st.error(f"Erreur: {report.get('error', 'Erreur inconnue')}")

def validation_page():
    """Page de validation des cas particuliers avec édition - restricted to last 2 periods"""
    st.header("✅ Validation et Modification des Paies")
    
    if not st.session_state.current_company or not st.session_state.current_period:
        st.warning("Sélectionnez une entreprise et une période")
        return
    
    # CHECK PERIOD EDIT PERMISSION
    is_new_company = AuthManager.is_new_company(st.session_state.current_company)
    available_periods = DataManager.get_available_period_strings(st.session_state.current_company)
    
    if not is_new_company:
        # Not a new company - restrict to last 2 periods
        if len(available_periods) < 2:
            editable_periods = available_periods
        else:
            editable_periods = available_periods[:2]  # Most recent 2 periods
        
        current_period = st.session_state.current_period
        can_edit = current_period in editable_periods
        
        if not can_edit:
            st.error(f"""
            ⚠️ **Modification interdite pour cette période**
            
            Les modifications ne sont autorisées que pour les **2 dernières périodes**.
            
            **Périodes modifiables actuellement:**
            {', '.join(editable_periods) if editable_periods else 'Aucune'}
            
            **Période sélectionnée:** {current_period}
            
            Pour modifier cette période, veuillez contacter l'administrateur.
            """)
            
            # Show view-only mode
            st.info("Mode consultation uniquement pour cette période")
            _show_read_only_validation()
            return
        else:
            # Show which periods are editable
            st.info(f"""
            **Modification autorisée**
            
            Périodes modifiables: {', '.join(editable_periods)}
            """)
    else:
        # Show company age for transparency
        age_months = DataManager.get_company_age_months(st.session_state.current_company)
        if age_months is not None:
            st.success(f"""
            **Nouvelle entreprise détectée** (créée il y a {age_months:.1f} mois)
            
            Toutes les périodes sont modifiables pour les nouvelles entreprises.
            """)
        else:
            st.success("""
            **Nouvelle entreprise détectée**
            
            Toutes les périodes sont modifiables pour les nouvelles entreprises.
            """)

    if 'edge_cases' not in st.session_state:
        st.session_state.edge_cases = []
    
    if 'processed_data' not in st.session_state or st.session_state.processed_data.is_empty():
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
    
    # Apply filters using Polars
    filtered_df = df
    if search:
        filtered_df = filtered_df.filter(
            pl.col('matricule').cast(pl.Utf8).str.contains(f"(?i){search}") |
            pl.col('nom').cast(pl.Utf8).str.contains(f"(?i){search}") |
            pl.col('prenom').cast(pl.Utf8).str.contains(f"(?i){search}")
        )
    
    if status_filter == "À vérifier":
        filtered_df = filtered_df.filter(pl.col('edge_case_flag') == True)
    elif status_filter == "Validés":
        filtered_df = filtered_df.filter(pl.col('statut_validation') == True)
    
    st.markdown("---")
    
    # Display employees
    if filtered_df.is_empty():
        st.info("Aucun employé trouvé avec ces critères")
        return

    for row_idx, row in enumerate(filtered_df.iter_rows(named=True)):
        matricule = row.get('matricule', '') or ''
        is_edge_case = row.get('edge_case_flag', False)
        is_validated = row.get('statut_validation', False) == True

        # Expander title with status indicator
        status_icon = "⚠️" if is_edge_case else ("✅" if is_validated else "⏳")
        title = f"{status_icon} {row.get('nom', '')} {row.get('prenom', '')} - {matricule}"

        # Use unique key combining row index and matricule
        unique_key = f"{row_idx}_{matricule}"

        with st.expander(title, expanded=is_edge_case):
            # Initialize edit mode state
            edit_key = f"edit_mode_{unique_key}"
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
                           key=f"toggle_edit_{unique_key}"):
                    st.session_state[edit_key] = not st.session_state[edit_key]
                    st.rerun()
            
            # EDIT MODE
            if st.session_state[edit_key]:
                st.subheader("📝 Mode Édition")

                # Initialize modifications storage
                mod_key = f"modifications_{unique_key}"
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
                        current_value = safe_get_numeric(row, field, 0.0)
                        
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
                                    format="%.2f",
                                    key=f"sal_{unique_key}_{field}",
                                    label_visibility="collapsed"
                                )
                            else:
                                new_value = st.number_input(
                                    f"Montant (€)",
                                    value=float(current_value),
                                    step=10.0,
                                    format="%.2f",
                                    key=f"sal_{unique_key}_{field}",
                                    label_visibility="collapsed"
                                )
                        
                        with col3:
                            if abs(new_value - current_value) > 0.01:
                                st.session_state[mod_key][field] = new_value
                                st.markdown(f"🔄 `{current_value:.2f}` → `{new_value:.2f}`")
                            else:
                                st.markdown(f"`{current_value:.2f}`")

                    # Initialize additional rubrics storage
                    additional_rubrics_key = f"additional_rubrics_{unique_key}"
                    if additional_rubrics_key not in st.session_state:
                        st.session_state[additional_rubrics_key] = []

                    # Display additional rubrics that were added
                    for added_rubric in st.session_state[additional_rubrics_key]:
                        field = added_rubric['field']
                        current_value = safe_get_numeric(row, field, 0.0)

                        col1, col2, col3 = st.columns([3, 2, 2])
                        with col1:
                            st.markdown(f"**{added_rubric['label']}** `{added_rubric['code']}`")
                        with col2:
                            # Show field type based on name
                            if 'heures' in field or 'jours' in field:
                                new_value = st.number_input(
                                    f"Quantité",
                                    value=float(current_value),
                                    step=0.5,
                                    format="%.2f",
                                    key=f"sal_{unique_key}_{field}",
                                    label_visibility="collapsed"
                                )
                            else:
                                new_value = st.number_input(
                                    f"Montant (€)",
                                    value=float(current_value),
                                    step=10.0,
                                    format="%.2f",
                                    key=f"sal_{unique_key}_{field}",
                                    label_visibility="collapsed"
                                )

                        with col3:
                            if abs(new_value - current_value) > 0.01:
                                st.session_state[mod_key][field] = new_value
                                st.markdown(f"🔄 `{current_value:.2f}` → `{new_value:.2f}`")
                            else:
                                st.markdown(f"`{current_value:.2f}`")

                    # Dropdown to add new rubric
                    st.markdown("---")
                    st.markdown("##### ➕ Ajouter une ligne")

                    # Get available rubrics for this employee
                    available_rubrics = get_available_rubrics_for_employee(row)

                    if available_rubrics:
                        # Create dropdown options
                        rubric_options = ["-- Sélectionner une rubrique --"] + [
                            f"{r['code']} - {r['label']}" for r in available_rubrics
                        ]

                        selected = st.selectbox(
                            "Rubrique à ajouter",
                            options=rubric_options,
                            key=f"add_rubric_{unique_key}",
                            label_visibility="collapsed"
                        )

                        if selected != "-- Sélectionner une rubrique --":
                            # Find the selected rubric
                            selected_code = selected.split(" - ")[0]
                            selected_rubric = next(
                                (r for r in available_rubrics if r['code'] == selected_code),
                                None
                            )

                            if selected_rubric:
                                # Add to additional rubrics
                                if selected_rubric not in st.session_state[additional_rubrics_key]:
                                    st.session_state[additional_rubrics_key].append(selected_rubric)
                                    # Initialize the field value to 0 in modifications
                                    st.session_state[mod_key][selected_rubric['field']] = 0.0
                                    st.rerun()
                    else:
                        st.info("Toutes les rubriques disponibles sont déjà affichées")

                # TAB 2: SOCIAL CHARGES - COMBINED FORMAT
                with tab2:
                    st.markdown("##### Cotisations sociales")
                    st.info("ℹ️ Modification manuelle des charges. La base est commune pour les parts salariale et patronale.")
                    
                    # Get charge definitions
                    from services.payroll_calculations import ChargesSocialesMonaco
                    from services.pdf_generation import PaystubPDFGenerator
                    
                    details_charges = row.get('details_charges', {})
                    charges_sal = details_charges.get('charges_salariales', {})
                    charges_pat = details_charges.get('charges_patronales', {})
                    
                    # Calculate current bases
                    salaire_brut = safe_get_numeric(row, 'salaire_brut', 0)
                    plafond_t1 = min(salaire_brut, 3428)
                    base_t2 = max(0, min(salaire_brut - 3428, 13712 - 3428)) if salaire_brut > 3428 else 0
                    
                    # Initialize bases storage
                    bases_key = f"charge_bases_{unique_key}"
                    if bases_key not in st.session_state:
                        st.session_state[bases_key] = {}
                    
                    # Define charges to display in combined format
                    charges_config = [
                        {
                            'code': 'CAR',
                            'name': 'CAR',
                            'base_default': salaire_brut,
                            'taux_sal': 6.85,
                            'taux_pat': 8.35,
                            'has_salarial': True,
                            'has_patronal': True
                        },
                        {
                            'code': 'CCSS',
                            'name': 'C.C.S.S.',
                            'base_default': salaire_brut,
                            'taux_sal': 14.75,
                            'taux_pat': 0,
                            'has_salarial': True,
                            'has_patronal': False
                        },
                        {
                            'code': 'ASSEDIC_T1',
                            'name': 'Assurance Chômage T1',
                            'base_default': plafond_t1,
                            'taux_sal': 2.40,
                            'taux_pat': 4.05,
                            'has_salarial': True,
                            'has_patronal': True
                        }
                    ]
                    
                    # Add T2 charges if applicable
                    if base_t2 > 0:
                        charges_config.extend([
                            {
                                'code': 'ASSEDIC_T2',
                                'name': 'Assurance Chômage T2',
                                'base_default': base_t2,
                                'taux_sal': 2.40,
                                'taux_pat': 4.05,
                                'has_salarial': True,
                                'has_patronal': True
                            },
                            {
                                'code': 'CONTRIB_EQUILIBRE_GEN_T2',
                                'name': 'Contrib. équilibre général T2',
                                'base_default': base_t2,
                                'taux_sal': 1.08,
                                'taux_pat': 1.62,
                                'has_salarial': True,
                                'has_patronal': True
                            },
                            {
                                'code': 'RETRAITE_COMP_T2',
                                'name': 'Retraite comp. unifiée T2',
                                'base_default': base_t2,
                                'taux_sal': 8.64,
                                'taux_pat': 12.95,
                                'has_salarial': True,
                                'has_patronal': True
                            }
                        ])
                    
                    # Add other charges
                    charges_config.extend([
                        {
                            'code': 'CONTRIB_EQUILIBRE_TECH',
                            'name': 'Contrib. équilibre technique',
                            'base_default': salaire_brut,
                            'taux_sal': 0.14,
                            'taux_pat': 0.21,
                            'has_salarial': True,
                            'has_patronal': True
                        },
                        {
                            'code': 'CONTRIB_EQUILIBRE_GEN_T1',
                            'name': 'Contrib. équilibre général T1',
                            'base_default': plafond_t1,
                            'taux_sal': 0.86,
                            'taux_pat': 1.29,
                            'has_salarial': True,
                            'has_patronal': True
                        },
                        {
                            'code': 'RETRAITE_COMP_T1',
                            'name': 'Retraite comp. unifiée T1',
                            'base_default': plafond_t1,
                            'taux_sal': 3.15,
                            'taux_pat': 4.72,
                            'has_salarial': True,
                            'has_patronal': True
                        },
                        {
                            'code': 'CMRC',
                            'name': 'CMRC',
                            'base_default': salaire_brut,
                            'taux_sal': 0,
                            'taux_pat': 5.22,
                            'has_salarial': False,
                            'has_patronal': True
                        }
                    ])
                    
                    # Create header
                    st.markdown("---")
                    col_headers = st.columns([3, 1.5, 1.5, 2, 1.5, 2])
                    col_headers[0].markdown("**Cotisation**")
                    col_headers[1].markdown("**Taux Sal.**")
                    col_headers[2].markdown("**Mont. Sal.**")
                    col_headers[3].markdown("**Base**")
                    col_headers[4].markdown("**Taux Pat.**")
                    col_headers[5].markdown("**Mont. Pat.**")
                    st.markdown("---")
                    
                    # Display each charge line
                    for charge in charges_config:
                        cols = st.columns([3, 1.5, 1.5, 2, 1.5, 2])
                        
                        # Charge name
                        cols[0].markdown(f"**{charge['name']}**")
                        cols[0].caption(f"Code: {charge['code']}")
                        
                        # Get current values
                        current_sal = charges_sal.get(charge['code'], 0)
                        current_pat = charges_pat.get(charge['code'], 0)
                        current_base = st.session_state[bases_key].get(
                            charge['code'], 
                            charge['base_default']
                        )
                        
                        # Salarial rate (display only)
                        if charge['has_salarial']:
                            cols[1].markdown(f"{charge['taux_sal']:.2f}%")
                        else:
                            cols[1].markdown("-")
                        
                        # Salarial amount (editable)
                        if charge['has_salarial']:
                            new_sal = cols[2].number_input(
                                "Sal",
                                value=float(current_sal),
                                step=1.0,
                                format="%.2f",
                                key=f"charge_sal_{unique_key}_{charge['code']}",
                                label_visibility="collapsed"
                            )
                            if abs(new_sal - current_sal) > 0.01:
                                if 'charges_salariales' not in st.session_state[mod_key]:
                                    st.session_state[mod_key]['charges_salariales'] = {}
                                st.session_state[mod_key]['charges_salariales'][charge['code']] = new_sal
                        else:
                            cols[2].markdown("-")
                        
                        # Base (editable, shared between salarial and patronal)
                        new_base = cols[3].number_input(
                            "Base",
                            value=float(current_base),
                            step=100.0,
                            format="%.2f",
                            key=f"charge_base_{unique_key}_{charge['code']}",
                            label_visibility="collapsed"
                        )
                        if abs(new_base - charge['base_default']) > 0.01:
                            st.session_state[bases_key][charge['code']] = new_base
                            # Store base modification
                            if 'charge_bases' not in st.session_state[mod_key]:
                                st.session_state[mod_key]['charge_bases'] = {}
                            st.session_state[mod_key]['charge_bases'][charge['code']] = new_base
                        
                        # Patronal rate (display only)
                        if charge['has_patronal']:
                            cols[4].markdown(f"{charge['taux_pat']:.2f}%")
                        else:
                            cols[4].markdown("-")
                        
                        # Patronal amount (editable)
                        if charge['has_patronal']:
                            new_pat = cols[5].number_input(
                                "Pat",
                                value=float(current_pat),
                                step=1.0,
                                format="%.2f",
                                key=f"charge_pat_{unique_key}_{charge['code']}",
                                label_visibility="collapsed"
                            )
                            if abs(new_pat - current_pat) > 0.01:
                                if 'charges_patronales' not in st.session_state[mod_key]:
                                    st.session_state[mod_key]['charges_patronales'] = {}
                                st.session_state[mod_key]['charges_patronales'][charge['code']] = new_pat
                        else:
                            cols[5].markdown("-")
                    
                    # Totals row
                    st.markdown("---")
                    total_cols = st.columns([3, 1.5, 1.5, 2, 1.5, 2])
                    total_cols[0].markdown("**TOTAL**")
                    
                    # Calculate totals from modified values
                    total_sal = sum(
                        st.session_state[mod_key].get('charges_salariales', {}).get(
                            c['code'], 
                            charges_sal.get(c['code'], 0)
                        )
                        for c in charges_config if c['has_salarial']
                    )
                    total_pat = sum(
                        st.session_state[mod_key].get('charges_patronales', {}).get(
                            c['code'], 
                            charges_pat.get(c['code'], 0)
                        )
                        for c in charges_config if c['has_patronal']
                    )
                    
                    total_cols[2].markdown(f"**{total_sal:.2f}€**")
                    total_cols[5].markdown(f"**{total_pat:.2f}€**")

                    # Initialize additional charges storage
                    additional_charges_key = f"additional_charges_{unique_key}"
                    if additional_charges_key not in st.session_state:
                        st.session_state[additional_charges_key] = []

                    # Display additional charges that were added
                    for added_charge in st.session_state[additional_charges_key]:
                        cols = st.columns([3, 1.5, 1.5, 2, 1.5, 2])

                        # Charge name
                        cols[0].markdown(f"**{added_charge['label']}**")
                        cols[0].caption(f"Code: {added_charge['code']}")

                        # Get current values
                        current_sal = charges_sal.get(added_charge['code'], 0)
                        current_pat = charges_pat.get(added_charge['code'], 0)

                        # Default base to salaire_brut
                        salaire_brut = safe_get_numeric(row, 'salaire_brut', 0)
                        current_base = st.session_state[bases_key].get(
                            added_charge['code'],
                            salaire_brut
                        )

                        # Salarial rate (display only)
                        if added_charge['has_salarial']:
                            cols[1].markdown(f"{added_charge['taux_sal']:.2f}%")
                        else:
                            cols[1].markdown("-")

                        # Salarial amount (editable)
                        if added_charge['has_salarial']:
                            new_sal = cols[2].number_input(
                                "Sal",
                                value=float(current_sal),
                                step=1.0,
                                format="%.2f",
                                key=f"charge_sal_{unique_key}_{added_charge['code']}",
                                label_visibility="collapsed"
                            )
                            if abs(new_sal - current_sal) > 0.01:
                                if 'charges_salariales' not in st.session_state[mod_key]:
                                    st.session_state[mod_key]['charges_salariales'] = {}
                                st.session_state[mod_key]['charges_salariales'][added_charge['code']] = new_sal
                        else:
                            cols[2].markdown("-")

                        # Base (editable)
                        new_base = cols[3].number_input(
                            "Base",
                            value=float(current_base),
                            step=100.0,
                            format="%.2f",
                            key=f"charge_base_{unique_key}_{added_charge['code']}",
                            label_visibility="collapsed"
                        )
                        if abs(new_base - current_base) > 0.01:
                            st.session_state[bases_key][added_charge['code']] = new_base
                            if 'charge_bases' not in st.session_state[mod_key]:
                                st.session_state[mod_key]['charge_bases'] = {}
                            st.session_state[mod_key]['charge_bases'][added_charge['code']] = new_base

                        # Patronal rate (display only)
                        if added_charge['has_patronal']:
                            cols[4].markdown(f"{added_charge['taux_pat']:.2f}%")
                        else:
                            cols[4].markdown("-")

                        # Patronal amount (editable)
                        if added_charge['has_patronal']:
                            new_pat = cols[5].number_input(
                                "Pat",
                                value=float(current_pat),
                                step=1.0,
                                format="%.2f",
                                key=f"charge_pat_{unique_key}_{added_charge['code']}",
                                label_visibility="collapsed"
                            )
                            if abs(new_pat - current_pat) > 0.01:
                                if 'charges_patronales' not in st.session_state[mod_key]:
                                    st.session_state[mod_key]['charges_patronales'] = {}
                                st.session_state[mod_key]['charges_patronales'][added_charge['code']] = new_pat
                        else:
                            cols[5].markdown("-")

                    # Dropdown to add new charge
                    st.markdown("---")
                    st.markdown("##### ➕ Ajouter une cotisation")

                    # Get available charges for this employee
                    available_charges = get_available_charges_for_employee(row)

                    if available_charges:
                        # Create dropdown options
                        charge_options = ["-- Sélectionner une cotisation --"] + [
                            f"{c['code']} - {c['label']}" for c in available_charges
                        ]

                        selected_charge = st.selectbox(
                            "Cotisation à ajouter",
                            options=charge_options,
                            key=f"add_charge_{unique_key}",
                            label_visibility="collapsed"
                        )

                        if selected_charge != "-- Sélectionner une cotisation --":
                            # Find the selected charge
                            selected_code = selected_charge.split(" - ")[0]
                            selected_charge_obj = next(
                                (c for c in available_charges if c['code'] == selected_code),
                                None
                            )

                            if selected_charge_obj:
                                # Add to additional charges
                                if selected_charge_obj not in st.session_state[additional_charges_key]:
                                    st.session_state[additional_charges_key].append(selected_charge_obj)
                                    # Initialize charges in modifications
                                    if 'charges_salariales' not in st.session_state[mod_key]:
                                        st.session_state[mod_key]['charges_salariales'] = {}
                                    if 'charges_patronales' not in st.session_state[mod_key]:
                                        st.session_state[mod_key]['charges_patronales'] = {}

                                    # Set initial values to 0
                                    if selected_charge_obj['has_salarial']:
                                        st.session_state[mod_key]['charges_salariales'][selected_code] = 0.0
                                    if selected_charge_obj['has_patronal']:
                                        st.session_state[mod_key]['charges_patronales'][selected_code] = 0.0

                                    st.rerun()
                    else:
                        st.info("Toutes les cotisations disponibles sont déjà affichées")

                # Action buttons
                st.markdown("---")
                col1, col2, col3 = st.columns([2, 2, 3])
                
                with col1:
                    if st.button("🔄 Recalculer", key=f"recalc_{unique_key}", type="primary"):
                        if st.session_state[mod_key]:
                            try:
                                # Recalculate with modifications
                                updated = recalculate_employee_payslip(
                                    dict(row),
                                    st.session_state[mod_key]
                                )
                                
                                # Update DataFrame
                                df = df.with_columns([
                                    pl.lit(value).alias(key) if key in df.columns else pl.lit(None).alias(key)
                                    for key, value in updated.items()
                                    ])
                                
                                st.session_state.processed_data = df
                                st.success("✅ Recalcul effectué!")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Erreur lors du recalcul: {str(e)}")
                        else:
                            st.warning("Aucune modification à appliquer")
                
                with col2:
                    reason = st.text_input("Motif de modification", key=f"reason_{unique_key}")
                    if st.button("💾 Sauvegarder", key=f"save_{unique_key}"):
                        if not reason:
                            st.error("Le motif est obligatoire")
                        elif not st.session_state[mod_key]:
                            st.warning("Aucune modification à sauvegarder")
                        else:
                            # Log all modifications
                            for field, new_value in st.session_state[mod_key].items():
                                if field == 'charge_bases':
                                    # Log base modifications
                                    for charge_code, base_value in new_value.items():
                                        log_modification(
                                            matricule, 
                                            f"base_{charge_code}", 
                                            None, 
                                            base_value,
                                            st.session_state.user, 
                                            reason
                                        )
                                else:
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
                            st.session_state[bases_key] = {}
                            st.rerun()
            
            # VALIDATION BUTTONS (always visible)
            else:
                col1, col2 = st.columns([1, 3])
                with col1:
                    if not is_validated:
                        if st.button("✅ Valider", key=f"validate_{unique_key}", type="primary"):
                            # Update using Polars
                            row_idx = df.filter(pl.col('matricule') == matricule).select(pl.first()).to_dicts()[0]
                            
                            df = df.with_columns([
                                pl.when(pl.col('matricule') == matricule)
                                .then(pl.lit(True))
                                .otherwise(pl.col('statut_validation'))
                                .alias('statut_validation'),
                                pl.when(pl.col('matricule') == matricule)
                                .then(pl.lit(False))
                                .otherwise(pl.col('edge_case_flag'))
                                .alias('edge_case_flag')
                            ])
                            
                            st.session_state.processed_data = df
                            
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
                            
                            st.success(f"✅ Fiche validée pour {row.get('nom', '')} {row.get('prenom', '')}")
                            st.rerun()
                    else:
                        st.success("✅ Déjà validé")

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
    df = pl.DataFrame(df) if not isinstance(df, pl.DataFrame) else df

    if df.is_empty():
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
        employees = df.select(['matricule', 'nom', 'prenom']).to_dicts()
        employee_options = [f"{emp['matricule']} - {emp['nom']} {emp['prenom']}" for emp in employees]
        
        selected_employee = st.selectbox("Sélectionner un employé", employee_options)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📄 Générer bulletin individuel", type="primary", use_container_width=True):
                if selected_employee:
                    try:
                        # Extract matricule from selection
                        matricule = selected_employee.split(' - ')[0].strip()
                        employee_row = df.filter(pl.col('matricule') == matricule)

                        if employee_row.is_empty():
                            st.error(f"Employee {matricule} not found in data")
                        else:
                            employee_data = clean_employee_data_for_pdf(
                                employee_row.to_dicts()[0]
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

                        # Add period information to all employees
                        last_day = calendar.monthrange(year, month)[1]

                        df_copy = df.with_columns([
                            pl.lit(f"01/{month:02d}/{year}").alias('period_start'),
                            pl.lit(f"{last_day:02d}/{month:02d}/{year}").alias('period_end'),
                            pl.lit(f"{last_day:02d}/{month:02d}/{year}").alias('payment_date')
                        ])

                        # Clean each row before generating PDFs
                        cleaned_data = []
                        for row in df_copy.iter_rows(named=True):
                            cleaned_data.append(clean_employee_data_for_pdf(row))
                        df_cleaned = pl.DataFrame(cleaned_data)
                        documents = pdf_service.generate_monthly_documents(df_cleaned, f"{month:02d}-{year}")
                        
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
            total_brut = df.select(pl.col('salaire_brut').sum()).item()
            st.metric("Masse salariale brute", f"{total_brut:,.0f} €")
        with col2:
            total_net = df.select(pl.col('salaire_net').sum()).item()
            st.metric("Total net à payer", f"{total_net:,.0f} €")
        with col3:
            total_charges_pat = df.select(pl.col('total_charges_patronales').sum()).item()
            st.metric("Charges patronales", f"{total_charges_pat:,.0f} €")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 Générer journal de paie", type="primary", use_container_width=True):
                try:
                    with st.spinner("Génération du journal en cours..."):
                        employees_data = df.to_dicts()
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
    month, year = map(int, st.session_state.current_period.split('-'))
    
    df = system.data_consolidator.load_period_data(st.session_state.current_company, month, year)
    
    if df.is_empty():
        st.warning("Aucune donnée à exporter. Lancez d'abord le traitement des paies.")
        return

    tab1, tab2 = st.tabs(["Exporter par Excel", "Voir le Rapport"])

    with tab1:
        st.info("📊 **Export Excel avec mise en forme**")
        
        # Preview key statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Employés", len(df))
        with col2:
            total_brut = df.select(pl.col('salaire_brut').sum()).item() if 'salaire_brut' in df.columns else 0
            st.metric("Masse salariale", f"{total_brut:,.0f} €")
        with col3:
            total_net = df.select(pl.col('salaire_net').sum()).item() if 'salaire_net' in df.columns else 0
            st.metric("Net à payer", f"{total_net:,.0f} €")
        
        if st.button("📥 Générer Excel", type="primary", use_container_width=True):
            try:
                from xlsxwriter import Workbook
                
                output = io.BytesIO()
                
                if HAS_EXCEL:
                    with Workbook(output) as wb:
                        # Sheet 1: Main payroll data with conditional formatting
                        df.write_excel(
                            workbook=wb,
                            worksheet="Paies",
                            position=(2, 0),
                            table_style={
                                "style": "Table Style Medium 2",
                                "first_column": True,
                            },
                            conditional_formats={
                                "salaire_brut": {
                                    "type": "3_color_scale",
                                    "min_color": "#63be7b",
                                    "mid_color": "#ffeb84",
                                    "max_color": "#f8696b",
                                },
                                "salaire_net": {
                                    "type": "data_bar",
                                    "data_bar_2010": True,
                                    "bar_color": "#2c3e50",
                                    "bar_negative_color_same": True,
                                },
                            } if 'salaire_brut' in df.columns and 'salaire_net' in df.columns else {},
                            column_widths={
                                "matricule": 100,
                                "nom": 150,
                                "prenom": 150,
                                "salaire_brut": 120,
                                "salaire_net": 120,
                            },
                            autofit=True,
                        )
                        
                        # Add title to payroll sheet
                        ws_paies = wb.get_worksheet_by_name("Paies")
                        fmt_title = wb.add_format({
                            "font_color": "#2c3e50",
                            "font_size": 14,
                            "bold": True,
                            "bg_color": "#f8f9fa",
                        })
                        ws_paies.write(0, 0, f"Paies - {st.session_state.current_company} - {st.session_state.current_period}", fmt_title)
                        ws_paies.set_row(0, 20)
                        
                        # Sheet 2: Summary statistics
                        summary_data = pl.DataFrame({
                            'Statistique': [
                                'Nombre de salariés',
                                'Masse salariale brute',
                                'Total charges salariales',
                                'Total charges patronales',
                                'Total net à payer',
                                'Coût total employeur'
                            ],
                            'Valeur': [
                                len(df),
                                df.select(pl.col('salaire_brut').sum()).item() if 'salaire_brut' in df.columns else 0,
                                df.select(pl.col('total_charges_salariales').sum()).item() if 'total_charges_salariales' in df.columns else 0,
                                df.select(pl.col('total_charges_patronales').sum()).item() if 'total_charges_patronales' in df.columns else 0,
                                df.select(pl.col('salaire_net').sum()).item() if 'salaire_net' in df.columns else 0,
                                df.select(pl.col('cout_total_employeur').sum()).item() if 'cout_total_employeur' in df.columns else 0,
                            ]
                        })
                        
                        summary_data.write_excel(
                            workbook=wb,
                            worksheet="Synthèse",
                            position=(2, 0),
                            table_style={
                                "style": "Table Style Light 9",
                                "first_column": True,
                            },
                            column_formats={
                                "Valeur": "#,##0.00 €"
                            },
                            column_widths={
                                "Statistique": 250,
                                "Valeur": 150,
                            },
                        )
                        
                        # Add title to summary sheet
                        ws_synthese = wb.get_worksheet_by_name("Synthèse")
                        ws_synthese.write(0, 0, "Synthèse de la Paie", fmt_title)
                        ws_synthese.set_row(0, 20)
                    
                else:
                    # Fallback to CSV if xlsxwriter not available
                    df.write_csv(output)
                
                st.download_button(
                    label="💾 Télécharger Excel",
                    data=output.getvalue(),
                    file_name=f"paies_{st.session_state.current_company}_{st.session_state.current_period}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if HAS_EXCEL else "text/csv",
                    use_container_width=True
                )
                
                st.success("✅ Fichier Excel généré avec succès!")
                st.info("""
                📊 **Contenu du fichier:**
                - **Paies**: Données complètes avec mise en forme conditionnelle
                - **Synthèse**: Statistiques principales
                - **Détail Charges**: Ventilation des cotisations sociales
                - **État Validation**: Répartition par statut
                - **Cas Particuliers**: Employés nécessitant une vérification
                """)
                
            except ImportError:
                st.error("Le module xlsxwriter n'est pas installé. Installez-le avec: pip install xlsxwriter")
            except Exception as e:
                st.error(f"Erreur lors de la génération: {str(e)}")
                st.exception(e)
    
    with tab2:
        st.info("📋 **Rapport de synthèse**")
        if st.button("Voir rapport", use_container_width=True):
            st.markdown("---")
            st.subheader("Rapport de synthèse")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Statistiques générales:**")
                st.write(f"- Nombre total d'employés: {len(df)}")
                
                validated_count = df.filter(pl.col('statut_validation') == True).height if 'statut_validation' in df.columns else 0
                st.write(f"- Fiches validées: {validated_count}")
                
                edge_count = df.select(pl.col('edge_case_flag').sum()).item() if 'edge_case_flag' in df.columns else 0
                st.write(f"- Cas à vérifier: {edge_count}")
                
                # Validation percentage
                if validated_count > 0:
                    pct = (validated_count / len(df)) * 100
                    st.write(f"- Taux de validation: {pct:.1f}%")
            
            with col2:
                st.write("**Statistiques financières:**")
                if 'salaire_brut' in df.columns:
                    total_brut = df.select(pl.col('salaire_brut').sum()).item()
                    st.write(f"- Masse salariale brute: {total_brut:,.2f} €")
                    
                    # Average salary
                    avg_brut = df.select(pl.col('salaire_brut').mean()).item()
                    st.write(f"- Salaire brut moyen: {avg_brut:,.2f} €")
                
                if 'salaire_net' in df.columns:
                    total_net = df.select(pl.col('salaire_net').sum()).item()
                    st.write(f"- Total net à payer: {total_net:,.2f} €")
                
                if 'total_charges_patronales' in df.columns:
                    total_charges = df.select(pl.col('total_charges_patronales').sum()).item()
                    st.write(f"- Charges patronales: {total_charges:,.2f} €")
                
                if 'cout_total_employeur' in df.columns:
                    total_cout = df.select(pl.col('cout_total_employeur').sum()).item()
                    st.write(f"- **Coût total employeur: {total_cout:,.2f} €**")
            
            # Additional breakdown by status
            if 'statut_validation' in df.columns:
                st.markdown("---")
                st.subheader("Répartition par statut de validation")
                
                status_breakdown = df.group_by('statut_validation').agg([
                    pl.count().alias('Nombre'),
                    pl.col('salaire_brut').sum().alias('Masse_Brute'),
                ]) if 'salaire_brut' in df.columns else df.group_by('statut_validation').agg(pl.count().alias('Nombre'))
                
                st.dataframe(status_breakdown.to_pandas(), use_container_width=True)
            
            # Charge breakdown if available
            if 'total_charges_salariales' in df.columns and 'total_charges_patronales' in df.columns:
                st.markdown("---")
                st.subheader("Ventilation des charges")
                
                col1, col2 = st.columns(2)
                with col1:
                    total_sal = df.select(pl.col('total_charges_salariales').sum()).item()
                    st.metric("Charges salariales totales", f"{total_sal:,.2f} €")
                with col2:
                    total_pat = df.select(pl.col('total_charges_patronales').sum()).item()
                    st.metric("Charges patronales totales", f"{total_pat:,.2f} €")

def send_validation_email_page():
    """Page d'envoi des emails de validation au client"""
    st.title("📧 Envoi Validation Client")

    # Vérifier la configuration email
    config_path = Path("config/email_config.json")
    if not config_path.exists():
        st.error("❌ Configuration email non trouvée. Veuillez d'abord configurer l'email dans la page Configuration.")
        if st.button("➡️ Aller à la configuration"):
            st.session_state.current_page = "email_config"
            st.rerun()
        return

    # Charger les données
    company_id = st.session_state.get('current_company')
    period_str = st.session_state.get('current_period', datetime.now().strftime("%m-%Y"))

    if not company_id:
        st.warning("Veuillez sélectionner une entreprise")
        return

    # Convertir la période au format YYYY-MM
    try:
        period_date = datetime.strptime(period_str, "%m-%Y")
        period = period_date.strftime("%Y-%m")
        month_year = period_date.strftime("%B %Y")
    except:
        st.error("Format de période invalide")
        return

    year = period_date.year
    month = period_date.month

    # Charger les données de paie
    df_period = DataManager.load_period_data(company_id, month, year)

    if df_period.height == 0:
        st.warning(f"Aucune donnée de paie trouvée pour {month_year}")
        return

    st.info(f"📊 {df_period.height} salariés pour la période {month_year}")

    # Formulaire d'envoi
    with st.form("validation_email_form"):
        st.subheader("Destinataire")

        col1, col2 = st.columns([2, 1])

        with col1:
            client_email = st.text_input(
                "Email du client (employeur)",
                help="L'email de l'entreprise cliente qui recevra tous les documents pour validation"
            )

        with col2:
            test_mode = st.checkbox("Mode test", value=True, help="Ne pas envoyer réellement l'email")

        st.markdown("---")
        st.subheader("Documents à envoyer")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"📦 **{df_period.height}** bulletins de paie\n\n(archive ZIP)")
        with col2:
            st.info("📄 **Journal de paie**\n\n(récapitulatif consolidé)")
        with col3:
            st.info("📊 **Provision CP**\n\n(congés payés)")

        st.markdown("---")

        # Calculer le récapitulatif
        total_brut = df_period.select(pl.col('salaire_brut').sum()).item()
        total_net = df_period.select(pl.col('salaire_net').sum()).item()
        total_charges_sal = df_period.select(pl.col('total_charges_salariales').sum()).item()
        total_charges_pat = df_period.select(pl.col('total_charges_patronales').sum()).item()
        total_cout = df_period.select(pl.col('cout_total_employeur').sum()).item()

        st.subheader("Récapitulatif de la paie")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Masse salariale brute", f"{total_brut:,.2f} €")
            st.metric("Charges salariales", f"{total_charges_sal:,.2f} €")

        with col2:
            st.metric("Masse salariale nette", f"{total_net:,.2f} €", delta=None, delta_color="normal")
            st.metric("Charges patronales", f"{total_charges_pat:,.2f} €")

        with col3:
            st.metric("Coût total employeur", f"{total_cout:,.2f} €", delta=None, delta_color="inverse")
            st.metric("Nombre de salariés", df_period.height)

        st.markdown("---")

        submit_button = st.form_submit_button("📧 Envoyer l'email de validation", use_container_width=True, type="primary")

    if submit_button:
        if not client_email:
            st.error("❌ Veuillez saisir l'adresse email du client")
            return

        try:
            with st.spinner("Génération des documents PDF..."):
                # Charger les informations de l'entreprise
                system = IntegratedPayrollSystem()
                company_info = system.company_info

                # Générer les documents PDF
                pdf_service = PDFGeneratorService(company_info)
                documents = pdf_service.generate_monthly_documents(df_period, period)

                # Préparer le résumé pour l'email
                payroll_summary = {
                    'total_brut': total_brut,
                    'total_net': total_net,
                    'total_charges_sal': total_charges_sal,
                    'total_charges_pat': total_charges_pat,
                    'total_cout': total_cout
                }

                progress_bar = st.progress(0, text="Préparation de l'email...")

                # Créer le système d'email
                email_system = create_email_distribution_system()
                email_service = email_system['email_service']

                progress_bar.progress(50, text="Envoi de l'email...")

                # Envoyer l'email de validation
                result = email_service.send_validation_email(
                    client_email=client_email,
                    company_name=company_info.get('name', 'Entreprise'),
                    paystubs_buffers=documents['paystubs'],
                    journal_buffer=documents['journal'],
                    pto_buffer=documents['pto_provision'],
                    period=period,
                    payroll_summary=payroll_summary,
                    test_mode=test_mode
                )

                progress_bar.progress(100, text="Terminé!")
                time.sleep(0.5)
                progress_bar.empty()

                if result['success']:
                    if test_mode:
                        st.success(f"✅ [MODE TEST] L'email aurait été envoyé à: {client_email}")
                        st.info(f"📎 Pièces jointes: {result.get('attachments_count', 3)} fichiers")
                    else:
                        st.success(f"✅ Email de validation envoyé avec succès à: {client_email}")
                        st.balloons()

                    # Afficher un aperçu
                    with st.expander("📋 Aperçu de l'email envoyé"):
                        st.markdown(f"""
                        **À:** {client_email}

                        **Sujet:** Validation paie - {company_info.get('name', 'Entreprise')} - {month_year}

                        **Documents joints:**
                        - bulletins_paie_{period}.zip ({df_period.height} bulletins)
                        - journal_paie_{period}.pdf
                        - provision_cp_{period}.pdf

                        **Récapitulatif:**
                        - Masse salariale brute: {total_brut:,.2f} €
                        - Charges salariales: {total_charges_sal:,.2f} €
                        - Charges patronales: {total_charges_pat:,.2f} €
                        - Masse salariale nette: {total_net:,.2f} €
                        - Coût total employeur: {total_cout:,.2f} €
                        """)
                else:
                    st.error(f"❌ Échec de l'envoi: {result.get('error', 'Erreur inconnue')}")

        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
            import traceback
            with st.expander("Détails de l'erreur"):
                st.code(traceback.format_exc())

def dsm_declaration_page():
    """Page de génération de la déclaration DSM Monaco"""
    st.title("📄 Déclaration DSM Monaco")

    st.info("Génération de la déclaration sociale mensuelle pour les Caisses Sociales de Monaco")

    # Load company info
    system = IntegratedPayrollSystem()
    company_info = system.company_info

    # Check if employer number is configured
    employer_number = company_info.get('employer_number_monaco', '')

    if not employer_number:
        st.warning("⚠️ Numéro d'employeur Monaco non configuré")
        st.info("Veuillez configurer le numéro d'employeur dans la page Configuration → Entreprise")

        if st.session_state.role == "admin":
            with st.expander("➕ Configurer maintenant"):
                with st.form("quick_employer_config"):
                    new_employer_number = st.text_input(
                        "Numéro d'employeur Monaco",
                        help="Numéro d'enregistrement auprès des Caisses Sociales de Monaco"
                    )

                    if st.form_submit_button("💾 Sauvegarder"):
                        if new_employer_number:
                            company_info['employer_number_monaco'] = new_employer_number
                            config_file = CONFIG_DIR / "company_info.json"
                            with open(config_file, 'w', encoding='utf-8') as f:
                                json.dump(company_info, f, indent=2)
                            st.success("✅ Numéro d'employeur sauvegardé!")
                            time.sleep(1)
                            st.rerun()
        return

    # Load period data
    company_id = st.session_state.get('current_company')
    period_str = st.session_state.get('current_period', datetime.now().strftime("%m-%Y"))

    if not company_id:
        st.warning("Veuillez sélectionner une entreprise")
        return

    # Convert period
    try:
        period_date = datetime.strptime(period_str, "%m-%Y")
        period = period_date.strftime("%Y-%m")
        month_year = period_date.strftime("%B %Y")
    except:
        st.error("Format de période invalide")
        return

    year = period_date.year
    month = period_date.month

    # Load payroll data
    df_period = DataManager.load_period_data(company_id, month, year)

    if df_period.height == 0:
        st.warning(f"Aucune donnée de paie trouvée pour {month_year}")
        st.info("Veuillez d'abord traiter la paie pour cette période dans 'Traitement des paies'")
        return

    st.success(f"✅ {df_period.height} salariés trouvés pour {month_year}")

    # Configuration section
    st.markdown("---")
    st.subheader("Configuration DSM")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Numéro employeur", employer_number)

    with col2:
        st.metric("Période", period)

    with col3:
        # Get plafond from constants
        constants = MonacoPayrollConstants(year)
        plafond_t1 = constants.PLAFOND_SS_T1
        st.metric("Plafond SS T1", f"{plafond_t1:,.2f} €")

    # Employee configuration section
    st.markdown("---")
    st.subheader("Configuration des employés")

    st.info("""
    Les champs suivants sont requis pour la déclaration DSM.
    Vous pouvez configurer les valeurs par défaut ou modifier individuellement chaque employé.
    """)

    # Default values
    with st.expander("⚙️ Valeurs par défaut"):
        col1, col2 = st.columns(2)

        with col1:
            default_affiliation_ac = st.selectbox("Affiliation AC (par défaut)", ["Oui", "Non"], index=0)
            default_affiliation_rc = st.selectbox("Affiliation RC (par défaut)", ["Oui", "Non"], index=0)
            default_affiliation_car = st.selectbox("Affiliation CAR (par défaut)", ["Oui", "Non"], index=0)

        with col2:
            default_teletravail = st.selectbox("Télétravail (par défaut)", ["Non", "Oui"], index=0)
            default_admin_salarie = st.selectbox("Administrateur salarié (par défaut)", ["Non", "Oui"], index=0)

        if st.button("📝 Appliquer les valeurs par défaut à tous les employés", use_container_width=True):
            # Apply defaults to all employees missing these values
            df_period = df_period.with_columns([
                pl.when(pl.col('affiliation_ac').is_null())
                .then(pl.lit(default_affiliation_ac))
                .otherwise(pl.col('affiliation_ac'))
                .alias('affiliation_ac'),

                pl.when(pl.col('affiliation_rc').is_null())
                .then(pl.lit(default_affiliation_rc))
                .otherwise(pl.col('affiliation_rc'))
                .alias('affiliation_rc'),

                pl.when(pl.col('affiliation_car').is_null())
                .then(pl.lit(default_affiliation_car))
                .otherwise(pl.col('affiliation_car'))
                .alias('affiliation_car'),

                pl.when(pl.col('teletravail').is_null())
                .then(pl.lit(default_teletravail))
                .otherwise(pl.col('teletravail'))
                .alias('teletravail'),

                pl.when(pl.col('administrateur_salarie').is_null())
                .then(pl.lit(default_admin_salarie))
                .otherwise(pl.col('administrateur_salarie'))
                .alias('administrateur_salarie'),
            ])

            # Save updated data
            DataManager.save_period_data(df_period, company_id, month, year)
            st.success("✅ Valeurs par défaut appliquées!")
            st.rerun()

    # Show employee data with missing fields
    missing_fields_df = df_period.filter(
        pl.col('date_naissance').is_null() |
        pl.col('affiliation_ac').is_null() |
        pl.col('affiliation_rc').is_null() |
        pl.col('affiliation_car').is_null()
    )

    if missing_fields_df.height > 0:
        st.warning(f"⚠️ {missing_fields_df.height} employé(s) avec des champs manquants pour la DSM")
        with st.expander("Voir les employés concernés"):
            display_cols = ['matricule', 'nom', 'prenom']
            if 'date_naissance' in missing_fields_df.columns:
                display_cols.append('date_naissance')
            st.dataframe(
                missing_fields_df.select(display_cols).to_pandas(),
                use_container_width=True
            )
            st.info("💡 Ajoutez ces informations dans le fichier Excel d'import ou configurez-les individuellement")

    # Generation section
    st.markdown("---")
    st.subheader("Génération du fichier XML")

    col1, col2 = st.columns([2, 1])

    with col1:
        recipient_email = st.text_input(
            "Email destinataire (Caisses Sociales Monaco)",
            help="Email pour l'envoi de la déclaration DSM (optionnel)"
        )

    with col2:
        include_in_email = st.checkbox("Inclure dans l'email", value=False, disabled=not recipient_email)

    # Summary
    st.markdown("### 📊 Récapitulatif")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Employés", df_period.height)

    with col2:
        total_brut = df_period.select(pl.col('salaire_brut').sum()).item()
        st.metric("Masse salariale brute", f"{total_brut:,.0f} €")

    with col3:
        # Calculate total base CCSS
        total_ccss = total_brut
        st.metric("Base CCSS totale", f"{total_ccss:,.0f} €")

    with col4:
        # Calculate total base CAR
        total_car = df_period.select(pl.col('salaire_brut').sum()).item()
        st.metric("Base CAR totale", f"{total_car:,.0f} €")

    st.markdown("---")

    # Generation button
    col1, col2, col3 = st.columns([1, 1, 1])

    with col2:
        generate_button = st.button(
            "📄 Générer la déclaration DSM",
            type="primary",
            use_container_width=True
        )

    if generate_button:
        try:
            with st.spinner("Génération du fichier XML DSM en cours..."):
                # Create generator
                generator = DSMXMLGenerator(employer_number, plafond_t1)

                # Generate XML
                xml_buffer = generator.generate_dsm_xml(df_period, period)

                # Get XML content for display
                xml_buffer.seek(0)
                xml_content = xml_buffer.read().decode('UTF-8')
                xml_buffer.seek(0)

                st.success("✅ Déclaration DSM générée avec succès!")

                # Download button
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.download_button(
                        label="📥 Télécharger DSM XML",
                        data=xml_buffer.getvalue(),
                        file_name=f"DSM_{employer_number}_{period}.xml",
                        mime="application/xml",
                        use_container_width=True
                    )

                # Preview
                with st.expander("👁️ Aperçu du fichier XML"):
                    st.code(xml_content, language="xml")

                # Email option
                if recipient_email and include_in_email:
                    st.info("📧 La fonctionnalité d'envoi par email sera disponible prochainement")
                    # TODO: Implement email sending when Caisses Sociales email is provided

        except Exception as e:
            st.error(f"❌ Erreur lors de la génération: {str(e)}")
            import traceback
            with st.expander("Détails de l'erreur"):
                st.code(traceback.format_exc())

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

    tab1, tab2, tab3 = st.tabs(["Entreprise", "Utilisateurs", "Admin"])

    with tab1:
        st.subheader("Informations de l'entreprise")
        
        with st.form("company_form"):
            name = st.text_input("Nom de l'entreprise", value=system.company_info.get('name', ''))
            siret = st.text_input("SIRET", value=system.company_info.get('siret', ''))
            address = st.text_area("Adresse", value=system.company_info.get('address', ''))
            phone = st.text_input("Téléphone", value=system.company_info.get('phone', ''))
            email = st.text_input("Email", value=system.company_info.get('email', ''))

            st.markdown("---")
            st.markdown("**Déclaration Monaco (DSM)**")
            employer_number_monaco = st.text_input(
                "Numéro d'employeur Monaco",
                value=system.company_info.get('employer_number_monaco', ''),
                help="Numéro d'enregistrement auprès des Caisses Sociales de Monaco"
            )

            if st.form_submit_button("💾 Sauvegarder"):
                updated_info = {
                    'name': name,
                    'siret': siret,
                    'address': address,
                    'phone': phone,
                    'email': email,
                    'employer_number_monaco': employer_number_monaco
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
            users_df = pl.DataFrame(users)
            st.dataframe(users_df.select(['username', 'name', 'role']), use_container_width=True)
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
        # Include the full admin panel in the configuration
        st.info("ℹ️ Les paramètres de calcul (plafonds SS, SMIC, taux de cotisations) sont désormais gérés dans le fichier CSV: config/payroll_rates.csv")
        admin_panel()

def email_config_page():
    """Page de configuration des emails"""
    st.title("⚙️ Configuration Email")

    config_manager = EmailConfigManager(Path("config/email_config.json"))

    # Charger la configuration existante
    existing_config = config_manager.load_config()

    st.info("Configurez les paramètres SMTP pour l'envoi des emails de paie")

    # Preset providers
    col1, col2 = st.columns([2, 1])
    with col1:
        provider = st.selectbox(
            "Fournisseur email",
            ["Gmail", "Outlook", "Office 365", "Autre (personnalisé)"]
        )

    # Default configs based on provider
    defaults = {
        "Gmail": {"server": "smtp.gmail.com", "port": 587, "use_tls": True, "use_ssl": False},
        "Outlook": {"server": "smtp-mail.outlook.com", "port": 587, "use_tls": True, "use_ssl": False},
        "Office 365": {"server": "smtp.office365.com", "port": 587, "use_tls": True, "use_ssl": False},
        "Autre (personnalisé)": {"server": "", "port": 587, "use_tls": True, "use_ssl": False}
    }

    preset = defaults.get(provider, defaults["Autre (personnalisé)"])

    st.markdown("---")

    with st.form("email_config_form"):
        col1, col2 = st.columns(2)

        with col1:
            smtp_server = st.text_input(
                "Serveur SMTP",
                value=existing_config.smtp_server if existing_config else preset["server"],
                help="ex: smtp.gmail.com"
            )

            smtp_port = st.number_input(
                "Port SMTP",
                value=existing_config.smtp_port if existing_config else preset["port"],
                min_value=1,
                max_value=65535
            )

            sender_email = st.text_input(
                "Adresse email expéditeur",
                value=existing_config.sender_email if existing_config else "",
                help="ex: paie@monentreprise.com"
            )

            sender_password = st.text_input(
                "Mot de passe / App Password",
                type="password",
                help="Pour Gmail/Outlook, utilisez un 'App Password' généré"
            )

        with col2:
            sender_name = st.text_input(
                "Nom de l'expéditeur",
                value=existing_config.sender_name if existing_config else "Service Paie",
                help="Nom affiché dans les emails"
            )

            use_tls = st.checkbox(
                "Utiliser TLS (StartTLS)",
                value=existing_config.use_tls if existing_config else preset["use_tls"]
            )

            use_ssl = st.checkbox(
                "Utiliser SSL",
                value=existing_config.use_ssl if existing_config else preset["use_ssl"]
            )

            reply_to = st.text_input(
                "Adresse de réponse (optionnel)",
                value=existing_config.reply_to if existing_config and existing_config.reply_to else ""
            )

            bcc_archive = st.text_input(
                "BCC pour archivage (optionnel)",
                value=existing_config.bcc_archive if existing_config and existing_config.bcc_archive else "",
                help="Copie cachée pour archivage automatique"
            )

        col1, col2, col3 = st.columns([1, 1, 2])

        with col1:
            save_button = st.form_submit_button("💾 Sauvegarder", use_container_width=True)

        with col2:
            test_button = st.form_submit_button("🧪 Tester", use_container_width=True)

    if save_button:
        try:
            # Créer la configuration
            config = EmailConfig(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                sender_email=sender_email,
                sender_password=sender_password or (existing_config.sender_password if existing_config else ""),
                sender_name=sender_name,
                use_tls=use_tls,
                use_ssl=use_ssl,
                reply_to=reply_to if reply_to else None,
                bcc_archive=bcc_archive if bcc_archive else None
            )

            # Sauvegarder
            if config_manager.save_config(config, encrypt_password=True):
                st.success("✅ Configuration sauvegardée avec succès!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Erreur lors de la sauvegarde")

        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")

    if test_button:
        try:
            import smtplib
            import ssl

            # Tester la connexion SMTP
            context = ssl.create_default_context()

            with st.spinner("Test de connexion SMTP..."):
                if use_ssl:
                    server = smtplib.SMTP_SSL(smtp_server, smtp_port, context=context)
                else:
                    server = smtplib.SMTP(smtp_server, smtp_port)
                    if use_tls:
                        server.starttls(context=context)

                server.login(sender_email, sender_password or (existing_config.sender_password if existing_config else ""))
                server.quit()

            st.success("✅ Connexion SMTP réussie!")

        except Exception as e:
            st.error(f"❌ Échec du test: {str(e)}")

    # Afficher la config actuelle
    if existing_config:
        st.markdown("---")
        st.subheader("Configuration actuelle")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Serveur SMTP", f"{existing_config.smtp_server}:{existing_config.smtp_port}")
            st.metric("Expéditeur", existing_config.sender_email)

        with col2:
            st.metric("TLS/SSL", f"TLS: {existing_config.use_tls} | SSL: {existing_config.use_ssl}")
            st.metric("Nom affiché", existing_config.sender_name)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    if not st.session_state.authenticated:
        login_page()
    else:
        main_app()
