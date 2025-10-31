"""
Import Page - Import des données
"""
import streamlit as st
import polars as pl
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.shared_utils import require_company_and_period, get_payroll_system
from services.data_mgt import DataManager

st.set_page_config(page_title="Import", page_icon="📥", layout="wide")

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
            st.dataframe(df_import.head(10), use_container_width=True)

            if st.button("💾 Sauvegarder les données", type="primary", use_container_width=True):
                month, year = map(int, st.session_state.current_period.split('-'))

                DataManager.save_period_data(
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
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
