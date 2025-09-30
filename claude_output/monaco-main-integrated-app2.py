import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import os
from pathlib import Path
import json
import io
from typing import Dict, List, Optional, Tuple
import pyarrow.parquet as pq
import pyarrow as pa
import hashlib
import logging
import time

# Import all our custom modules
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
from services.pdf_generation import (
    PDFGeneratorService,
    PaystubPDFGenerator,
    PayJournalPDFGenerator,
    PTOProvisionPDFGenerator
)
from services.email_archive import (
    EmailDistributionService,
    EmailConfig,
    EmailConfigManager,
    PDFArchiveManager,
    ComplianceAuditLogger,
    EmailTemplate
)

# OAuth2 imports
from services.oauth2_integration import (
    OAuth2Config, 
    OAuth2EmailManager, 
    MicrosoftOAuth2Service
)




# Constants
DATA_DIR = Path("data")
CONFIG_DIR = Path("config")
ARCHIVES_DIR = Path("archives")
TEMP_DIR = Path("temp")

# Create directories
for directory in [DATA_DIR, CONFIG_DIR, ARCHIVES_DIR, TEMP_DIR]:
    directory.mkdir(parents=True, exist_ok=True)



class OAuth2EmailService:
    """Service d'email avec support OAuth2 pour Office 365"""

    def __init__(self):
        self.config = OAUTH_CONFIG['microsoft']

    def authenticate_microsoft(self) -> Optional[str]:
        """
        Authentification OAuth2 pour Microsoft/Office 365
        """
        try:
            app = msal.ConfidentialClientApplication(
                self.config['client_id'],
                authority=self.config['authority'],
                client_credential=self.config['client_secret']
            )
            
            auth_url = app.get_authorization_request_url(
                scopes=self.config['scope'],
                redirect_uri=self.config['redirect_uri']
            )
            
            return auth_url
            
        except Exception as e:
            logger.error(f"Erreur authentification Microsoft: {e}")
            return None
    
    def send_email_oauth2(self, to_email: str, subject: str, 
                         body: str, attachment: Optional[bytes] = None,
                         filename: Optional[str] = None) -> bool:
        """
        Envoyer un email via OAuth2 (Gmail ou Office 365)
        """
        if self.provider == 'google':
            return self._send_gmail(to_email, subject, body, attachment, filename)
        elif self.provider == 'microsoft':
            return self._send_office365(to_email, subject, body, attachment, filename)
        return False
    
    
    def _send_office365(self, to_email: str, subject: str,
                       body: str, attachment: Optional[bytes] = None,
                       filename: Optional[str] = None) -> bool:
        """
        Envoyer via Microsoft Graph API avec OAuth2
        """
        try:
            import requests
            import base64
            
            # Préparer le message
            message = {
                'subject': subject,
                'body': {
                    'contentType': 'HTML',
                    'content': body
                },
                'toRecipients': [
                    {
                        'emailAddress': {
                            'address': to_email
                        }
                    }
                ]
            }
            
            # Ajouter la pièce jointe si présente
            if attachment and filename:
                message['attachments'] = [
                    {
                        '@odata.type': '#microsoft.graph.fileAttachment',
                        'name': filename,
                        'contentType': 'application/pdf',
                        'contentBytes': base64.b64encode(attachment).decode()
                    }
                ]
            
            # Envoyer via Graph API
            headers = {
                'Authorization': f'Bearer {self.credentials}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                'https://graph.microsoft.com/v1.0/me/sendMail',
                headers=headers,
                json={'message': message}
            )
            
            if response.status_code == 202:
                logger.info("Email envoyé via Office 365")
                return True
            else:
                logger.error(f"Erreur envoi Office 365: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur envoi Office 365: {e}")
            return False


