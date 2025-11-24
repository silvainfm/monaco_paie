"""
Payslip Editing Helpers
======================
Helper functions for payslip validation, editing, and data cleaning
"""

import json
import streamlit as st
import polars as pl
import numpy as np
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from functools import lru_cache
from services.payroll_calculations import MonacoPayrollConstants, ChargesSocialesMonaco, CalculateurPaieMonaco
from services.pdf_generation import PaystubPDFGenerator

# ============================================================================
# RUBRICS AND CODES
# ============================================================================

@lru_cache(maxsize=1)
def load_rubrics_from_excel() -> List[Dict]:
    """
    Load salary rubrics from config/acc_rem.xlsx

    Returns list of rubrics with filtering:
    - Excludes rubrics with 'X' in 'Ajout automatique' (auto-added by system)
    - Excludes rubrics with 'X' in 'Presence obligatoire' (mandatory presence)
    - Returns rubrics available for manual addition

    Returns:
        List of dicts with keys: code, label, field_name, calcul,
        cotisable_mc, cotisable_autres, base_cp, imposable
    """
    excel_path = Path("data/config") / "acc_rem.xlsx"

    if not excel_path.exists():
        return []

    try:
        df = pl.read_excel(excel_path)

        rubrics = []
        for row in df.iter_rows(named=True):
            # Filter logic: exclude auto and mandatory rubrics
            ajout_auto = str(row.get('Ajout automatique') or '').strip().upper() == 'X'
            presence_oblig = str(row.get('Presence obligatoire') or '').strip().upper() == 'X'

            # Skip if auto-added or mandatory
            if ajout_auto or presence_oblig:
                continue

            rubric = {
                'code': int(row['Rémunération']),
                'label': str(row['Libellé']),
                'field_name': str(row['field_name']),
                'calcul': str(row.get('Calcul') or ''),
                'cotisable_mc': str(row.get('Cotisable MC  ?') or '').strip().upper() == 'X',
                'cotisable_autres': str(row.get('Cotisable autres cot ?') or '').strip().upper() == 'X',
                'base_cp': str(row.get('Base CP') or '').strip().upper() == 'X',
                'imposable': str(row.get('Imposable ?') or '').strip().upper() == 'X',
            }
            rubrics.append(rubric)

        return rubrics
    except Exception as e:
        st.error(f"Erreur lors du chargement des rubriques: {e}")
        return []

def get_salary_rubrics() -> List[Dict]:
    """Get salary element rubrics from pdf_generation"""
    codes = PaystubPDFGenerator.RUBRIC_CODES

    return [
        {'code': codes['salaire_base'], 'label': 'Salaire Mensuel', 'field': 'salaire_base'},
        {'code': codes['prime_anciennete'], 'label': "Prime d'ancienneté", 'field': 'prime_anciennete'},
        {'code': codes['heures_sup_125'], 'label': 'Heures sup. 125%', 'field': 'heures_sup_125'},
        {'code': codes['heures_sup_150'], 'label': 'Heures sup. 150%', 'field': 'heures_sup_150'},
        {'code': codes['prime_performance'], 'label': 'Prime performance', 'field': 'prime'},
        {'code': codes['prime_autre'], 'label': 'Autre prime', 'field': 'prime_autre'},
        {'code': codes['prime_non_cotisable'], 'label': 'Prime non cotisable', 'field': 'prime_non_cotisable'},
        {'code': codes['jours_feries'], 'label': 'Jours fériés 100%', 'field': 'heures_jours_feries'},
        {'code': codes['absence_maladie'], 'label': 'Absence maladie', 'field': 'heures_absence'},
        {'code': codes['absence_cp'], 'label': 'Absence congés payés', 'field': 'heures_conges_payes'},
        {'code': codes['indemnite_cp'], 'label': 'Indemnité congés payés', 'field': 'jours_conges_pris'},
        {'code': codes['tickets_resto'], 'label': 'Tickets restaurant', 'field': 'tickets_restaurant'},
    ]

