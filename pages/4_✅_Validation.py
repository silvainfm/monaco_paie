"""
Validation Page - Validation et Modification des Paies
"""
import streamlit as st
import polars as pl
import sys
from pathlib import Path
from datetime import date

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.shared_utils import require_company_and_period, render_sidebar
from services.auth import AuthManager
from services.data_mgt import DataManager
from services.payslip_helpers import (
    get_salary_rubrics,
    get_available_rubrics_for_employee,
    get_available_charges_for_employee,
    safe_get_numeric,
    log_modification,
    recalculate_employee_payslip,
    _show_read_only_validation,
    check_and_restart_time_tracking
)

st.set_page_config(page_title="Validation", page_icon="✅", layout="wide")

# Render sidebar with company/period selection
render_sidebar()

st.header("✅ Validation et Modification des Paies")

if not require_company_and_period():
    st.stop()

# Start time tracking for this company/period
check_and_restart_time_tracking()

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
        st.stop()
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
    st.stop()

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

# Apply filters using optimized Polars expressions
filters = []

if search:
    # Use single contains check instead of multiple casts
    filters.append(
        pl.col('matricule').cast(pl.Utf8).str.to_lowercase().str.contains(search.lower()) |
        pl.col('nom').cast(pl.Utf8).str.to_lowercase().str.contains(search.lower()) |
        pl.col('prenom').cast(pl.Utf8).str.to_lowercase().str.contains(search.lower())
    )

if status_filter == "À vérifier":
    filters.append(pl.col('edge_case_flag') == True)
elif status_filter == "Validés":
    filters.append(pl.col('statut_validation') == True)

# Apply all filters at once
filtered_df = df.filter(pl.all_horizontal(filters)) if filters else df

st.markdown("---")

# Display employees
if filtered_df.is_empty():
    st.info("Aucun employé trouvé avec ces critères")
    st.stop()

