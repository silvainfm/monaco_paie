"""
Export Page - Exporter les résultats
"""
import streamlit as st
import polars as pl
import io
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.shared_utils import require_company_and_period, render_sidebar
from services.data_mgt import DataManager

# Import send_validation_email function from Email page
# Note: We'll import it at runtime to avoid circular imports
try:
    from xlsxwriter import Workbook
    HAS_EXCEL = True
except ImportError:
    HAS_EXCEL = False

st.set_page_config(page_title="Export", page_icon="📤", layout="wide")

# Render sidebar with company/period selection
render_sidebar()

st.header("📄 Exporter les résultats")

if not require_company_and_period():
    st.stop()

month, year = map(int, st.session_state.current_period.split('-'))

df = DataManager.load_period_data(st.session_state.current_company, month, year)

if df.is_empty():
    st.warning("Aucune donnée à exporter. Lancez d'abord le traitement des paies.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Exporter par Excel", "Voir le Rapport", "Envoi Validation Client"])

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

with tab3:
    # Import the email page function
    import importlib.util
    spec = importlib.util.spec_from_file_location("email_page", Path(__file__).parent / "7_📧_Email.py")
    if spec and spec.loader:
        email_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(email_module)
        if hasattr(email_module, 'send_validation_email_page'):
            email_module.send_validation_email_page()
        else:
            st.error("La fonction send_validation_email_page n'a pas été trouvée dans le module Email")
    else:
        st.error("Impossible de charger le module Email. Veuillez créer la page 7_📧_Email.py")