def get_all_available_salary_rubrics(year: int = None) -> List[Dict]:
    """Get all available salary rubrics including constants from MonacoPayrollConstants"""
    all_rubrics = []

    # Add standard salary rubrics
    codes = PaystubPDFGenerator.RUBRIC_CODES
    all_rubrics.extend([
        {'code': codes['salaire_base'], 'label': 'Salaire Mensuel', 'field': 'salaire_base'},
        {'code': codes['prime_anciennete'], 'label': "Prime d'ancienneté", 'field': 'prime_anciennete'},
        {'code': codes['heures_sup_125'], 'label': 'Heures sup. 125%', 'field': 'heures_sup_125'},
        {'code': codes['heures_sup_150'], 'label': 'Heures sup. 150%', 'field': 'heures_sup_150'},
        {'code': codes['prime_performance'], 'label': 'Prime performance', 'field': 'prime'},
        {'code': codes['prime_autre'], 'label': 'Autre prime', 'field': 'prime_autre'},
        {'code': codes['prime_non_cotisable'], 'label': 'Prime non cotisable', 'field': 'prime_non_cotisable'},
        {'code': codes['jours_feries'], 'label': 'Jours fériés 100%', 'field': 'heures_jours_feries'},
        {'code': codes['absence_maladie'], 'label': 'Absence maladie', 'field': 'heures_absence'},
        {'code': codes['absence_cp'], 'label': 'Absence congés payés', 'field': 'heures_conges_payes'},
        {'code': codes['indemnite_cp'], 'label': 'Indemnité congés payés', 'field': 'jours_conges_pris'},
        {'code': codes['tickets_resto'], 'label': 'Tickets restaurant', 'field': 'tickets_restaurant'},
        {'code': codes['maintien_salaire'], 'label': 'Maintien de salaire', 'field': 'maintien_salaire'},
    ])

    # Add constants from MonacoPayrollConstants CSV
    csv_path = Path("data/config") / "payroll_rates.csv"
    if csv_path.exists():
        try:
            df = pl.read_csv(csv_path)
            constants_df = df.filter(pl.col("category") == "CONSTANT")
            for row in constants_df.iter_rows(named=True):
                const_code = row["code"]
                const_desc = row.get("description", const_code)
                # Use the constant code as the field name (lowercase)
                all_rubrics.append({
                    'code': const_code,
                    'label': const_desc,
                    'field': const_code.lower()
                })
        except Exception as e:
            print(f"Error loading constants: {e}")

    return all_rubrics

def get_available_rubrics_for_employee(employee_data: Dict, year: int = None) -> List[Dict]:
    """Get rubrics not currently displayed for this employee"""
    # Load rubrics from Excel (filtered for manual addition)
    all_rubrics = load_rubrics_from_excel()

    # Get currently displayed fields (non-zero values)
    displayed_fields = set()
    for rubric in all_rubrics:
        field = rubric['field_name']
        if safe_get_numeric(employee_data, field, 0) != 0:
            displayed_fields.add(field)

    # Filter out displayed rubrics
    available = [r for r in all_rubrics if r['field_name'] not in displayed_fields]

    return available

def get_charge_rubrics() -> Dict[str, List[Dict]]:
    """Get social charge rubrics from payroll_calculations"""

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

def get_available_charges_for_employee(employee_data: Dict, year: int = None, month: int = None) -> List[Dict]:
    """Get charge codes not currently displayed for this employee"""

    # Initialize charges calculator
    charges_calc = ChargesSocialesMonaco(year, month)

    # Get all available charge codes
    all_charges = {}
    for code, params in charges_calc.COTISATIONS_SALARIALES.items():
        all_charges[code] = {
            'code': code,
            'label': params['description'],
            'taux_sal': params['taux'],
            'taux_pat': 0,
            'plafond': params['plafond'],
            'has_salarial': True,
            'has_patronal': False
        }

    # Merge with patronal charges
    for code, params in charges_calc.COTISATIONS_PATRONALES.items():
        if code in all_charges:
            all_charges[code]['taux_pat'] = params['taux']
            all_charges[code]['has_patronal'] = True
        else:
            all_charges[code] = {
                'code': code,
                'label': params['description'],
                'taux_sal': 0,
                'taux_pat': params['taux'],
                'plafond': params['plafond'],
                'has_salarial': False,
                'has_patronal': True
            }

    # Get currently displayed charges
    details_charges = employee_data.get('details_charges', {})
    charges_sal = details_charges.get('charges_salariales', {})
    charges_pat = details_charges.get('charges_patronales', {})

    displayed_codes = set()
    for code in charges_sal.keys():
        if charges_sal.get(code, 0) != 0:
            displayed_codes.add(code)
    for code in charges_pat.keys():
        if charges_pat.get(code, 0) != 0:
            displayed_codes.add(code)

    # Filter out displayed charges
    available = [charge for code, charge in all_charges.items() if code not in displayed_codes]

    return available