class IntegratedPayrollSystem:
    """Système intégré de gestion de paie"""
    
    def __init__(self):
        """Initialiser le système complet"""
        
        # Initialisation des services
        self.calculator = CalculateurPaieMonaco()
        self.validator = ValidateurPaieMonaco()
        self.pto_manager = GestionnaireCongesPayes()
        self.excel_manager = ExcelImportExport()
        self.data_consolidator = DataConsolidation()
        
        # Configuration entreprise (à charger depuis fichier)
        self.company_info = self._load_company_info()
        
        # Services PDF
        logo_path = "logo.png" if Path("logo.png").exists() else None
        self.pdf_service = PDFGeneratorService(self.company_info, logo_path)
        
        # Services Email
        self.email_system = self._initialize_email_system()
        
        # OAuth2 Service
        self.oauth_service = None
    
    def _load_company_info(self) -> Dict:
        """Charger les informations de l'entreprise"""
        config_file = CONFIG_DIR / "company_info.json"
        
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Configuration par défaut
        default_info = {
            'name': 'Cabinet Comptable Monaco',
            'siret': '000000000',
            'address': '98000 MONACO',
            'phone': '+377 93 00 00 00',
            'email': 'contact@cabinet.mc'
        }
        
        # Sauvegarder la configuration par défaut
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_info, f, indent=2)
        
        return default_info
    
    def _initialize_email_system(self) -> Dict:
        """Initialiser le système d'email"""
        from email_distribution import create_email_distribution_system
        
        return create_email_distribution_system(
            config_path=str(CONFIG_DIR / "email_config.json"),
            archive_path=str(ARCHIVES_DIR / "email_archives")
        )
    
    def process_monthly_payroll(self, company_id: str, period: str) -> Dict:
        """
        Traiter la paie mensuelle complète
        
        Args:
            company_id: ID de l'entreprise
            period: Période YYYY-MM
        
        Returns:
            Rapport de traitement
        """
        report = {
            'period': period,
            'company_id': company_id,
            'start_time': datetime.now(),
            'steps': []
        }
        
        try:
            # 1. Charger les données
            year, month = map(int, period.split('-'))
            df = self.data_consolidator.load_period_data(company_id, year, month)
            
            if df.empty:
                report['error'] = "Aucune donnée trouvée pour cette période"
                return report
            
            report['steps'].append({
                'step': 'Chargement des données',
                'status': 'success',
                'count': len(df)
            })
            
            # 2. Traiter les calculs de paie
            processed_data = []
            edge_cases = []
            
            for idx, row in df.iterrows():
                # Calculer la paie
                payslip = self.calculator.process_employee_payslip(row.to_dict())
                
                # Valider
                is_valid, issues = self.validator.validate_payslip(payslip)
                
                # Détecter les cas particuliers
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
                    payslip['edge_case_reason'] = '; '.join(issues)
                else:
                    payslip['statut_validation'] = 'Validé'
                    payslip['edge_case_flag'] = False
                    payslip['edge_case_reason'] = ''
                
                processed_data.append(payslip)
            
            # Créer DataFrame avec les données traitées
            processed_df = pd.DataFrame(processed_data)
            
            # Sauvegarder les données traitées
            self.data_consolidator.save_period_data(processed_df, company_id, year, month)
            
            report['steps'].append({
                'step': 'Calcul des paies',
                'status': 'success',
                'processed': len(processed_data),
                'validated': len(processed_data) - len(edge_cases),
                'edge_cases': len(edge_cases)
            })
            
            # 3. Générer les PDFs
            documents = self.pdf_service.generate_monthly_documents(
                processed_df,
                period,
                output_dir=None  # Retourner les buffers
            )
            
            report['steps'].append({
                'step': 'Génération des PDFs',
                'status': 'success',
                'paystubs': len(documents.get('paystubs', [])),
                'journal': 'generated' if 'journal' in documents else 'failed',
                'pto_provision': 'generated' if 'pto_provision' in documents else 'failed'
            })
            
            # Stocker les documents dans la session
            st.session_state['generated_documents'] = documents
            st.session_state['processed_data'] = processed_df
            st.session_state['edge_cases'] = edge_cases
            
            report['success'] = True
            report['end_time'] = datetime.now()
            report['duration'] = (report['end_time'] - report['start_time']).total_seconds()
            
        except Exception as e:
            report['error'] = str(e)
            report['success'] = False
            logger.error(f"Erreur traitement paie: {e}")
        
        return report


# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.current_company = None
    st.session_state.current_period = None
    st.session_state.payroll_system = IntegratedPayrollSystem()



