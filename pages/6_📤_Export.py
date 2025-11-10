"""
Export Page - Exporter les résultats
"""
import streamlit as st
import polars as pl
import io
import sys
from xlsxwriter import Workbook
from pathlib import Path
import streamlit as st
import polars as pl
import time
import sys
from pathlib import Path
from datetime import datetime
from xlsxwriter import Workbook

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.shared_utils import render_sidebar, require_company_and_period
from services.data_mgt import DataManager
from services.payroll_system import IntegratedPayrollSystem
from services.pdf_generation import PDFGeneratorService
from services.email_archive import create_email_distribution_system
from services.dsm_xml_generator import DSMXMLGenerator
from services.payroll_calculations import MonacoPayrollConstants
import json


# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

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

tab1, tab2, tab3, tab4 = st.tabs(["Exporter par Excel", "Voir le Rapport", "Envoi Validation Client", "DSM"])

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

            output = io.BytesIO()


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

            st.download_button(
                label="💾 Télécharger Excel",
                data=output.getvalue(),
                file_name=f"paies_{st.session_state.current_company}_{st.session_state.current_period}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
            st.error("Le module xlsxwriter n'est pas installé")
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
    # client email validation page
    st.info("📋 **Envoyer les bulletins pour validation client**")
    
    # Vérifier la configuration email
    config_path = Path("config/email_config.json")
    if not config_path.exists():
        st.error("❌ Configuration email non trouvée. Veuillez d'abord configurer l'email dans la page Configuration.")
        if st.button("➡️ Aller à la configuration"):
            st.session_state.current_page = "email_config"
            st.rerun()

    # Charger les données
    company_id = st.session_state.get('current_company')
    period_str = st.session_state.get('current_period', datetime.now().strftime("%m-%Y"))

    if not company_id:
        st.warning("Veuillez sélectionner une entreprise")

    # Convertir la période au format YYYY-MM
    try:
        period_date = datetime.strptime(period_str, "%m-%Y")
        period = period_date.strftime("%Y-%m")
        month_year = period_date.strftime("%B %Y")
    except:
        st.error("Format de période invalide")

    year = period_date.year
    month = period_date.month

    # Charger les données de paie
    df_period = DataManager.load_period_data(company_id, month, year)

    if df_period.height == 0:
        st.warning(f"Aucune donnée de paie trouvée pour {month_year}")

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

with tab4:
    st.info("📋 **Déclaration DSM Monaco**")

    # Load company info
    system = IntegratedPayrollSystem()
    company_info = system.company_info

    # Check employer number
    employer_number = company_info.get('employer_number_monaco', '')

    if not employer_number:
        st.warning("⚠️ Numéro d'employeur Monaco non configuré")
        st.info("Veuillez configurer le numéro d'employeur dans Configuration → Entreprise")

        if st.session_state.get('role') == "admin":
            with st.expander("➕ Configurer maintenant"):
                with st.form("quick_employer_config"):
                    new_employer_number = st.text_input(
                        "Numéro d'employeur Monaco",
                        help="Numéro d'enregistrement Caisses Sociales Monaco (5 chiffres requis)"
                    )

                    if st.form_submit_button("💾 Sauvegarder"):
                        if new_employer_number:
                            if not new_employer_number.isdigit() or len(new_employer_number) != 5:
                                st.error("Le numéro doit être exactement 5 chiffres")
                            else:
                                company_info['employer_number_monaco'] = new_employer_number
                                config_file = Path("config/company_info.json")
                                with open(config_file, 'w', encoding='utf-8') as f:
                                    json.dump(company_info, f, indent=2)
                                st.success("✅ Numéro d'employeur sauvegardé!")
                                time.sleep(1)
                                st.rerun()
    else:
        st.success(f"✅ Numéro employeur: {employer_number}")

        # Configuration
        st.markdown("---")
        st.subheader("Configuration DSM")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Numéro employeur", employer_number)

        with col2:
            st.metric("Période", st.session_state.current_period)

        with col3:
            constants = MonacoPayrollConstants(year)
            plafond_t1 = constants.PLAFOND_SS_T1
            st.metric("Plafond SS T1", f"{plafond_t1:,.2f} €")

        # Default values configuration
        st.markdown("---")
        st.subheader("Configuration employés")

        with st.expander("⚙️ Valeurs par défaut"):
            col1, col2 = st.columns(2)

            with col1:
                default_affiliation_ac = st.selectbox("Affiliation AC", ["Oui", "Non"], index=0, key="dsm_ac")
                default_affiliation_rc = st.selectbox("Affiliation RC", ["Oui", "Non"], index=0, key="dsm_rc")
                default_affiliation_car = st.selectbox("Affiliation CAR", ["Oui", "Non"], index=0, key="dsm_car")

            with col2:
                default_teletravail = st.selectbox("Télétravail", ["Non", "Oui"], index=0, key="dsm_tt")
                default_admin_salarie = st.selectbox("Admin salarié", ["Non", "Oui"], index=0, key="dsm_admin")

            if st.button("📝 Appliquer aux employés", use_container_width=True, key="apply_dsm_defaults"):
                df = df.with_columns([
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

                DataManager.save_period_data(df, st.session_state.current_company, month, year)
                st.success("✅ Valeurs appliquées!")
                st.rerun()

        # Check missing fields
        missing_fields_df = df.filter(
            pl.col('date_naissance').is_null() |
            pl.col('affiliation_ac').is_null() |
            pl.col('affiliation_rc').is_null() |
            pl.col('affiliation_car').is_null()
        )

        if missing_fields_df.height > 0:
            st.warning(f"⚠️ {missing_fields_df.height} employé(s) avec champs manquants")
            with st.expander("Voir"):
                display_cols = ['matricule', 'nom', 'prenom']
                if 'date_naissance' in missing_fields_df.columns:
                    display_cols.append('date_naissance')
                st.dataframe(missing_fields_df.select(display_cols).to_pandas(), use_container_width=True)

        # Summary
        st.markdown("---")
        st.subheader("📊 Récapitulatif")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Employés", len(df))

        with col2:
            total_brut = df.select(pl.col('salaire_brut').sum()).item()
            st.metric("Masse brute", f"{total_brut:,.0f} €")

        with col3:
            st.metric("Base CCSS", f"{total_brut:,.0f} €")

        with col4:
            st.metric("Base CAR", f"{total_brut:,.0f} €")

        st.markdown("---")

        # Generation
        col1, col2, col3 = st.columns([1, 1, 1])

        with col2:
            generate_button = st.button("📄 Générer DSM", type="primary", use_container_width=True)

        if generate_button:
            try:
                with st.spinner("Génération XML DSM..."):
                    generator = DSMXMLGenerator(employer_number, plafond_t1)
                    xml_buffer = generator.generate_dsm_xml(df, st.session_state.current_period)

                    xml_buffer.seek(0)
                    xml_content = xml_buffer.read().decode('UTF-8')
                    xml_buffer.seek(0)

                    st.success("✅ DSM générée!")

                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col2:
                        st.download_button(
                            label="📥 Télécharger DSM XML",
                            data=xml_buffer.getvalue(),
                            file_name=f"DSM_{employer_number}_{st.session_state.current_period}.xml",
                            mime="application/xml",
                            use_container_width=True
                        )

                    with st.expander("👁️ Aperçu XML"):
                        st.code(xml_content, language="xml")

            except Exception as e:
                st.error(f"❌ Erreur: {str(e)}")
                import traceback
                with st.expander("Détails"):
                    st.code(traceback.format_exc())

