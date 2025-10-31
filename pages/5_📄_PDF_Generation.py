"""
PDF Generation Page - Génération des PDFs
"""
import streamlit as st
import polars as pl
import io
import zipfile
import calendar
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.shared_utils import require_company_and_period, get_payroll_system, render_sidebar
from services.data_mgt import DataManager
from services.pdf_generation import PDFGeneratorService
from services.payslip_helpers import clean_employee_data_for_pdf

st.set_page_config(page_title="PDF Generation", page_icon="📄", layout="wide")

# Render sidebar with company/period selection
render_sidebar()

st.header("📄 Génération des PDFs")

if not require_company_and_period():
    st.stop()

system = get_payroll_system()
period_parts = st.session_state.current_period.split('-')
month = int(period_parts[0])
year = int(period_parts[1])

# Load data directly without dropping Object columns (needed for PDF generation)
df = DataManager.load_period_data(st.session_state.current_company, month, year)

if df.is_empty():
    st.warning("Aucune donnée pour cette période. Lancez d'abord l'import des données.")
    st.stop()

# Check if data has been processed (has calculated fields)
if 'salaire_brut' not in df.columns:
    st.warning("Les données n'ont pas été traitées. Lancez d'abord le traitement des paies.")
    st.stop()

# Initialize PDF service
company_info = system.company_info
pdf_service = PDFGeneratorService(company_info)

# Create unique key for current company/period
pdf_key = f"{st.session_state.current_company}_{month:02d}_{year}"

# Initialize PDF storage for this key if not exists
if 'generated_pdfs' not in st.session_state:
    st.session_state.generated_pdfs = {}

if pdf_key not in st.session_state.generated_pdfs:
    st.session_state.generated_pdfs[pdf_key] = {}

st.subheader("Options de génération PDF")
st.info(f"**{len(df)} employés** traités pour la période {st.session_state.current_period}")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📄 Bulletin individuel",
    "📚 Tous les bulletins",
    "📊 Journal de paie",
    "💰 Provision CP",
    "Charges Sociales"
])

with tab1:
    st.info("📄 Générer le bulletin de paie d'un employé spécifique")

    # Employee selection
    employees = df.select(['matricule', 'nom', 'prenom']).to_dicts()
    employee_options = [f"{emp.get('matricule', '')} - {emp.get('nom') or ''} {emp.get('prenom') or ''}" for emp in employees]

    selected_employee = st.selectbox("Sélectionner un employé", employee_options)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📄 Générer bulletin individuel", type="primary", use_container_width=True):
            if selected_employee:
                try:
                    # Extract matricule from selection
                    matricule = selected_employee.split(' - ')[0].strip()
                    employee_row = df.filter(pl.col('matricule') == matricule)

                    if employee_row.is_empty():
                        st.error(f"Employee {matricule} not found in data")
                    else:
                        employee_data = clean_employee_data_for_pdf(
                            employee_row.to_dicts()[0]
                        )

                        # Add period information for PDF generation
                        last_day = calendar.monthrange(year, month)[1]

                        employee_data['period_start'] = f"01/{month:02d}/{year}"
                        employee_data['period_end'] = f"{last_day:02d}/{month:02d}/{year}"
                        employee_data['payment_date'] = f"{last_day:02d}/{month:02d}/{year}"

                        # Generate PDF
                        with st.spinner("Génération du bulletin en cours..."):
                            pdf_buffer = pdf_service.generate_email_ready_paystub(
                                employee_data,
                                f"{month:02d}-{year}"
                            )

                        # Store in session state
                        st.session_state.generated_pdfs[pdf_key][f'bulletin_{matricule}'] = {
                            'buffer': pdf_buffer.getvalue(),
                            'filename': f"bulletin_{matricule}_{year}_{month:02d}.pdf",
                            'generated_at': datetime.now()
                        }

                        st.success("✅ Bulletin généré avec succès!")

                except Exception as e:
                    st.error(f"Erreur lors de la génération: {str(e)}")

    with col2:
        # Check if individual bulletin exists in session state
        bulletin_key = f"bulletin_{selected_employee.split(' - ')[0]}" if selected_employee else None
        if bulletin_key and bulletin_key in st.session_state.generated_pdfs[pdf_key]:
            pdf_data = st.session_state.generated_pdfs[pdf_key][bulletin_key]
            st.download_button(
                label="💾 Télécharger le bulletin",
                data=pdf_data['buffer'],
                file_name=pdf_data['filename'],
                mime="application/pdf",
                use_container_width=True
            )

