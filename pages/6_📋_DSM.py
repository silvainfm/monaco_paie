"""
DSM Page - Déclaration DSM Monaco
"""
import streamlit as st
import polars as pl
import json
import time
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.payroll_system import IntegratedPayrollSystem
from services.dsm_xml_generator import DSMXMLGenerator
from services.data_mgt import DataManager
from services.payroll_calculations import MonacoPayrollConstants

CONFIG_DIR = Path("config")

st.set_page_config(page_title="DSM", page_icon="📋", layout="wide")

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

    if st.session_state.get('role') == "admin":
        with st.expander("➕ Configurer maintenant"):
            with st.form("quick_employer_config"):
                new_employer_number = st.text_input(
                    "Numéro d'employeur Monaco",
                    help="Numéro d'enregistrement auprès des Caisses Sociales de Monaco (5 chiffres requis)"
                )

                if st.form_submit_button("💾 Sauvegarder"):
                    if new_employer_number:
                        # Validate employer number is 5 digits
                        if not new_employer_number.isdigit() or len(new_employer_number) != 5:
                            st.error("Le numéro d'employeur Monaco doit être exactement 5 chiffres")
                        else:
                            company_info['employer_number_monaco'] = new_employer_number
                            config_file = CONFIG_DIR / "company_info.json"
                            with open(config_file, 'w', encoding='utf-8') as f:
                                json.dump(company_info, f, indent=2)
                            st.success("✅ Numéro d'employeur sauvegardé!")
                            time.sleep(1)
                            st.rerun()
    st.stop()

# Load period data
company_id = st.session_state.get('current_company')
period_str = st.session_state.get('current_period', datetime.now().strftime("%m-%Y"))

if not company_id:
    st.warning("Veuillez sélectionner une entreprise")
    st.stop()

# Convert period
try:
    period_date = datetime.strptime(period_str, "%m-%Y")
    period = period_date.strftime("%Y-%m")
    month_year = period_date.strftime("%B %Y")
except:
    st.error("Format de période invalide")
    st.stop()

year = period_date.year
month = period_date.month

# Load payroll data
df_period = DataManager.load_period_data(company_id, month, year)

if df_period.height == 0:
    st.warning(f"Aucune donnée de paie trouvée pour {month_year}")
    st.info("Veuillez d'abord traiter la paie pour cette période dans 'Traitement des paies'")
    st.stop()

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