# ============================================================================
# PAYSLIP RECALCULATION
# ============================================================================

def recalculate_employee_payslip(employee_data: Dict, modifications: Dict,
                                 company_id: str = None, year: int = None, month: int = None) -> Dict:
    """Recalculate payslip after modifications"""

    # Deep copy and clean all numeric fields first
    updated_data = {}

    # Copy and clean all fields from employee_data
    for key, value in employee_data.items():
        if key in ['salaire_brut', 'salaire_base', 'salaire_net', 'total_charges_salariales',
                   'total_charges_patronales', 'heures_sup_125', 'heures_sup_150', 'prime',
                   'montant_hs_125', 'montant_hs_150', 'cout_total_employeur', 'taux_horaire',
                   'base_heures', 'heures_payees', 'retenue_absence', 'heures_absence',
                   'indemnite_cp', 'heures_jours_feries', 'montant_jours_feries',
                   'prime_anciennete', 'prime_autre', 'tickets_restaurant']:
            # Force numeric conversion
            if isinstance(value, dict):
                updated_data[key] = 0.0
            elif value is None: #pl.is_nan(value)
                updated_data[key] = 0.0
            else:
                try:
                    updated_data[key] = float(value)
                except (TypeError, ValueError):
                    updated_data[key] = 0.0
        else:
            updated_data[key] = value

    # Handle nested charges updates
    if 'charges_salariales' in modifications or 'charges_patronales' in modifications:
        if 'details_charges' not in updated_data:
            updated_data['details_charges'] = {'charges_salariales': {}, 'charges_patronales': {}}
        if not isinstance(updated_data['details_charges'], dict):
            updated_data['details_charges'] = {'charges_salariales': {}, 'charges_patronales': {}}

        if 'charges_salariales' in modifications:
            if 'charges_salariales' not in updated_data['details_charges']:
                updated_data['details_charges']['charges_salariales'] = {}
            updated_data['details_charges']['charges_salariales'].update(modifications['charges_salariales'])

        if 'charges_patronales' in modifications:
            if 'charges_patronales' not in updated_data['details_charges']:
                updated_data['details_charges']['charges_patronales'] = {}
            updated_data['details_charges']['charges_patronales'].update(modifications['charges_patronales'])

        # Remove from top-level modifications
        modifications = {k: v for k, v in modifications.items()
                        if k not in ['charges_salariales', 'charges_patronales']}

    # Apply remaining modifications (these are already numeric from the form inputs)
    updated_data.update(modifications)

    # Get cumulative annual gross salary for plafond calculations
    cumul_brut_annuel = 0.0
    if company_id and year and month:
        matricule = updated_data.get('matricule', '')
        if matricule:
            cumul_brut_annuel = DataManager.get_cumul_brut_annuel(
                company_id, matricule, year, month
            )

    # Recalculate
    calculator = CalculateurPaieMonaco()
    return calculator.process_employee_payslip(updated_data, cumul_brut_annuel=cumul_brut_annuel)

# ============================================================================
# DATA CLEANING AND VALIDATION
# ============================================================================

def clean_employee_data_for_pdf(employee_dict: Dict) -> Dict:
    """Clean employee data to ensure numeric fields are not dicts"""

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
            # Force numeric conversion - check None first
            if value is None:
                cleaned[key] = 0
            elif isinstance(value, dict):
                cleaned[key] = 0
            elif isinstance(value, (list, tuple)):
                cleaned[key] = 0
            elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                cleaned[key] = 0
            elif isinstance(value, (int, float, np.integer, np.floating)):
                cleaned[key] = float(value)
            else:
                try:
                    cleaned[key] = float(value)
                except (TypeError, ValueError, AttributeError):
                    cleaned[key] = 0
        else:
            # Keep non-numeric fields as-is, but handle None safely
            cleaned[key] = value if value is not None else ""

    return cleaned

