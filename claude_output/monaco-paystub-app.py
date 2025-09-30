"""
Monaco Paystub Management System
=================================
Système de gestion des bulletins de paie pour Monaco
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
import os
from pathlib import Path
import hashlib
import json
from typing import Dict, List, Optional, Tuple
import pyarrow.parquet as pq
import pyarrow as pa

# Configuration
st.set_page_config(
    page_title="Système de Paie Monaco",
    page_icon="🇲🇨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
DATA_DIR = Path("data")
USERS_FILE = DATA_DIR / "users.parquet"
COMPANIES_DIR = DATA_DIR / "companies"
PAYSTUBS_DIR = DATA_DIR / "paystubs"
ARCHIVES_DIR = DATA_DIR / "archives"

# Create directories if they don't exist
for directory in [DATA_DIR, COMPANIES_DIR, PAYSTUBS_DIR, ARCHIVES_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.current_company = None
    st.session_state.current_period = None

class AuthManager:
    """Gestion de l'authentification et des utilisateurs"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def verify_user(username: str, password: str) -> Optional[Dict]:
        """Vérifier les credentials de l'utilisateur"""
        if not USERS_FILE.exists():
            # Create default admin user
            AuthManager.create_default_users()
        
        users_df = pd.read_parquet(USERS_FILE)
        user_row = users_df[users_df['username'] == username]
        
        if not user_row.empty:
            hashed_pw = AuthManager.hash_password(password)
            if user_row.iloc[0]['password'] == hashed_pw:
                return {
                    'username': username,
                    'role': user_row.iloc[0]['role'],
                    'name': user_row.iloc[0]['name']
                }
        return None
    
    @staticmethod
    def create_default_users():
        """Créer les utilisateurs par défaut"""
        default_users = pd.DataFrame([
            {
                'username': 'admin',
                'password': AuthManager.hash_password('admin123'),
                'role': 'admin',
                'name': 'Administrateur',
                'created_at': datetime.now()
            },
            {
                'username': 'comptable',
                'password': AuthManager.hash_password('compta123'),
                'role': 'accountant',
                'name': 'Comptable Test',
                'created_at': datetime.now()
            }
        ])
        default_users.to_parquet(USERS_FILE)

class DataManager:
    """Gestion des données de paie"""
    
    @staticmethod
    def get_company_file(company_id: str, period: str) -> Path:
        """Obtenir le chemin du fichier parquet pour une entreprise et période"""
        return PAYSTUBS_DIR / f"{company_id}_{period}.parquet"
    
    @staticmethod
    def load_paystub_data(company_id: str, period: str) -> pd.DataFrame:
        """Charger les données de paie pour une entreprise"""
        file_path = DataManager.get_company_file(company_id, period)
        if file_path.exists():
            return pd.read_parquet(file_path)
        else:
            return DataManager.create_empty_paystub_df()
    
    @staticmethod
    def save_paystub_data(df: pd.DataFrame, company_id: str, period: str):
        """Sauvegarder les données de paie"""
        file_path = DataManager.get_company_file(company_id, period)
        df.to_parquet(file_path)
    
    @staticmethod
    def create_empty_paystub_df() -> pd.DataFrame:
        """Créer un DataFrame vide avec la structure correcte"""
        columns = [
            'matricule', 'nom', 'prenom', 'base_heures', 'heures_conges_payes',
            'heures_absence', 'type_absence', 'prime', 'type_prime',
            'heures_sup_125', 'heures_sup_150', 'heures_jours_feries',
            'heures_dimanche', 'tickets_restaurant', 'avantage_logement',
            'avantage_transport', 'date_sortie', 'remarques',
            'salaire_base', 'salaire_brut', 'charges_salariales',
            'charges_patronales', 'net_a_payer', 'statut_validation',
            'edge_case_flag', 'edge_case_reason'
        ]
        return pd.DataFrame(columns=columns)
    
    @staticmethod
    def get_companies_list() -> List[Dict]:
        """Obtenir la liste des entreprises"""
        companies_file = COMPANIES_DIR / "companies.parquet"
        if companies_file.exists():
            df = pd.read_parquet(companies_file)
            return df.to_dict('records')
        else:
            # Create sample companies
            sample_companies = pd.DataFrame([
                {'id': 'CARAX', 'name': 'CARAX MONACO', 'siret': '763000000'},
                {'id': 'RGCAP', 'name': 'RG CAPITAL SERVICES', 'siret': '169000000'}
            ])
            sample_companies.to_parquet(companies_file)
            return sample_companies.to_dict('records')

