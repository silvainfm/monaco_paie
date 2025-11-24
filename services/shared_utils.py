"""
Shared utilities and imports for all pages
"""
import streamlit as st
import polars as pl
from datetime import datetime, date, timedelta
import calendar
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import services
from services.data_mgt import DataManager, DataConsolidation
from services.payroll_system import IntegratedPayrollSystem
from services.payslip_helpers import stop_time_tracking


def get_payroll_system():
    """Get or initialize payroll system from session state"""
    if 'payroll_system' not in st.session_state:
        st.session_state.payroll_system = IntegratedPayrollSystem()
    return st.session_state.payroll_system


def require_company_and_period():
    """Check if company and period are selected, show warning if not"""
    if not st.session_state.get('current_company') or not st.session_state.get('current_period'):
        st.warning("Sélectionnez une entreprise et une période")
        return False
    return True


@st.cache_data(ttl=600)
def load_companies_cached():
    """Load companies from DB (cached 10min)"""
    try:
        return DataManager.get_companies_list()
    except Exception as e:
        if "WAL" in str(e) or "Catalog Error" in str(e):
            from pathlib import Path
            wal_path = Path("data/payroll.duckdb.wal")
            if wal_path.exists():
                wal_path.unlink()
            return DataManager.get_companies_list()
        else:
            raise


def render_sidebar():
    """Render the sidebar with company/period selection - shared across all pages"""
    with st.sidebar:
        st.markdown("**Entreprise**")
        companies = load_companies_cached()
        company_names = [c['name'] for c in companies]

        # Find current selection index
        current_company_name = None
        if st.session_state.current_company:
            company = next((c for c in companies if c['id'] == st.session_state.current_company), None)
            current_company_name = company['name'] if company else None

        selected_index = company_names.index(current_company_name) if current_company_name in company_names else 0

        # Initialize company in session state if not present
        if 'current_company' not in st.session_state:
            st.session_state.current_company = companies[0]['id'] if companies else None

        selected_company = st.selectbox(
            "company_select",
            company_names,
            index=selected_index,
            label_visibility="collapsed",
            key="sidebar_company_selector"
        )

        if selected_company:
            company = next((c for c in companies if c['name'] == selected_company), None)
            st.session_state.current_company = company['id'] if company else None

        st.markdown("**Période**")
        # Generate last 12 months
        periods = []
        now = datetime.now()
        for i in range(12):
            month = now.month - i
            year = now.year
            if month <= 0:
                month += 12
                year -= 1
            periods.append(f"{month:02d}-{year}")

        current_period_idx = 0
        if st.session_state.current_period and st.session_state.current_period in periods:
            current_period_idx = periods.index(st.session_state.current_period)

        # Initialize period in session state if not present
        if 'current_period' not in st.session_state:
            st.session_state.current_period = periods[0] if periods else None

        st.session_state.current_period = st.selectbox(
            "period_select",
            options=periods,
            index=current_period_idx,
            label_visibility="collapsed",
            key="sidebar_period_selector"
        )

        st.markdown("""
            <div style="padding: 1rem 0; border-bottom: 1px solid #e8e8e8; margin-bottom: 1.5rem;">
                <h3 style="margin: 0; color: #2c3e50;">Paie Monégasque</h3>
                <div style="margin-top: 0.5rem; color: #6c757d; font-size: 0.9rem;">
                    <div>👤 {}</div>
                    <div>🔐 {}</div>
                </div>
            </div>
        """.format(st.session_state.user, st.session_state.role), unsafe_allow_html=True)

        if st.button("Déconnexion", width='stretch'):
            # Stop time tracking before clearing session
            stop_time_tracking()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def get_last_n_months(month: int, year: int, n_months: int):
    """Get start/end year and month for last n months"""
    start_date = date(year, month, 1) - timedelta(days=30 * (n_months - 1))
    start_year, start_month = start_date.year, start_date.month
    end_year, end_month = year, month
    return start_year, start_month, end_year, end_month


@st.cache_data(ttl=300)
def load_period_data_cached(company_id: str, month: int, year: int):
    """Cached data loading for period - drops Object columns for Streamlit compatibility"""
    df = DataManager.load_period_data(company_id, month, year)

    # Drop Object dtype columns to avoid serialization errors in Streamlit
    if not df.is_empty():
        object_cols = [col for col in df.columns if df[col].dtype == pl.Object]
        if object_cols:
            df = df.drop(object_cols)

    return df


@st.cache_data(ttl=300)
def load_salary_trend_data(company_id: str, month: int, year: int, n_months: int = 6):
    """
    Load salary trend data for last n months (OPTIMIZED: uses DuckDB aggregations)
    Returns aggregated by period without loading all raw data
    """
    # Use optimized DuckDB aggregation method (memory efficient)
    trend = DataManager.get_monthly_aggregations(company_id, year - 1, n_months)

    if trend.is_empty():
        return pl.DataFrame()

    # Rename columns to match expected format
    trend = trend.rename({
        'total_brut': 'total_brut',
        'total_net': 'total_net',
        'employee_count': 'nb_employees'
    })

    # Add period label for display
    trend = trend.with_columns(
        pl.concat_str([
            pl.col('period_month').cast(pl.Utf8).str.zfill(2),
            pl.lit('-'),
            pl.col('period_year').cast(pl.Utf8)
        ]).alias('period')
    )

    return trend