def safe_get_charge_value(details_charges: Dict, charge_type: str, charge_code: str) -> float:
    """Safely extract charge value from details_charges structure"""
    try:
        charges = details_charges.get(charge_type, {})
        if isinstance(charges, dict):
            value = charges.get(charge_code, 0)
            if isinstance(value, dict):
                # If it's still a dict, try to extract 'montant' or 'value' key
                return float(value.get('montant', value.get('value', 0)))
            return float(value) if value is not None else 0.0
        return 0.0
    except (TypeError, ValueError, AttributeError):
        return 0.0

def safe_get_numeric(row: Dict, field: str, default: float = 0.0) -> float:
    """Safely extract numeric value from dict, handling nested structures"""
    try:
        value = row.get(field, default)
        if isinstance(value, dict):
            return float(value.get('montant', value.get('value', value.get('amount', default))))
        if value is None or (isinstance(value, float) and pl.datatypes.Float64.is_null(value)):
            return default
        return float(value)
    except (TypeError, ValueError, AttributeError):
        return default

# ============================================================================
# AUDIT AND MODIFICATION TRACKING
# ============================================================================
#
# TIME TRACKING USAGE:
# To enable automatic time tracking in your Streamlit app:
#
# 1. Add to main payslip validation page (where accountants work):
#    check_and_restart_time_tracking()
#
# 2. Add to logout/exit handlers:
#    stop_time_tracking()
#
# 3. View reports in audit_log_page() under "Suivi du Temps" tab
#
# Time tracking auto-starts when company/period selected, auto-stops when
# switching companies or exiting. Sessions < 10 seconds are ignored.
#
# ============================================================================

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

def log_time_entry(user: str, company: str, period: str, duration_seconds: float, session_start: str, session_end: str):
    """Log time spent on company payslips"""

    log_dir = Path("data/audit_logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_entry = {
        'timestamp': session_end,
        'entry_type': 'time_tracking',
        'user': user,
        'company': company,
        'period': period,
        'session_start': session_start,
        'session_end': session_end,
        'duration_seconds': duration_seconds,
        'duration_minutes': round(duration_seconds / 60, 2)
    }

    log_file = log_dir / f"modifications_{datetime.now().strftime('%Y%m')}.jsonl"
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

def start_time_tracking():
    """Start tracking time for current company/period"""
    if 'current_company' in st.session_state and 'current_period' in st.session_state:
        company = st.session_state.current_company
        period = st.session_state.current_period

        # Stop previous tracking if exists
        stop_time_tracking()

        # Start new tracking
        st.session_state.time_tracking_active = True
        st.session_state.time_tracking_start = datetime.now()
        st.session_state.time_tracking_company = company
        st.session_state.time_tracking_period = period

def stop_time_tracking():
    """Stop tracking time and log entry"""
    if st.session_state.get('time_tracking_active', False):
        end_time = datetime.now()
        start_time = st.session_state.time_tracking_start
        duration = (end_time - start_time).total_seconds()

        # Only log if session was > 10 seconds (avoid accidental clicks)
        if duration > 10:
            log_time_entry(
                user=st.session_state.get('user', 'unknown'),
                company=st.session_state.time_tracking_company,
                period=st.session_state.time_tracking_period,
                duration_seconds=duration,
                session_start=start_time.isoformat(),
                session_end=end_time.isoformat()
            )

        # Clear tracking state
        st.session_state.time_tracking_active = False
        st.session_state.time_tracking_start = None
        st.session_state.time_tracking_company = None
        st.session_state.time_tracking_period = None

def check_and_restart_time_tracking():
    """Check if company/period changed and restart tracking"""
    current_company = st.session_state.get('current_company')
    current_period = st.session_state.get('current_period')

    if st.session_state.get('time_tracking_active', False):
        tracking_company = st.session_state.get('time_tracking_company')
        tracking_period = st.session_state.get('time_tracking_period')

        # If company or period changed, stop old and start new
        if tracking_company != current_company or tracking_period != current_period:
            stop_time_tracking()
            start_time_tracking()
    else:
        # Start tracking if not active
        if current_company and current_period:
            start_time_tracking()

