"""
Processing Page - Traitement des paies
"""
import streamlit as st
import polars as pl
import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.shared_utils import require_company_and_period, get_payroll_system, render_sidebar
from services.data_mgt import DataManager
from services.edge_case_agent import EdgeCaseAgent
from services.payslip_helpers import check_and_restart_time_tracking

st.set_page_config(page_title="Traitement", page_icon="⚙️", layout="wide")

# Render sidebar with company/period selection
render_sidebar()

st.markdown("## Traitement des paies")

if not require_company_and_period():
    st.stop()

# Start time tracking for this company/period
check_and_restart_time_tracking()

system = get_payroll_system()

# Clean info box
st.markdown("""
    <div style="background: #f8f9fa; border-left: 4px solid #2c3e50; padding: 1rem; border-radius: 0 8px 8px 0; margin-bottom: 2rem;">
        <div style="font-weight: 500; margin-bottom: 0.5rem;">Traitement automatique intelligent</div>
        <div style="color: #6c757d; font-size: 0.9rem;">
            • Calcul des salaires selon la législation monégasque<br>
            • Analyse intelligente des remarques et cas particuliers<br>
            • Comparaison avec le mois précédent<br>
            • Corrections automatiques (confiance ≥95%)<br>
            • Détection d'anomalies et erreurs de saisie
        </div>
    </div>
""", unsafe_allow_html=True)

# Edge case agent configuration
st.markdown("### ⚙️ Configuration de l'agent")
col1, col2 = st.columns(2)
with col1:
    enable_agent = st.checkbox("Activer l'agent de traitement intelligent", value=True,
                               help="L'agent analysera automatiquement les cas particuliers et effectuera des corrections avec haute confiance")
with col2:
    send_email = st.checkbox("Envoyer le rapport par email", value=False,
                            help="Envoyer un résumé des modifications au comptable")

if send_email:
    accountant_email = st.text_input("Email du comptable",
                                     value="comptable@example.com",
                                     help="Email pour recevoir le rapport de traitement")