with tab2:
    st.info("📚 Générer tous les bulletins de paie")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Bulletins à générer", len(df))
    with col2:
        total_size_est = len(df) * 0.2  # Estimation 200KB par bulletin
        st.metric("Taille estimée", f"{total_size_est:.1f} MB")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📚 Générer tous les bulletins", type="primary", use_container_width=True):
            try:
                with st.spinner("Génération de tous les bulletins en cours..."):
                    # Add period information to all employees
                    last_day = calendar.monthrange(year, month)[1]

                    df_copy = df.with_columns([
                        pl.lit(f"01/{month:02d}/{year}").alias('period_start'),
                        pl.lit(f"{last_day:02d}/{month:02d}/{year}").alias('period_end'),
                        pl.lit(f"{last_day:02d}/{month:02d}/{year}").alias('payment_date')
                    ])

                    # Clean each row before generating PDFs
                    cleaned_data = []
                    for row in df_copy.iter_rows(named=True):
                        cleaned_data.append(clean_employee_data_for_pdf(row))

                    # Create DataFrame with schema inference but exclude Object columns
                    df_cleaned = pl.DataFrame(cleaned_data, infer_schema_length=1)

                    # Drop any Object dtype columns that can't be serialized
                    object_cols = [col for col in df_cleaned.columns if df_cleaned[col].dtype == pl.Object]
                    if object_cols:
                        df_cleaned = df_cleaned.drop(object_cols)

                    documents = pdf_service.generate_monthly_documents(df_cleaned, f"{month:02d}-{year}")

                    if 'paystubs' in documents:
                        # Create a zip file with all paystubs
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            for paystub in documents['paystubs']:
                                mat = paystub.get('matricule', '')
                                nom = paystub.get('nom') or ''
                                prenom = paystub.get('prenom') or ''
                                filename = f"bulletin_{mat}_{nom}_{prenom}.pdf"
                                zip_file.writestr(filename, paystub['buffer'].getvalue())

                        # Store in session state
                        st.session_state.generated_pdfs[pdf_key]['all_bulletins'] = {
                            'buffer': zip_buffer.getvalue(),
                            'filename': f"bulletins_{st.session_state.current_company}_{year}_{month:02d}.zip",
                            'generated_at': datetime.now(),
                            'count': len(documents['paystubs'])
                        }

                        st.success(f"✅ {len(documents['paystubs'])} bulletins générés avec succès!")
                    else:
                        st.error("Erreur lors de la génération des bulletins")

            except Exception as e:
                st.error(f"Erreur lors de la génération: {str(e)}")

    with col2:
        # Check if all bulletins exist in session state
        if 'all_bulletins' in st.session_state.generated_pdfs[pdf_key]:
            pdf_data = st.session_state.generated_pdfs[pdf_key]['all_bulletins']
            st.download_button(
                label=f"💾 Télécharger {pdf_data.get('count', '')} bulletins (ZIP)",
                data=pdf_data['buffer'],
                file_name=pdf_data['filename'],
                mime="application/zip",
                use_container_width=True
            )

with tab3:
    st.info("📊 Générer le journal de paie")

    # Show summary stats
    col1, col2, col3 = st.columns(3)
    with col1:
        total_brut = df.select(pl.col('salaire_brut').sum()).item()
        st.metric("Masse salariale brute", f"{total_brut:,.0f} €")
    with col2:
        total_net = df.select(pl.col('salaire_net').sum()).item()
        st.metric("Total net à payer", f"{total_net:,.0f} €")
    with col3:
        total_charges_pat = df.select(pl.col('total_charges_patronales').sum()).item()
        st.metric("Charges patronales", f"{total_charges_pat:,.0f} €")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Générer journal de paie", type="primary", use_container_width=True):
            try:
                with st.spinner("Génération du journal en cours..."):
                    employees_data = df.to_dicts()
                    journal_buffer = pdf_service.journal_generator.generate_pay_journal(
                        employees_data,
                        f"{month:02d}-{year}"
                    )

                # Store in session state
                st.session_state.generated_pdfs[pdf_key]['journal'] = {
                    'buffer': journal_buffer.getvalue(),
                    'filename': f"journal_paie_{st.session_state.current_company}_{month:02d}_{year}.pdf",
                    'generated_at': datetime.now()
                }

                st.success("✅ Journal de paie généré avec succès!")

            except Exception as e:
                st.error(f"Erreur lors de la génération: {str(e)}")

    with col2:
        # Check if journal exists in session state
        if 'journal' in st.session_state.generated_pdfs[pdf_key]:
            pdf_data = st.session_state.generated_pdfs[pdf_key]['journal']
            st.download_button(
                label="💾 Télécharger le journal de paie",
                data=pdf_data['buffer'],
                file_name=pdf_data['filename'],
                mime="application/pdf",
                use_container_width=True
            )