class PayrollCalculator:
    """Calculs de paie spécifiques à Monaco"""
    
    # Taux de charges sociales Monaco (2024)
    CHARGES_SALARIALES = {
        'CAR': 0.0685,  # Caisse Autonome des Retraites
        'ASSEDIC_T1': 0.024,  # Assurance chômage tranche 1
        'ASSEDIC_T2': 0.024,  # Assurance chômage tranche 2
        'RETRAITE_COMP_T1': 0.0315,  # Retraite complémentaire T1
        'RETRAITE_COMP_T2': 0.0864,  # Retraite complémentaire T2
        'CCSS': 0.1475  # Caisse de Compensation des Services Sociaux
    }
    
    CHARGES_PATRONALES = {
        'CAR': 0.0835,
        'ASSEDIC_T1': 0.0405,
        'ASSEDIC_T2': 0.0405,
        'RETRAITE_COMP_T1': 0.0472,
        'RETRAITE_COMP_T2': 0.1295,
        'CMRC': 0.0522  # Caisse Monégasque de Retraite Complémentaire
    }
    
    PLAFOND_SS = 3428  # Plafond Sécurité Sociale mensuel 2024
    
    @staticmethod
    def calculate_overtime(hours_125: float, hours_150: float, hourly_rate: float) -> float:
        """Calculer les heures supplémentaires"""
        return (hours_125 * hourly_rate * 1.25) + (hours_150 * hourly_rate * 1.50)
    
    @staticmethod
    def calculate_social_charges(gross_salary: float) -> Tuple[float, float]:
        """Calculer les charges sociales (salariales et patronales)"""
        # Simplified calculation - should be more complex in production
        employee_charges = gross_salary * 0.22  # ~22% charges salariales
        employer_charges = gross_salary * 0.35  # ~35% charges patronales
        return employee_charges, employer_charges
    
    @staticmethod
    def calculate_net_salary(gross_salary: float, employee_charges: float) -> float:
        """Calculer le salaire net"""
        return gross_salary - employee_charges

class PayrollAgent:
    """Agent automatique pour traiter les fiches de paie"""
    
    @staticmethod
    def process_paystubs(df: pd.DataFrame) -> pd.DataFrame:
        """Traiter automatiquement les fiches de paie"""
        processed_df = df.copy()
        
        for idx, row in processed_df.iterrows():
            # Calculate base salary
            if pd.notna(row['base_heures']) and row['base_heures'] > 0:
                hourly_rate = row.get('salaire_base', 0) / row['base_heures'] if row.get('salaire_base', 0) > 0 else 20.0
                
                # Calculate overtime
                overtime = PayrollCalculator.calculate_overtime(
                    row.get('heures_sup_125', 0),
                    row.get('heures_sup_150', 0),
                    hourly_rate
                )
                
                # Calculate gross salary
                gross_salary = row.get('salaire_base', 0) + overtime + row.get('prime', 0)
                processed_df.at[idx, 'salaire_brut'] = gross_salary
                
                # Calculate charges
                employee_charges, employer_charges = PayrollCalculator.calculate_social_charges(gross_salary)
                processed_df.at[idx, 'charges_salariales'] = employee_charges
                processed_df.at[idx, 'charges_patronales'] = employer_charges
                
                # Calculate net salary
                net_salary = PayrollCalculator.calculate_net_salary(gross_salary, employee_charges)
                processed_df.at[idx, 'net_a_payer'] = net_salary
                
                # Flag edge cases
                edge_case, reason = PayrollAgent.detect_edge_cases(row, gross_salary)
                processed_df.at[idx, 'edge_case_flag'] = edge_case
                processed_df.at[idx, 'edge_case_reason'] = reason
                processed_df.at[idx, 'statut_validation'] = 'À vérifier' if edge_case else 'Validé'
        
        return processed_df
    
    @staticmethod
    def detect_edge_cases(row: pd.Series, gross_salary: float) -> Tuple[bool, str]:
        """Détecter les cas particuliers nécessitant une vérification manuelle"""
        reasons = []
        
        # Check for unusual values
        if gross_salary > 15000:
            reasons.append("Salaire brut élevé (>15000€)")
        if gross_salary < 1800:
            reasons.append("Salaire brut faible (<1800€)")
        
        # Check for termination
        if pd.notna(row.get('date_sortie')):
            reasons.append("Salarié sortant")
        
        # Check for excessive overtime
        if row.get('heures_sup_125', 0) + row.get('heures_sup_150', 0) > 40:
            reasons.append("Heures supplémentaires excessives (>40h)")
        
        # Check for long absence
        if row.get('heures_absence', 0) > 80:
            reasons.append("Absence prolongée (>80h)")
        
        if reasons:
            return True, "; ".join(reasons)
        return False, ""

