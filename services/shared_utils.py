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


def get_last_n_months(month: int, year: int, n_months: int):
    """Get start/end year and month for last n months"""
    start_date = date(year, month, 1) - timedelta(days=30 * (n_months - 1))
    start_year, start_month = start_date.year, start_date.month
    end_year, end_month = year, month
    return start_year, start_month, end_year, end_month


@st.cache_data(ttl=300)
def load_period_data_cached(company_id: str, month: int, year: int):
    """Cached data loading for period"""
    return DataManager.load_period_data(company_id, month, year)


@st.cache_data(ttl=300)
def load_salary_trend_data(company_id: str, month: int, year: int, n_months: int = 6):
    """Load salary trend data for last n months - returns aggregated by period"""
    start_year, start_month, end_year, end_month = get_last_n_months(month, year, n_months)

    df = DataManager.get_period_range(company_id, start_year, start_month, end_year, end_month)

    if df.is_empty():
        return pl.DataFrame()

    # Aggregate by period
    trend = df.group_by(['period_year', 'period_month']).agg([
        pl.col('salaire_brut').sum().alias('total_brut'),
        pl.col('salaire_net').sum().alias('total_net'),
        pl.col('matricule').count().alias('nb_employees')
    ]).sort(['period_year', 'period_month'])

    # Add period label for display
    trend = trend.with_columns(
        pl.concat_str([
            pl.col('period_month').cast(pl.Utf8).str.zfill(2),
            pl.lit('-'),
            pl.col('period_year').cast(pl.Utf8)
        ]).alias('period')
    )

    return trend