with tab4:
    st.info("💰 Générer la provision pour congés payés")

    st.markdown("""
    **Informations sur la provision CP:**
    - Calcul basé sur les droits acquis et non pris
    - Inclut les charges sociales estimées (45% de majoration)
    - Document comptable pour l'arrêté des comptes
    """)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("💰 Générer provision CP", type="primary", use_container_width=True):
            try:
                with st.spinner("Génération de la provision en cours..."):
                    # Prepare provisions data
                    period_date = datetime(year, month, 1)
                    provisions_data = pdf_service._prepare_provisions_data(df, period_date)

                    pto_buffer = pdf_service.pto_generator.generate_pto_provision(
                        provisions_data,
                        f"{month:02d}-{year}"
                    )

                # Calculate total provision for display
                total_provision = sum(p.get('provision_amount', 0) for p in provisions_data)

                # Store in session state
                st.session_state.generated_pdfs[pdf_key]['provision_cp'] = {
                    'buffer': pto_buffer.getvalue(),
                    'filename': f"provision_cp_{st.session_state.current_company}_{year}_{month:02d}.pdf",
                    'generated_at': datetime.now(),
                    'total': total_provision
                }

                st.success(f"✅ Provision générée avec succès!")
                st.info(f"**Provision totale:** {total_provision:,.2f} €")

            except Exception as e:
                st.error(f"Erreur lors de la génération: {str(e)}")

    with col2:
        # Check if provision exists in session state
        if 'provision_cp' in st.session_state.generated_pdfs[pdf_key]:
            pdf_data = st.session_state.generated_pdfs[pdf_key]['provision_cp']
            if 'total' in pdf_data:
                st.info(f"**Provision totale:** {pdf_data['total']:,.2f} €")
            st.download_button(
                label="💾 Télécharger provision CP",
                data=pdf_data['buffer'],
                file_name=pdf_data['filename'],
                mime="application/pdf",
                use_container_width=True
            )

with tab5:
    st.info("📈 Générer l'état des charges sociales")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Employés", len(df))
    with col2:
        total_charges_sal = df.select(pl.col('total_charges_salariales').sum()).item() if 'total_charges_salariales' in df.columns else 0
        total_charges_pat = df.select(pl.col('total_charges_patronales').sum()).item() if 'total_charges_patronales' in df.columns else 0
        st.metric("Charges totales", f"{(total_charges_sal + total_charges_pat):,.2f} €")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Générer état charges sociales", type="primary", use_container_width=True):
            try:
                with st.spinner("Génération de l'état des charges sociales..."):
                    # Clean data for PDF
                    cleaned_data = []
                    for row in df.iter_rows(named=True):
                        cleaned_data.append(clean_employee_data_for_pdf(row))

                    # Generate PDF
                    pdf_buffer = pdf_service.generate_charges_sociales_pdf(
                        cleaned_data,
                        f"{month:02d}-{year}"
                    )

                    # Store in session state
                    st.session_state.generated_pdfs[pdf_key]['charges_sociales'] = {
                        'buffer': pdf_buffer.getvalue(),
                        'filename': f"charges_sociales_{st.session_state.current_company}_{year}_{month:02d}.pdf",
                        'generated_at': datetime.now()
                    }

                    st.success("✅ État des charges sociales généré avec succès!")
                    st.rerun()

            except Exception as e:
                st.error(f"Erreur lors de la génération: {str(e)}")

    with col2:
        # Check if charges sociales PDF exists in session state
        if 'charges_sociales' in st.session_state.generated_pdfs[pdf_key]:
            pdf_data = st.session_state.generated_pdfs[pdf_key]['charges_sociales']
            st.download_button(
                label="💾 Télécharger état charges sociales",
                data=pdf_data['buffer'],
                file_name=pdf_data['filename'],
                mime="application/pdf",
                use_container_width=True
            )

    st.markdown("""
    **À propos de l'état des charges sociales:**

    - Agrégation de toutes les charges par code
    - Répartition salariales / patronales
    - Décompte des employés par charge
    - Calcul des bases cotisées
    - Format réglementaire Monaco
    """)

# Add some helpful information at the bottom
st.markdown("---")

# Show status of generated PDFs
if pdf_key in st.session_state.generated_pdfs and st.session_state.generated_pdfs[pdf_key]:
    st.success(f"📁 **PDFs disponibles pour téléchargement:**")
    for doc_type, doc_data in st.session_state.generated_pdfs[pdf_key].items():
        if isinstance(doc_data, dict) and 'generated_at' in doc_data:
            st.write(f"- {doc_data['filename']} (généré à {doc_data['generated_at'].strftime('%H:%M:%S')})")

st.info("""
💡 **Conseils pour la génération PDF:**
- Les bulletins individuels sont générés au format réglementaire Monaco
- Le journal de paie contient les écritures comptables
- La provision CP est calculée selon la législation sociale monégasque
- Tous les documents sont horodatés et numérotés
- Les PDFs générés restent disponibles jusqu'au changement de période
""")