# ============================================================================
# AUDIT LOG PAGE
# ============================================================================

def audit_log_page():
    """View audit trail of modifications and time tracking"""
    st.header("📋 Journal des Modifications et Temps")

    if st.session_state.role != 'admin':
        st.error("Accès réservé aux administrateurs")
        return

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

    # Convert to Polars DataFrame
    logs_df = pl.DataFrame(all_logs)
    logs_df = logs_df.with_columns(
        pl.col('timestamp').str.strptime(pl.Datetime, format='%Y-%m-%dT%H:%M:%S%.f')
    ).sort('timestamp', descending=True)

    # Add entry_type column if missing (for backward compatibility)
    if 'entry_type' not in logs_df.columns:
        logs_df = logs_df.with_columns(
            pl.lit('modification').alias('entry_type')
        )

    # Separate time tracking and modification logs
    time_logs = logs_df.filter(pl.col('entry_type') == 'time_tracking')
    mod_logs = logs_df.filter(pl.col('entry_type') != 'time_tracking')

    # Tab selection
    tab1, tab2, tab3 = st.tabs(["Modifications", "Suivi du Temps", "Rapports Temps"])

    with tab1:
        st.subheader("Modifications")

        if mod_logs.is_empty():
            st.info("Aucune modification")
        else:
            # Filters
            col1, col2, col3 = st.columns(3)
            with col1:
                user_filter = st.selectbox("Utilisateur", ["Tous"] + mod_logs['user'].unique().to_list(), key="mod_user")
            with col2:
                period_filter = st.selectbox("Période", ["Toutes"] + mod_logs['period'].unique().to_list(), key="mod_period")
            with col3:
                matricule_filter = st.text_input("Matricule", key="mod_matricule")

            # Apply filters
            filtered = mod_logs
            if user_filter != "Tous":
                filtered = filtered.filter(pl.col('user') == user_filter)
            if period_filter != "Toutes":
                filtered = filtered.filter(pl.col('period') == period_filter)
            if matricule_filter:
                filtered = filtered.filter(pl.col('matricule').str.contains(f"(?i){matricule_filter}"))

            st.metric("Total modifications", len(filtered))

            # Display
            st.dataframe(
                filtered.select(['timestamp', 'user', 'matricule', 'field', 'old_value', 'new_value', 'reason']).to_pandas(),
                width='stretch'
            )

    with tab2:
        st.subheader("Sessions de Travail")

        if time_logs.is_empty():
            st.info("Aucune session enregistrée")
        else:
            # Filters
            col1, col2 = st.columns(2)
            with col1:
                time_user_filter = st.selectbox("Utilisateur", ["Tous"] + time_logs['user'].unique().to_list(), key="time_user")
            with col2:
                time_period_filter = st.selectbox("Période", ["Toutes"] + time_logs['period'].unique().to_list(), key="time_period")

            # Apply filters
            filtered_time = time_logs
            if time_user_filter != "Tous":
                filtered_time = filtered_time.filter(pl.col('user') == time_user_filter)
            if time_period_filter != "Toutes":
                filtered_time = filtered_time.filter(pl.col('period') == time_period_filter)

            # Metrics
            total_minutes = filtered_time['duration_minutes'].sum()
            total_hours = round(total_minutes / 60, 2)

            col1, col2, col3 = st.columns(3)
            col1.metric("Sessions", len(filtered_time))
            col2.metric("Total heures", f"{total_hours}h")
            col3.metric("Moy. par session", f"{round(total_minutes / max(len(filtered_time), 1), 1)} min")

            # Display
            st.dataframe(
                filtered_time.select(['timestamp', 'user', 'company', 'period', 'duration_minutes', 'session_start', 'session_end']).to_pandas(),
                width='stretch'
            )

    with tab3:
        st.subheader("Rapports de Temps")

        if time_logs.is_empty():
            st.info("Aucune donnée de temps")
        else:
            # Time per company/period
            st.markdown("### Temps par Client/Période")
            time_by_company = time_logs.group_by(['company', 'period']).agg([
                pl.col('duration_minutes').sum().alias('total_minutes'),
                pl.col('duration_minutes').count().alias('sessions')
            ]).with_columns(
                (pl.col('total_minutes') / 60).round(2).alias('total_hours')
            ).sort('total_minutes', descending=True)

            st.dataframe(
                time_by_company.select(['company', 'period', 'total_hours', 'sessions']).to_pandas(),
                width='stretch'
            )

            # Time per accountant
            st.markdown("### Temps par Comptable")
            time_by_user = time_logs.group_by('user').agg([
                pl.col('duration_minutes').sum().alias('total_minutes'),
                pl.col('duration_minutes').count().alias('sessions'),
                pl.col('company').n_unique().alias('clients')
            ]).with_columns(
                (pl.col('total_minutes') / 60).round(2).alias('total_hours')
            ).sort('total_minutes', descending=True)

            st.dataframe(
                time_by_user.select(['user', 'total_hours', 'sessions', 'clients']).to_pandas(),
                width='stretch'
            )