def login_page():
    """Page de connexion"""
    st.title("🇲🇨 Système de Gestion des Paies - Monaco")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("Connexion")
        
        with st.form("login_form"):
            username = st.text_input("Nom d'utilisateur")
            password = st.text_input("Mot de passe", type="password")
            submit = st.form_submit_button("Se connecter", use_container_width=True)
            
            if submit:
                user = AuthManager.verify_user(username, password)
                if user:
                    st.session_state.authenticated = True
                    st.session_state.user = user['username']
                    st.session_state.role = user['role']
                    st.success(f"Bienvenue, {user['name']}!")
                    st.rerun()
                else:
                    st.error("Nom d'utilisateur ou mot de passe incorrect")
        
        st.info("**Demo:** admin/admin123 ou comptable/compta123")

def main_app():
    """Application principale"""
    # Sidebar
    with st.sidebar:
        st.title("Navigation")
        st.write(f"👤 **Utilisateur:** {st.session_state.user}")
        st.write(f"🔐 **Rôle:** {st.session_state.role}")
        
        st.markdown("---")
        
        # Company selection
        companies = DataManager.get_companies_list()
        company_names = [c['name'] for c in companies]
        selected_company = st.selectbox(
            "Sélectionner une entreprise",
            company_names,
            index=0 if company_names else None
        )
        
        if selected_company:
            company = next((c for c in companies if c['name'] == selected_company), None)
            st.session_state.current_company = company['id']
        
        # Period selection
        current_month = datetime.now().strftime("%Y-%m")
        period = st.text_input("Période (YYYY-MM)", value=current_month)
        st.session_state.current_period = period
        
        st.markdown("---")
        
        # Navigation menu
        page = st.radio(
            "Menu",
            ["📊 Tableau de bord", "👥 Gestion des salariés", "💰 Traitement des paies",
             "📄 Génération des documents", "⚙️ Configuration"]
        )
        
        st.markdown("---")
        
        if st.button("🚪 Déconnexion", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user = None
            st.session_state.role = None
            st.rerun()
    
    # Main content
    st.title(f"Gestion des Paies - {selected_company}")
    st.write(f"**Période:** {period}")
    
    if page == "📊 Tableau de bord":
        dashboard_page()
    elif page == "👥 Gestion des salariés":
        employees_page()
    elif page == "💰 Traitement des paies":
        payroll_processing_page()
    elif page == "📄 Génération des documents":
        documents_page()
    elif page == "⚙️ Configuration":
        if st.session_state.role == 'admin':
            configuration_page()
        else:
            st.error("Accès réservé aux administrateurs")

def dashboard_page():
    """Page tableau de bord"""
    st.header("📊 Tableau de bord")
    
    # Load current period data
    if st.session_state.current_company and st.session_state.current_period:
        df = DataManager.load_paystub_data(
            st.session_state.current_company,
            st.session_state.current_period
        )
        
        # Statistics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Nombre de salariés", len(df))
        
        with col2:
            total_brut = df['salaire_brut'].sum() if 'salaire_brut' in df.columns else 0
            st.metric("Masse salariale brute", f"{total_brut:,.2f} €")
        
        with col3:
            edge_cases = df['edge_case_flag'].sum() if 'edge_case_flag' in df.columns else 0
            st.metric("Cas à vérifier", edge_cases)
        
        with col4:
            validated = (df['statut_validation'] == 'Validé').sum() if 'statut_validation' in df.columns else 0
            st.metric("Fiches validées", f"{validated}/{len(df)}")
        
        # Charts
        st.markdown("---")
        
        if not df.empty and 'salaire_brut' in df.columns:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Répartition des salaires")
                salary_ranges = pd.cut(df['salaire_brut'], bins=5)
                st.bar_chart(salary_ranges.value_counts())
            
            with col2:
                st.subheader("Statut de validation")
                if 'statut_validation' in df.columns:
                    status_counts = df['statut_validation'].value_counts()
                    st.bar_chart(status_counts)
    else:
        st.info("Sélectionnez une entreprise et une période pour afficher le tableau de bord")

def employees_page():
    """Page de gestion des salariés"""
    st.header("👥 Gestion des salariés")
    
    if st.session_state.current_company and st.session_state.current_period:
        df = DataManager.load_paystub_data(
            st.session_state.current_company,
            st.session_state.current_period
        )
        
        # Add new employee
        with st.expander("➕ Ajouter un salarié"):
            with st.form("add_employee"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    matricule = st.text_input("Matricule")
                    nom = st.text_input("Nom")
                    prenom = st.text_input("Prénom")
                
                with col2:
                    base_heures = st.number_input("Base heures", value=169.0)
                    salaire_base = st.number_input("Salaire de base", value=0.0)
                    tickets_restaurant = st.number_input("Tickets restaurant", value=0)
                
                with col3:
                    avantage_logement = st.number_input("Avantage logement", value=0.0)
                    avantage_transport = st.number_input("Avantage transport", value=0.0)
                
                if st.form_submit_button("Ajouter"):
                    new_row = {
                        'matricule': matricule,
                        'nom': nom,
                        'prenom': prenom,
                        'base_heures': base_heures,
                        'salaire_base': salaire_base,
                        'tickets_restaurant': tickets_restaurant,
                        'avantage_logement': avantage_logement,
                        'avantage_transport': avantage_transport,
                        'statut_validation': 'À traiter'
                    }
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    DataManager.save_paystub_data(df, st.session_state.current_company, st.session_state.current_period)
                    st.success("Salarié ajouté avec succès")
                    st.rerun()
        
        # Display employees
        st.subheader("Liste des salariés")
        
        if not df.empty:
            # Allow editing
            edited_df = st.data_editor(
                df,
                use_container_width=True,
                num_rows="dynamic",
                key="employees_editor"
            )
            
            # Save changes
            if st.button("💾 Sauvegarder les modifications"):
                DataManager.save_paystub_data(edited_df, st.session_state.current_company, st.session_state.current_period)
                st.success("Modifications sauvegardées")
                st.rerun()
        else:
            st.info("Aucun salarié pour cette période")
    else:
        st.info("Sélectionnez une entreprise et une période")

def payroll_processing_page():
    """Page de traitement des paies"""
    st.header("💰 Traitement des paies")
    
    if st.session_state.current_company and st.session_state.current_period:
        df = DataManager.load_paystub_data(
            st.session_state.current_company,
            st.session_state.current_period
        )
        
        if not df.empty:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.subheader("Traitement automatique")
                
                if st.button("🤖 Lancer le traitement automatique", type="primary", use_container_width=True):
                    with st.spinner("Traitement en cours..."):
                        processed_df = PayrollAgent.process_paystubs(df)
                        DataManager.save_paystub_data(
                            processed_df,
                            st.session_state.current_company,
                            st.session_state.current_period
                        )
                        
                        # Show results
                        total = len(processed_df)
                        validated = (processed_df['statut_validation'] == 'Validé').sum()
                        edge_cases = processed_df['edge_case_flag'].sum()
                        
                        st.success(f"""
                        ✅ Traitement terminé!
                        - {validated}/{total} fiches validées automatiquement ({validated/total*100:.1f}%)
                        - {edge_cases} cas nécessitant une vérification manuelle
                        """)
                        st.rerun()
            
            with col2:
                st.subheader("Statistiques")
                validated = (df['statut_validation'] == 'Validé').sum() if 'statut_validation' in df.columns else 0
                to_check = (df['statut_validation'] == 'À vérifier').sum() if 'statut_validation' in df.columns else 0
                to_process = (df['statut_validation'] == 'À traiter').sum() if 'statut_validation' in df.columns else 0
                
                st.metric("Validées", validated)
                st.metric("À vérifier", to_check)
                st.metric("À traiter", to_process)
            
            # Show edge cases
            st.markdown("---")
            st.subheader("Cas particuliers à vérifier")
            
            if 'edge_case_flag' in df.columns:
                edge_cases_df = df[df['edge_case_flag'] == True]
                
                if not edge_cases_df.empty:
                    for idx, row in edge_cases_df.iterrows():
                        with st.expander(f"⚠️ {row['nom']} {row['prenom']} - {row['matricule']}"):
                            st.warning(f"**Raison:** {row.get('edge_case_reason', 'Non spécifié')}")
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.write(f"**Salaire brut:** {row.get('salaire_brut', 0):,.2f} €")
                            with col2:
                                st.write(f"**Net à payer:** {row.get('net_a_payer', 0):,.2f} €")
                            with col3:
                                if st.button(f"Valider", key=f"validate_{idx}"):
                                    df.at[idx, 'statut_validation'] = 'Validé'
                                    df.at[idx, 'edge_case_flag'] = False
                                    DataManager.save_paystub_data(
                                        df,
                                        st.session_state.current_company,
                                        st.session_state.current_period
                                    )
                                    st.success("Fiche validée")
                                    st.rerun()
                else:
                    st.success("Aucun cas particulier détecté")
        else:
            st.info("Aucune donnée à traiter. Ajoutez d'abord des salariés.")
    else:
        st.info("Sélectionnez une entreprise et une période")

def documents_page():
    """Page de génération des documents"""
    st.header("📄 Génération des documents")
    
    if st.session_state.current_company and st.session_state.current_period:
        df = DataManager.load_paystub_data(
            st.session_state.current_company,
            st.session_state.current_period
        )
        
        if not df.empty:
            st.subheader("Documents disponibles")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.info("📋 **Bulletins de paie**")
                if st.button("Générer les bulletins", use_container_width=True):
                    st.warning("⏳ Module PDF en attente de spécifications détaillées")
            
            with col2:
                st.info("📊 **Journal de paie**")
                if st.button("Générer le journal", use_container_width=True):
                    st.warning("⏳ Module PDF en attente de spécifications détaillées")
            
            with col3:
                st.info("🏖️ **Provision congés payés**")
                if st.button("Générer la provision", use_container_width=True):
                    st.warning("⏳ Module PDF en attente de spécifications détaillées")
            
            st.markdown("---")
            st.info("""
            📝 **Note:** Les modules de génération PDF seront développés selon vos spécifications détaillées.
            Les documents générés respecteront le format exact des exemples fournis.
            """)
        else:
            st.info("Aucune donnée disponible pour générer des documents")
    else:
        st.info("Sélectionnez une entreprise et une période")

def configuration_page():
    """Page de configuration (admin only)"""
    st.header("⚙️ Configuration")
    
    tab1, tab2, tab3 = st.tabs(["Utilisateurs", "Entreprises", "Paramètres"])
    
    with tab1:
        st.subheader("Gestion des utilisateurs")
        
        # Load users
        if USERS_FILE.exists():
            users_df = pd.read_parquet(USERS_FILE)
            
            # Display users
            st.dataframe(users_df[['username', 'name', 'role', 'created_at']], use_container_width=True)
            
            # Add new user
            with st.expander("Ajouter un utilisateur"):
                with st.form("add_user"):
                    username = st.text_input("Nom d'utilisateur")
                    name = st.text_input("Nom complet")
                    password = st.text_input("Mot de passe", type="password")
                    role = st.selectbox("Rôle", ["accountant", "admin"])
                    
                    if st.form_submit_button("Ajouter"):
                        new_user = {
                            'username': username,
                            'password': AuthManager.hash_password(password),
                            'name': name,
                            'role': role,
                            'created_at': datetime.now()
                        }
                        users_df = pd.concat([users_df, pd.DataFrame([new_user])], ignore_index=True)
                        users_df.to_parquet(USERS_FILE)
                        st.success("Utilisateur ajouté")
                        st.rerun()
    
    with tab2:
        st.subheader("Gestion des entreprises")
        
        companies = DataManager.get_companies_list()
        st.dataframe(pd.DataFrame(companies), use_container_width=True)
        
        # Add new company
        with st.expander("Ajouter une entreprise"):
            with st.form("add_company"):
                company_id = st.text_input("ID Entreprise")
                company_name = st.text_input("Nom de l'entreprise")
                siret =