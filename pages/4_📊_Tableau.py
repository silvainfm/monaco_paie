"""
Dashboard Page - Tableau de bord
"""
import streamlit as st
import polars as pl
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.data_mgt import DataManager
from services.shared_utils import (
    require_company_and_period,
    load_period_data_cached,
    load_salary_trend_data,
    render_sidebar
)

st.set_page_config(page_title="Tableau", page_icon="📊", layout="wide")

# Render sidebar with company/period selection
render_sidebar()

st.markdown("## Tableau de bord")

if not require_company_and_period():
    st.stop()

month, year = map(int, st.session_state.current_period.split('-'))

summary = DataManager.get_company_summary(st.session_state.current_company, year, month)

if not summary or summary.get('employee_count', 0) == 0:
    st.info("Aucune donnée pour cette période. Commencez par importer les données.")
    st.stop()

# Premium metrics cards (using aggregated summary - memory efficient)
col1, col2, col3, col4 = st.columns(4)

metrics_style = """
    <div style="background: white; padding: 1.5rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 1rem;">
        <div style="color: #6c757d; font-size: 0.85rem; font-weight: 500; margin-bottom: 0.5rem;">{}</div>
        <div style="color: #2c3e50; font-size: 1.5rem; font-weight: 600;">{}</div>
    </div>
"""

with col1:
    st.markdown(metrics_style.format("SALARIÉS", summary['employee_count']), unsafe_allow_html=True)

with col2:
    total_brut = summary.get('total_brut', 0)
    st.markdown(metrics_style.format("MASSE SALARIALE", f"{total_brut:,.0f} €"), unsafe_allow_html=True)

with col3:
    edge_cases = summary.get('edge_cases', 0)
    st.markdown(metrics_style.format("CAS À VÉRIFIER", edge_cases), unsafe_allow_html=True)

with col4:
    validated = summary.get('validated', 0)
    total = summary['employee_count']
    st.markdown(metrics_style.format("VALIDÉES", f"{validated}/{total}"), unsafe_allow_html=True)

st.markdown("---")

# Salary trend over last 6 months
st.subheader("Évolution des salaires (6 derniers mois)")
trend_data = load_salary_trend_data(st.session_state.current_company, month, year, 6)

if not trend_data.is_empty() and trend_data.height > 1:
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Salaire Brut Total**")
        brut_chart = trend_data.select([
            pl.col('period').cast(pl.Utf8),
            pl.col('total_brut').cast(pl.Float64)
        ])
        st.line_chart(brut_chart, x='period', y='total_brut')

    with col2:
        st.markdown("**Salaire Net Total**")
        net_chart = trend_data.select([
            pl.col('period').cast(pl.Utf8),
            pl.col('total_net').cast(pl.Float64)
        ])
        st.line_chart(net_chart, x='period', y='total_net')

    # Show month-to-month change
    if trend_data.height >= 2:
        latest = trend_data.row(-1, named=True)
        previous = trend_data.row(-2, named=True)

        brut_change = ((latest['total_brut'] - previous['total_brut']) / previous['total_brut'] * 100) if previous['total_brut'] > 0 else 0
        net_change = ((latest['total_net'] - previous['total_net']) / previous['total_net'] * 100) if previous['total_net'] > 0 else 0

        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "Variation brut (mois-à-mois)",
                f"{latest['total_brut']:,.0f} €",
                f"{brut_change:+.1f}%"
            )
        with col2:
            st.metric(
                "Variation net (mois-à-mois)",
                f"{latest['total_net']:,.0f} €",
                f"{net_change:+.1f}%"
            )
else:
    st.info("Pas assez de données historiques pour afficher la tendance (minimum 2 mois)")

st.markdown("---")

st.markdown("---")
st.subheader("Employés avec cas particuliers")

edge_count = summary.get('edge_cases', 0)

if edge_count > 0:
# Load only employees with edge cases using DuckDB filter
    conn = DataManager.get_connection()
    try:
        edge_cases_df = conn.execute("""
            SELECT matricule, nom, prenom, salaire_brut, edge_case_reason
            FROM payroll_data
            WHERE company_id = ? AND period_year = ? AND period_month = ?
            AND edge_case_flag = true
            ORDER BY matricule
            """, [st.session_state.current_company, year, month]).pl()
        
        if not edge_cases_df.is_empty():
            st.dataframe(edge_cases_df, width='stretch')
        else:
            st.success("Aucun cas particulier détecté")
    finally:
        DataManager.close_connection(conn)
else:
    st.success("Aucun cas particulier détecté")