# ============================================================================
# UI HELPER FUNCTIONS
# ============================================================================

def _show_read_only_validation():
    """Show read-only view of payslips when editing is not allowed"""

    if 'processed_data' not in st.session_state or st.session_state.processed_data.is_empty():
        st.info("Aucune donnée disponible pour cette période.")
        return

    df = st.session_state.processed_data

    # Filter and search bar
    col1, col2 = st.columns([2, 2])
    with col1:
        search = st.text_input("🔍 Rechercher (matricule, nom, prénom)", "", key="readonly_search")
    with col2:
        status_filter = st.selectbox("Filtrer par statut",
                                     ["Tous", "À vérifier", "Validés"],
                                     key="readonly_status")

    # Apply filters
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

    # Display employees in read-only mode
    if filtered_df.is_empty():
        st.info("Aucun employé trouvé avec ces critères")
        return

    for row in filtered_df.iter_rows(named=True):
        matricule = row.get('matricule', '') or ''
        is_edge_case = row.get('edge_case_flag', False)
        is_validated = row.get('statut_validation', False) == True

        status_icon = "⚠️" if is_edge_case else ("✅" if is_validated else "⏳")
        nom = row.get('nom') or ''
        prenom = row.get('prenom') or ''
        title = f"{status_icon} {nom} {prenom} - {matricule} [LECTURE SEULE]"

        with st.expander(title):
            # Show issues if any
            if is_edge_case:
                st.warning(f"**Raison:** {row.get('edge_case_reason', 'Non spécifiée')}")

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Salaire brut", f"{row.get('salaire_brut', 0):,.2f} €")
            with col2:
                st.metric("Charges sal.", f"{row.get('total_charges_salariales', 0):,.2f} €")
            with col3:
                st.metric("Salaire net", f"{row.get('salaire_net', 0):,.2f} €")
            with col4:
                st.metric("Coût employeur", f"{row.get('cout_total_employeur', 0):,.2f} €")

            # Show detailed breakdown in tabs
            tab1, tab2 = st.tabs(["💰 Éléments de Salaire", "📊 Charges Sociales"])

            with tab1:
                st.markdown("**Éléments de rémunération:**")
                salary_rubrics = get_salary_rubrics()
                for rubric in salary_rubrics:
                    field = rubric['field']
                    value = safe_get_numeric(row, field, 0.0)
                    if value > 0:
                        st.text(f"• {rubric['label']} ({rubric['code']}): {value:.2f}")

            with tab2:
                details_charges = row.get('details_charges', {})
                if isinstance(details_charges, dict):
                    charges_sal = details_charges.get('charges_salariales', {})
                    charges_pat = details_charges.get('charges_patronales', {})

                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Charges salariales:**")
                        if isinstance(charges_sal, dict):
                            for code, amount in charges_sal.items():
                                val = safe_get_charge_value(details_charges, 'charges_salariales', code)
                                if val > 0:
                                    st.text(f"• {code}: {val:.2f} €")

                    with col2:
                        st.markdown("**Charges patronales:**")
                        if isinstance(charges_pat, dict):
                            for code, amount in charges_pat.items():
                                val = safe_get_charge_value(details_charges, 'charges_patronales', code)
                                if val > 0:
                                    st.text(f"• {code}: {val:.2f} €")