for row_idx, row in enumerate(filtered_df.iter_rows(named=True)):
    matricule = row.get('matricule', '') or ''
    is_edge_case = row.get('edge_case_flag', False)
    is_validated = row.get('statut_validation', False) == True

    # Expander title with status indicator
    status_icon = "⚠️" if is_edge_case else ("✅" if is_validated else "⏳")
    nom = row.get('nom') or ''
    prenom = row.get('prenom') or ''
    title = f"{status_icon} {nom} {prenom} - {matricule}"

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

            # CHECK FOR MISSING DATE DE NAISSANCE
            current_date_naissance = row.get('date_naissance')
            if current_date_naissance is None or current_date_naissance == '' or str(current_date_naissance).strip() == '':
                st.warning("⚠️ **Date de naissance manquante** - Veuillez renseigner la date de naissance de cet employé")

                # Date input for missing date de naissance
                col_dob1, col_dob2 = st.columns([2, 3])
                with col_dob1:
                    new_date_naissance = st.date_input(
                        "Date de naissance",
                        value=date(1990, 1, 1),
                        key=f"date_naissance_{unique_key}",
                        format="DD/MM/YYYY"
                    )
                    if new_date_naissance:
                        st.session_state[mod_key]['date_naissance'] = new_date_naissance.strftime('%Y-%m-%d')
                        st.info(f"✅ Date de naissance sélectionnée: {new_date_naissance.strftime('%d/%m/%Y')}")

                st.markdown("---")

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

                # Assedic toggle
                assedic_toggle_key = f"assedic_toggle_{unique_key}"
                if assedic_toggle_key not in st.session_state:
                    st.session_state[assedic_toggle_key] = False

                has_assedic = st.toggle(
                    "Assurance Chômage (Assedic)",
                    value=st.session_state[assedic_toggle_key],
                    key=f"assedic_input_{unique_key}",
                    help="Activer pour inclure les charges d'assurance chômage"
                )
                st.session_state[assedic_toggle_key] = has_assedic

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
                    }
                ]

                # Add ASSEDIC_T1 if toggle is enabled
                if has_assedic:
                    charges_config.append({
                        'code': 'ASSEDIC_T1',
                        'name': 'Assurance Chômage T1',
                        'base_default': plafond_t1,
                        'taux_sal': 2.40,
                        'taux_pat': 4.05,
                        'has_salarial': True,
                        'has_patronal': True
                    })

                # Add T2 charges if applicable
                if base_t2 > 0:
                    t2_charges = []

                    # Add ASSEDIC_T2 only if toggle is enabled
                    if has_assedic:
                        t2_charges.append({
                            'code': 'ASSEDIC_T2',
                            'name': 'Assurance Chômage T2',
                            'base_default': base_t2,
                            'taux_sal': 2.40,
                            'taux_pat': 4.05,
                            'has_salarial': True,
                            'has_patronal': True
                        })

                    t2_charges.extend([
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

                    charges_config.extend(t2_charges)

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
                col_headers = st.columns([2, 3, 1.5, 1.5, 1.5, 2])
                col_headers[0].markdown("**Base**")
                col_headers[1].markdown("**Cotisation**")
                col_headers[2].markdown("**Taux Sal.**")
                col_headers[3].markdown("**Mont. Sal.**")
                col_headers[4].markdown("**Taux Pat.**")
                col_headers[5].markdown("**Mont. Pat.**")
                st.markdown("---")

                # Display each charge line
                for charge in charges_config:
                    cols = st.columns([2, 3, 1.5, 1.5, 1.5, 2])

                    # Get current values
                    current_sal = charges_sal.get(charge['code'], 0)
                    current_pat = charges_pat.get(charge['code'], 0)
                    current_base = st.session_state[bases_key].get(
                        charge['code'],
                        charge['base_default']
                    )

                    # Base (editable, shared between salarial and patronal)
                    new_base = cols[0].number_input(
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

                    # Charge name
                    cols[1].markdown(f"**{charge['name']}**")
                    cols[1].caption(f"Code: {charge['code']}")

                    # Salarial rate (display only)
                    if charge['has_salarial']:
                        cols[2].markdown(f"{charge['taux_sal']:.2f}%")
                    else:
                        cols[2].markdown("-")

                    # Salarial amount (editable)
                    if charge['has_salarial']:
                        new_sal = cols[3].number_input(
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
                        cols[3].markdown("-")

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
                total_cols = st.columns([2, 3, 1.5, 1.5, 1.5, 2])
                total_cols[1].markdown("**TOTAL**")

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

                total_cols[3].markdown(f"**{total_sal:.2f}€**")
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
                # Extract year and month from current period for rate determination
                month, year = map(int, st.session_state.current_period.split('-'))
                available_charges = get_available_charges_for_employee(row, year, month)

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

                        # Update DataFrame with modifications for this employee
                        for field, new_value in st.session_state[mod_key].items():
                            if field not in ['charge_bases', 'charges_salariales', 'charges_patronales']:
                                # Update only the row for this employee
                                if field in df.columns:
                                    df = df.with_columns([
                                        pl.when(pl.col('matricule') == matricule)
                                        .then(pl.lit(new_value))
                                        .otherwise(pl.col(field))
                                        .alias(field)
                                    ])

                        # Update session state with modified dataframe
                        st.session_state.processed_data = df

                        # Save to DuckDB
                        month, year = map(int, st.session_state.current_period.split('-'))
                        DataManager.save_period_data(
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

                        # Save to DuckDB
                        month, year = map(int, st.session_state.current_period.split('-'))
                        DataManager.save_period_data(
                            df, st.session_state.current_company, month, year
                        )

                        nom = row.get('nom') or ''
                        prenom = row.get('prenom') or ''
                        st.success(f"✅ Fiche validée pour {nom} {prenom}")
                        st.rerun()
                else:
                    st.success("✅ Déjà validé")
