"""
Email Page - Envoi des emails de validation
"""
import streamlit as st
import polars as pl
import time
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.data_mgt import DataManager
from services.payroll_system import IntegratedPayrollSystem
from services.pdf_generation import PDFGeneratorService
from services.email_archive import create_email_distribution_system

st.set_page_config(page_title="Email", page_icon="📧", layout="wide")


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


# If run as standalone page
if __name__ == "__main__" or __name__ == "pages.7_📧_Email":
    send_validation_email_page()
