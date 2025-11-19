"""
Import Page - Import des données
"""
import streamlit as st
import polars as pl
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.shared_utils import require_company_and_period, get_payroll_system, render_sidebar
from services.data_mgt import DataManager

st.set_page_config(page_title="Import", page_icon="📥", layout="wide")

# Render sidebar with company/period selection
render_sidebar()

st.header("📥 Import des données")

if not require_company_and_period():
    st.stop()

system = get_payroll_system()

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
            # Use ExcelImportExport for proper validation and column mapping
            if uploaded_file.name.endswith('.csv'):
                # CSV: read and apply filtered mapping
                dtypes = {"Matricule": pl.Utf8}
                df_import = pl.read_csv(uploaded_file, dtypes=dtypes)
                # Only rename columns that exist (support case/accent variants)
                rename_mapping = {k: v for k, v in system.excel_manager.EXCEL_COLUMN_MAPPING.items() if k in df_import.columns}
                df_import = df_import.rename(rename_mapping)
                # Ensure matricule is string
                if 'matricule' in df_import.columns:
                    df_import = df_import.with_columns(pl.col('matricule').cast(pl.Utf8, strict=False))
            else:
                # Excel: use full import method with validation
                df_import = system.excel_manager.import_from_excel(uploaded_file)

            st.success(f"✅ {len(df_import)} employés importés avec succès")

            st.subheader("Aperçu des données importées")
            st.dataframe(df_import.head(10), width='stretch')

            # Check for existing employees
            month, year = map(int, st.session_state.current_period.split('-'))
            check_result = DataManager.check_existing_employees(
                df_import,
                st.session_state.current_company,
                month,
                year
            )

            # Show import summary
            st.markdown("---")
            st.subheader("📊 Résumé de l'import")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total à importer", len(df_import))
            with col2:
                st.metric("Nouveaux employés", len(check_result['new']), delta=len(check_result['new']))
            with col3:
                st.metric("Employés existants", len(check_result['existing']),
                         delta=f"-{len(check_result['existing'])}" if check_result['existing'] else None,
                         delta_color="inverse")

            # Warn about existing employees
            if check_result['existing']:
                st.warning(f"""
                ⚠️ **Attention:** {len(check_result['existing'])} employé(s) existe(nt) déjà pour cette période.

                En sauvegardant, vous allez **écraser** les données existantes pour ces employés:
                """)

                with st.expander("Voir les employés qui seront écrasés"):
                    for emp in check_result['existing']:
                        st.write(f"• {emp['matricule']} - {emp['nom']} {emp['prenom']}")

            # Save button with confirmation
            save_label = "💾 Sauvegarder les données" if not check_result['existing'] else f"⚠️ Écraser {len(check_result['existing'])} employé(s) et sauvegarder"
            button_type = "primary" if not check_result['existing'] else "secondary"

            if st.button(save_label, type=button_type, use_container_width=True):
                DataManager.save_period_data(
                    df_import,
                    st.session_state.current_company,
                    month,
                    year
                )

                st.success(f"✅ Données sauvegardées! {len(check_result['new'])} nouveaux, {len(check_result['existing'])} mis à jour")

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

    if st.button("📥 Générer le template", width='stretch'):
        template_buffer = system.excel_manager.create_template()

        st.download_button(
            label="💾 Télécharger template.xlsx",
            data=template_buffer.getvalue(),
            file_name=f"template_paie_{st.session_state.current_period}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