if st.button("Lancer le traitement", type="primary", width='content'):
    with st.spinner("Traitement en cours..."):
        report = system.process_monthly_payroll(
            st.session_state.current_company,
            st.session_state.current_period
        )

    if report.get('success'):
        st.success("✅ Traitement terminé avec succès!")

        for step in report['steps']:
            if step['status'] == 'success':
                st.write(f"✓ {step['step']}")

        # Run edge case agent if enabled
        if enable_agent and 'processed_data' in st.session_state:
            with st.spinner("🤖 Analyse intelligente des cas particuliers..."):
                df = st.session_state.processed_data
                df = pl.DataFrame(df) if not isinstance(df, pl.DataFrame) else df

                # Initialize agent
                agent = EdgeCaseAgent(system.data_consolidator)

                # Process payroll with agent
                month, year = map(int, st.session_state.current_period.split('-'))
                modified_df, agent_report = agent.process_payroll(df, st.session_state.current_company, month, year)

                # Update processed data
                st.session_state.processed_data = modified_df

                # Save modified data
                DataManager.save_period_data(
                    modified_df,
                    st.session_state.current_company,
                    month,
                    year
                )

                # Store agent report in session
                st.session_state.edge_case_report = agent_report

                # Show agent results
                st.markdown("---")
                st.subheader("🤖 Rapport de l'Agent Intelligent")

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Modifications automatiques", agent_report.automatic_count,
                             help="Corrections effectuées avec confiance ≥95%")
                with col2:
                    st.metric("Cas signalés", agent_report.flagged_count,
                             help="Cas nécessitant une révision manuelle")
                with col3:
                    st.metric("Anomalies détectées", len(agent_report.anomalies),
                             help="Variations importantes (>15%) détectées")
                with col4:
                    st.metric("Tendances analysées", len(agent_report.trends),
                             help="Analyses historiques sur 6 mois")

                # Show automatic modifications
                if agent_report.modifications:
                    with st.expander(f"📝 Modifications automatiques ({agent_report.automatic_count})", expanded=True):
                        auto_mods = [m for m in agent_report.modifications if m.automatic]
                        if auto_mods:
                            for mod in auto_mods:
                                st.success(f"""
                                **{mod.employee_name}** ({mod.matricule})
                                {mod.field}: {mod.old_value:.2f} → {mod.new_value:.2f}
                                ✓ {mod.reason} (Confiance: {mod.confidence*100:.0f}%)
                                """)

                # Show flagged cases
                if agent_report.flagged_cases:
                    with st.expander(f"⚠️ Cas signalés pour révision ({agent_report.flagged_count})", expanded=True):
                        for case in agent_report.flagged_cases:
                            st.warning(f"""
                            **{case['employee_name']}** ({case['matricule']})
                            {case['reason']}
                            Remarque: {case.get('remark', 'N/A')}
                            """)

                # Show historical trends
                if agent_report.trends:
                    with st.expander(f"📈 Tendances Historiques ({len(agent_report.trends)} analyses)", expanded=False):
                        st.info("Analyse des 6 derniers mois pour détecter les tendances et la volatilité")

                        # Group by employee for better display
                        employee_trends = {}
                        for trend in agent_report.trends:
                            key = trend.matricule
                            if key not in employee_trends:
                                employee_trends[key] = {
                                    'name': trend.employee_name,
                                    'trends': []
                                }
                            employee_trends[key]['trends'].append(trend)

                        # Display by employee
                        for matricule, emp_data in employee_trends.items():
                            with st.expander(f"👤 {emp_data['name']} ({matricule})", expanded=False):
                                for trend in emp_data['trends']:
                                    col1, col2, col3, col4 = st.columns(4)
                                    with col1:
                                        st.markdown(f"**{trend.field}**")
                                    with col2:
                                        direction_icon = "📈" if trend.trend_direction == "increasing" else "📉" if trend.trend_direction == "decreasing" else "➡️"
                                        st.markdown(f"{direction_icon} {trend.trend_direction}")
                                    with col3:
                                        volatility_color = "🟢" if trend.volatility == "low" else "🟡" if trend.volatility == "medium" else "🔴"
                                        st.markdown(f"{volatility_color} Volatilité: {trend.volatility}")
                                    with col4:
                                        st.markdown(f"Moyenne: {trend.avg_value:.2f}")

                                    # Show mini chart
                                    st.line_chart({trend.field: trend.values})

                # Excel Export
                st.markdown("---")
                st.markdown("### 📊 Export du Rapport")
                col1, col2 = st.columns(2)

                with col1:
                    try:
                        excel_buffer = agent.export_to_excel(st.session_state.current_company, st.session_state.current_period)
                        st.download_button(
                            label="📥 Télécharger le rapport Excel",
                            data=excel_buffer,
                            file_name=f"rapport_agent_{st.session_state.current_company}_{st.session_state.current_period}_{agent_report.timestamp.strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            help="Rapport complet avec toutes les modifications, anomalies et tendances",
                            width='stretch'
                        )
                    except Exception as e:
                        st.error(f"Erreur lors de la génération du rapport Excel: {e}")

                with col2:
                    # JSON export (backup)
                    report_json = json.dumps(agent_report.to_dict(), indent=2, ensure_ascii=False)
                    st.download_button(
                        label="📄 Télécharger le rapport JSON",
                        data=report_json,
                        file_name=f"rapport_agent_{st.session_state.current_company}_{st.session_state.current_period}_{agent_report.timestamp.strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json",
                        help="Format JSON pour traitement automatique",
                        width='stretch'
                    )

                # Send email if requested
                if send_email and accountant_email:
                    try:
                        # Try to get SMTP config from session or use defaults
                        smtp_config = st.session_state.get('smtp_config', {
                            'smtp_server': 'smtp.gmail.com',
                            'smtp_port': 587,
                            'sender_email': 'paie@example.com',
                            'sender_password': 'password',
                            'sender_name': 'Service Paie Monaco'
                        })

                        # Note: Email sending will need proper SMTP configuration
                        st.info("📧 Configuration email requise pour l'envoi automatique. Consultez la page de configuration.")

                        # Generate email preview
                        email_data = agent.generate_email_summary(accountant_email)
                        with st.expander("📧 Aperçu de l'email"):
                            st.markdown(f"**À:** {email_data['to']}")
                            st.markdown(f"**Sujet:** {email_data['subject']}")
                            st.markdown("---")
                            st.markdown(email_data['html_body'], unsafe_allow_html=True)
                    except Exception as e:
                        st.warning(f"Impossible de générer l'email: {e}")


        st.markdown("---")
        st.subheader("Résultats du traitement")

        if 'processed_data' in st.session_state:
            df = st.session_state.processed_data
            df = pl.DataFrame(df) if not isinstance(df, pl.DataFrame) else df
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Fiches traitées", len(df))

            with col2:
                validated = df.filter(pl.col('statut_validation') == True).height
                st.metric("Validées automatiquement", f"{validated} ({validated/len(df)*100:.1f}%)")

            with col3:
                edge_cases = df.select(pl.col('edge_case_flag').sum()).item()
                st.metric("Cas à vérifier", edge_cases)
    else:
        st.error(f"Erreur: {report.get('error', 'Erreur inconnue')}")