def main_app():
    """Application principale"""
    
    # Sidebar navigation
    with st.sidebar:
        st.title("Navigation")
        st.write(f"👤 **Utilisateur:** {st.session_state.user}")
        st.write(f"🔐 **Rôle:** {st.session_state.role}")
        
        st.markdown("---")
        
        # Company and period selection
        companies = ['CARAX MONACO', 'RG CAPITAL SERVICES']
        st.session_state.current_company = st.selectbox("Entreprise", companies)
        
        current_month = datetime.now().strftime("%Y-%m")
        st.session_state.current_period = st.text_input("Période (YYYY-MM)", value=current_month)
        
        st.markdown("---")
        
        # Menu pages
        pages = {
            "📊 Tableau de bord": "dashboard",
            "📥 Import des données": "import",
            "💰 Traitement des paies": "processing",
            "✅ Validation": "validation", 
            "📄 Documents PDF": "documents",
            "📧 Envoi des bulletins": "email",
            "📁 Archives": "archives"
        }
        
        if st.session_state.role == "admin":
            pages["⚙️ Configuration"] = "config"
        
        selected_page = st.radio("Menu", list(pages.keys()))
        current_page = pages[selected_page]
        
        st.markdown("---")
        
        if st.button("🚪 Déconnexion", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user = None
            st.session_state.role = None
            st.rerun()
    
    # Main content area
    st.title(f"Gestion des Paies - {st.session_state.current_company}")
    st.write(f"**Période:** {st.session_state.current_period}")
    
    # Route to appropriate page
    if current_page == "dashboard":
        dashboard_page()
    elif current_page == "import":
        import_page()
    elif current_page == "processing":
        processing_page()
    elif current_page == "validation":
        validation_page()
    elif current_page == "documents":
        documents_page()
    elif current_page == "email":
        email_page()
    elif current_page == "archives":
        archives_page()
    elif current_page == "config":
        config_page()


def dashboard_page():
    """Page tableau de bord"""
    st.header("📊 Tableau de bord")
    
    system = st.session_state.payroll_system
    
    # Charger les données de la période
    if st.session_state.current_company and st.session_state.current_period:
        year, month = map(int, st.session_state.current_period.split('-'))
        company_id = st.session_state.current_company.replace(' ', '_')
        
        df = system.data_consolidator.load_period_data(company_id, year, month)
        
        if not df.empty:
            # Métriques principales
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Nombre de salariés", len(df))
            
            with col2:
                total_brut = df['salaire_brut'].sum() if 'salaire_brut' in df.columns else 0
                st.metric("Masse salariale brute", f"{total_brut:,.0f} €")
            
            with col3:
                edge_cases = df['edge_case_flag'].sum() if 'edge_case_flag' in df.columns else 0
                st.metric("Cas à vérifier", edge_cases)
            
            with col4:
                validated = (df['statut_validation'] == 'Validé').sum() if 'statut_validation' in df.columns else 0
                st.metric("Fiches validées", f"{validated}/{len(df)}")
            
            # Graphiques
            st.markdown("---")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Répartition par statut")
                if 'statut_validation' in df.columns:
                    status_counts = df['statut_validation'].value_counts()
                    st.bar_chart(status_counts)
            
            with col2:
                st.subheader("Distribution des salaires")
                if 'salaire_net' in df.columns:
                    st.histogram(df['salaire_net'], nbins=20)
            
            # Tableau récapitulatif
            st.markdown("---")
            st.subheader("Employés avec cas particuliers")
            
            if 'edge_case_flag' in df.columns:
                edge_cases_df = df[df['edge_case_flag'] == True]
                if not edge_cases_df.empty:
                    display_df = edge_cases_df[['matricule', 'nom', 'prenom', 
                                               'salaire_brut', 'edge_case_reason']]
                    st.dataframe(display_df, use_container_width=True)
                else:
                    st.success("Aucun cas particulier détecté")
        else:
            st.info("Aucune donnée pour cette période. Commencez par importer les données.")
    else:
        st.warning("Sélectionnez une entreprise et une période")


def import_page():
    """Page d'import des données"""
    st.header("📥 Import des données")
    
    system = st.session_state.payroll_system
    
    tab1, tab2 = st.tabs(["Import Excel", "Télécharger Template"])
    
    with tab1:
        st.subheader("Importer les données depuis Excel")
        
        uploaded_file = st.file_uploader(
            "Choisir un fichier Excel",
            type=['xlsx', 'xls'],
            help="Le fichier doit respecter le format du template"
        )
        
        if uploaded_file:
            try:
                # Lire et valider le fichier
                df_import = system.excel_manager.import_from_excel(uploaded_file)
                
                st.success(f"✅ {len(df_import)} employés importés avec succès")
                
                # Afficher un aperçu
                st.subheader("Aperçu des données importées")
                st.dataframe(df_import.head(10), use_container_width=True)
                
                # Bouton pour sauvegarder
                if st.button("💾 Sauvegarder les données", type="primary", use_container_width=True):
                    year, month = map(int, st.session_state.current_period.split('-'))
                    company_id = st.session_state.current_company.replace(' ', '_')
                    
                    system.data_consolidator.save_period_data(
                        df_import,
                        company_id,
                        year,
                        month
                    )
                    
                    st.success("Données sauvegardées avec succès!")
                    st.balloons()
                    
            except Exception as e:
                st.error(f"Erreur lors de l'import: {str(e)}")
    
    with tab2:
        st.subheader("Télécharger le template Excel")
        
        st.info("""
        Le template contient toutes les colonnes nécessaires pour l'import:
        - Informations des employés
        - Salaires et heures
        - Primes et avantages
        - Absences et congés
        """)
        
        if st.button("📥 Télécharger le template", use_container_width=True):
            template_buffer = system.excel_manager.create_template()
            
            st.download_button(
                label="💾 Télécharger template.xlsx",
                data=template_buffer.getvalue(),
                file_name=f"template_paie_{st.session_state.current_period}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


def processing_page():
    """Page de traitement des paies"""
    st.header("💰 Traitement des paies")
    
    system = st.session_state.payroll_system
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.info("""
        Le traitement automatique va:
        1. Calculer tous les salaires et charges
        2. Détecter les cas particuliers
        3. Générer tous les documents PDF
        """)
    
    with col2:
        if st.button("🚀 Lancer le traitement", type="primary", use_container_width=True):
            with st.spinner("Traitement en cours..."):
                company_id = st.session_state.current_company.replace(' ', '_')
                report = system.process_monthly_payroll(
                    company_id,
                    st.session_state.current_period
                )
            
            if report.get('success'):
                st.success("✅ Traitement terminé avec succès!")
                
                # Afficher le rapport
                for step in report['steps']:
                    if step['status'] == 'success':
                        st.write(f"✓ {step['step']}")
                
                # Afficher les statistiques
                st.markdown("---")
                st.subheader("Résultats du traitement")
                
                if 'processed_data' in st.session_state:
                    df = st.session_state.processed_data
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Fiches traitées", len(df))
                    
                    with col2:
                        validated = (df['statut_validation'] == 'Validé').sum()
                        st.metric("Validées automatiquement", f"{validated} ({validated/len(df)*100:.1f}%)")
                    
                    with col3:
                        edge_cases = df['edge_case_flag'].sum()
                        st.metric("Cas à vérifier", edge_cases)
            else:
                st.error(f"Erreur: {report.get('error', 'Erreur inconnue')}")


def validation_page():
    """Page de validation des cas particuliers"""
    st.header("✅ Validation des cas particuliers")
    
    if 'edge_cases' not in st.session_state or not st.session_state.edge_cases:
        st.info("Aucun cas particulier à valider")
        return
    
    edge_cases = st.session_state.edge_cases
    
    st.write(f"**{len(edge_cases)} cas à vérifier**")
    
    for i, case in enumerate(edge_cases):
        with st.expander(f"⚠️ {case['nom']} {case['prenom']} - {case['matricule']}"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Problèmes détectés:**")
                for issue in case.get('issues', []):
                    st.write(f"• {issue}")
                
                if case.get('remarques'):
                    st.write(f"**Remarques:** {case['remarques']}")
                
                if case.get('date_sortie'):
                    st.write(f"**Date de sortie:** {case['date_sortie']}")
            
            with col2:
                if st.button(f"Valider", key=f"validate_{i}"):
                    # Update validation status
                    if 'processed_data' in st.session_state:
                        df = st.session_state.processed_data
                        mask = df['matricule'] == case['matricule']
                        df.loc[mask, 'statut_validation'] = 'Validé'
                        df.loc[mask, 'edge_case_flag'] = False
                        
                        # Remove from edge cases
                        st.session_state.edge_cases.pop(i)
                        st.success(f"✅ Fiche validée pour {case['nom']} {case['prenom']}")
                        st.rerun()


def documents_page():
    """Page de génération et téléchargement des documents"""
    st.header("📄 Documents PDF")
    
    if 'generated_documents' not in st.session_state:
        st.warning("Aucun document généré. Lancez d'abord le traitement des paies.")
        return
    
    documents = st.session_state.generated_documents
    
    tab1, tab2, tab3 = st.tabs(["Bulletins individuels", "Journal de paie", "Provision CP"])
    
    with tab1:
        st.subheader("Bulletins de paie individuels")
        
        if 'paystubs' in documents:
            paystubs = documents['paystubs']
            st.write(f"**{len(paystubs)} bulletins disponibles**")
            
            # Recherche
            search = st.text_input("🔍 Rechercher un employé")
            
            # Filtrer les bulletins
            filtered = paystubs
            if search:
                filtered = [p for p in paystubs 
                          if search in p['nom'].lower()
                            or search in p['prenom'].lower()
                            or search in p['matricule'].lower()]
            for p in filtered:
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    st.write(f"• {p['nom']} {p['prenom']} - {p['matricule']}")
