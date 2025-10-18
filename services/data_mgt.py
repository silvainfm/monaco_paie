"""
Data Management Module using DuckDB
Optimized for single-period lookups, cross-period aggregations, and historical analysis
"""

import duckdb
import polars as pl
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "payroll.duckdb"

class DataManager:
    """DuckDB-based payroll data management with in-memory connection pool"""
    
    _conn = None  # Shared connection for 10-15 concurrent users
    
    @staticmethod
    def get_connection() -> duckdb.DuckDBPyConnection:
        """Get persistent DuckDB connection (thread-safe for read operations)"""
        if DataManager._conn is None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            DataManager._conn = duckdb.connect(str(DB_PATH))
            # Optimize for read-heavy workload
            DataManager._conn.execute("PRAGMA threads=4")
            DataManager._conn.execute("PRAGMA memory_limit='2GB'")
        return DataManager._conn
    
    @staticmethod
    def init_schema():
        """Initialize database schema with indexes"""
        conn = DataManager.get_connection()
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payroll_data (
                company_id VARCHAR,
                period_year INTEGER,
                period_month INTEGER,
                matricule VARCHAR,
                nom VARCHAR,
                prenom VARCHAR,
                email VARCHAR,
                ccss_number VARCHAR,
                date_entree DATE,
                date_sortie DATE,
                anciennete VARCHAR,
                emploi VARCHAR,
                qualification VARCHAR,
                niveau VARCHAR,
                coefficient VARCHAR,
                pays_residence VARCHAR,
                base_heures DOUBLE,
                heures_payees DOUBLE,
                taux_horaire DOUBLE,
                salaire_base DOUBLE,
                heures_conges_payes DOUBLE,
                jours_cp_pris DOUBLE,
                indemnite_cp DOUBLE,
                heures_absence DOUBLE,
                type_absence VARCHAR,
                retenue_absence DOUBLE,
                prime DOUBLE,
                type_prime VARCHAR,
                heures_sup_125 DOUBLE,
                montant_hs_125 DOUBLE,
                heures_sup_150 DOUBLE,
                montant_hs_150 DOUBLE,
                heures_jours_feries DOUBLE,
                montant_jours_feries DOUBLE,
                heures_dimanche DOUBLE,
                tickets_restaurant DOUBLE,
                avantage_logement DOUBLE,
                avantage_transport DOUBLE,
                remarques VARCHAR,
                salaire_brut DOUBLE,
                total_charges_salariales DOUBLE,
                total_charges_patronales DOUBLE,
                salaire_net DOUBLE,
                cout_total_employeur DOUBLE,
                prelevement_source DOUBLE,
                statut_validation VARCHAR,
                edge_case_flag BOOLEAN,
                edge_case_reason VARCHAR,
                cumul_brut DOUBLE,
                cumul_base_ss DOUBLE,
                cumul_net_percu DOUBLE,
                cumul_charges_sal DOUBLE,
                cumul_charges_pat DOUBLE,
                cp_acquis_n1 DOUBLE,
                cp_pris_n1 DOUBLE,
                cp_restants_n1 DOUBLE,
                cp_acquis_n DOUBLE,
                cp_pris_n DOUBLE,
                cp_restants_n DOUBLE,
                details_charges JSON,
                tickets_restaurant_details JSON,
                last_modified TIMESTAMP,
                PRIMARY KEY (company_id, period_year, period_month, matricule)
            )
        """)
        
        # Create indexes for common queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_period 
            ON payroll_data(company_id, period_year, period_month)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_matricule 
            ON payroll_data(company_id, matricule)
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id VARCHAR PRIMARY KEY,
                name VARCHAR,
                siret VARCHAR,
                address VARCHAR,
                phone VARCHAR,
                email VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Ensure sample companies exist
        count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        if count == 0:
            conn.execute("""
                INSERT INTO companies (id, name, siret) VALUES
                ('CARAX_MONACO', 'CARAX MONACO', '763000000'),
                ('RG_CAPITAL_SERVICES', 'RG CAPITAL SERVICES', '169000000')
            """)
        
        logger.info("Database schema initialized")
    
    @staticmethod
    def save_period_data(df: pl.DataFrame, company_id: str, month: int, year: int):
        """Save period data (upsert operation)"""
        conn = DataManager.get_connection()
        
        # Add metadata if not present
        if 'company_id' not in df.columns:
            df = df.with_columns([
                pl.lit(company_id).alias('company_id'),
                pl.lit(year).alias('period_year'),
                pl.lit(month).alias('period_month'),
                pl.lit(datetime.now()).alias('last_modified')
            ])
        
        # Delete existing period data
        conn.execute("""
            DELETE FROM payroll_data 
            WHERE company_id = ? AND period_year = ? AND period_month = ?
        """, [company_id, year, month])
        
        # Insert new data
        conn.execute("INSERT INTO payroll_data SELECT * FROM df")
        
        logger.info(f"Saved {df.height} records for {company_id} {year}-{month:02d}")
    
    @staticmethod
    def load_period_data(company_id: str, month: int, year: int) -> pl.DataFrame:
        """Load period data (optimized single-period lookup)"""
        conn = DataManager.get_connection()
        
        result = conn.execute("""
            SELECT * FROM payroll_data
            WHERE company_id = ? AND period_year = ? AND period_month = ?
            ORDER BY matricule
        """, [company_id, year, month]).pl()
        
        if result.height == 0:
            return DataManager.create_empty_df()
        
        return result
    
    @staticmethod
    def get_employee_history(company_id: str, matricule: str, 
                            start_year: int, start_month: int,
                            end_year: int, end_month: int) -> pl.DataFrame:
        """Get employee history across periods (historical analysis)"""
        conn = DataManager.get_connection()
        
        result = conn.execute("""
            SELECT * FROM payroll_data
            WHERE company_id = ?
                AND matricule = ?
                AND (period_year > ? OR (period_year = ? AND period_month >= ?))
                AND (period_year < ? OR (period_year = ? AND period_month <= ?))
            ORDER BY period_year, period_month
        """, [company_id, matricule, start_year, start_year, start_month, 
              end_year, end_year, end_month]).pl()
        
        return result
    
    @staticmethod
    def get_period_range(company_id: str, 
                        start_year: int, start_month: int,
                        end_year: int, end_month: int) -> pl.DataFrame:
        """Get all payroll data for period range (cross-period aggregation)"""
        conn = DataManager.get_connection()
        
        result = conn.execute("""
            SELECT * FROM payroll_data
            WHERE company_id = ?
                AND (period_year > ? OR (period_year = ? AND period_month >= ?))
                AND (period_year < ? OR (period_year = ? AND period_month <= ?))
            ORDER BY period_year, period_month, matricule
        """, [company_id, start_year, start_year, start_month, 
              end_year, end_year, end_month]).pl()
        
        return result
    
    @staticmethod
    def get_company_summary(company_id: str, year: int, month: int) -> Dict:
        """Get aggregated summary for a period"""
        conn = DataManager.get_connection()
        
        result = conn.execute("""
            SELECT 
                COUNT(*) as employee_count,
                SUM(salaire_brut) as total_brut,
                SUM(salaire_net) as total_net,
                SUM(total_charges_salariales) as total_charges_sal,
                SUM(total_charges_patronales) as total_charges_pat,
                SUM(cout_total_employeur) as total_cost,
                SUM(CASE WHEN edge_case_flag THEN 1 ELSE 0 END) as edge_cases,
                SUM(CASE WHEN statut_validation = 'Validé' THEN 1 ELSE 0 END) as validated
            FROM payroll_data
            WHERE company_id = ? AND period_year = ? AND period_month = ?
        """, [company_id, year, month]).fetchone()
        
        if result[0] == 0:
            return {}
        
        return {
            'employee_count': result[0],
            'total_brut': result[1],
            'total_net': result[2],
            'total_charges_sal': result[3],
            'total_charges_pat': result[4],
            'total_cost': result[5],
            'edge_cases': result[6],
            'validated': result[7]
        }
    
    @staticmethod
    def get_available_periods(company_id: str) -> List[Dict]:
        """Get list of available periods for a company"""
        conn = DataManager.get_connection()
        
        result = conn.execute("""
            SELECT DISTINCT period_year, period_month,
                   COUNT(*) as employee_count,
                   MAX(last_modified) as last_modified
            FROM payroll_data
            WHERE company_id = ?
            GROUP BY period_year, period_month
            ORDER BY period_year DESC, period_month DESC
        """, [company_id]).pl()
        
        return result.to_dicts()
    
    @staticmethod
    def get_companies_list() -> List[Dict]:
        """Get list of companies"""
        conn = DataManager.get_connection()
        result = conn.execute("SELECT * FROM companies ORDER BY name").pl()
        return result.to_dicts()
    
    @staticmethod
    def create_empty_df() -> pl.DataFrame:
        """Create empty DataFrame with full schema"""
        return pl.DataFrame({
            'matricule': pl.Series([], dtype=pl.Utf8),
            'nom': pl.Series([], dtype=pl.Utf8),
            'prenom': pl.Series([], dtype=pl.Utf8),
            'email': pl.Series([], dtype=pl.Utf8),
            'ccss_number': pl.Series([], dtype=pl.Utf8),
            'date_entree': pl.Series([], dtype=pl.Date),
            'date_sortie': pl.Series([], dtype=pl.Date),
            'anciennete': pl.Series([], dtype=pl.Utf8),
            'emploi': pl.Series([], dtype=pl.Utf8),
            'qualification': pl.Series([], dtype=pl.Utf8),
            'niveau': pl.Series([], dtype=pl.Utf8),
            'coefficient': pl.Series([], dtype=pl.Utf8),
            'pays_residence': pl.Series([], dtype=pl.Utf8),
            'base_heures': pl.Series([], dtype=pl.Float64),
            'heures_payees': pl.Series([], dtype=pl.Float64),
            'taux_horaire': pl.Series([], dtype=pl.Float64),
            'salaire_base': pl.Series([], dtype=pl.Float64),
            'heures_conges_payes': pl.Series([], dtype=pl.Float64),
            'jours_cp_pris': pl.Series([], dtype=pl.Float64),
            'indemnite_cp': pl.Series([], dtype=pl.Float64),
            'heures_absence': pl.Series([], dtype=pl.Float64),
            'type_absence': pl.Series([], dtype=pl.Utf8),
            'retenue_absence': pl.Series([], dtype=pl.Float64),
            'prime': pl.Series([], dtype=pl.Float64),
            'type_prime': pl.Series([], dtype=pl.Utf8),
            'heures_sup_125': pl.Series([], dtype=pl.Float64),
            'montant_hs_125': pl.Series([], dtype=pl.Float64),
            'heures_sup_150': pl.Series([], dtype=pl.Float64),
            'montant_hs_150': pl.Series([], dtype=pl.Float64),
            'heures_jours_feries': pl.Series([], dtype=pl.Float64),
            'montant_jours_feries': pl.Series([], dtype=pl.Float64),
            'heures_dimanche': pl.Series([], dtype=pl.Float64),
            'tickets_restaurant': pl.Series([], dtype=pl.Float64),
            'avantage_logement': pl.Series([], dtype=pl.Float64),
            'avantage_transport': pl.Series([], dtype=pl.Float64),
            'remarques': pl.Series([], dtype=pl.Utf8),
            'salaire_brut': pl.Series([], dtype=pl.Float64),
            'total_charges_salariales': pl.Series([], dtype=pl.Float64),
            'total_charges_patronales': pl.Series([], dtype=pl.Float64),
            'salaire_net': pl.Series([], dtype=pl.Float64),
            'cout_total_employeur': pl.Series([], dtype=pl.Float64),
            'prelevement_source': pl.Series([], dtype=pl.Float64),
            'statut_validation': pl.Series([], dtype=pl.Utf8),
            'edge_case_flag': pl.Series([], dtype=pl.Boolean),
            'edge_case_reason': pl.Series([], dtype=pl.Utf8),
            'cumul_brut': pl.Series([], dtype=pl.Float64),
            'cumul_base_ss': pl.Series([], dtype=pl.Float64),
            'cumul_net_percu': pl.Series([], dtype=pl.Float64),
            'cumul_charges_sal': pl.Series([], dtype=pl.Float64),
            'cumul_charges_pat': pl.Series([], dtype=pl.Float64),
            'cp_acquis_n1': pl.Series([], dtype=pl.Float64),
            'cp_pris_n1': pl.Series([], dtype=pl.Float64),
            'cp_restants_n1': pl.Series([], dtype=pl.Float64),
            'cp_acquis_n': pl.Series([], dtype=pl.Float64),
            'cp_pris_n': pl.Series([], dtype=pl.Float64),
            'cp_restants_n': pl.Series([], dtype=pl.Float64)
        })

class DataAuditLogger:
    """Audit logger for data operations"""
    
    @staticmethod
    def init_audit_table():
        """Initialize audit log table"""
        conn = DataManager.get_connection()
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user VARCHAR,
                action VARCHAR,
                company_id VARCHAR,
                period_year INTEGER,
                period_month INTEGER,
                details JSON,
                ip_address VARCHAR,
                record_count INTEGER
            )
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
            ON audit_log(timestamp DESC)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_company 
            ON audit_log(company_id, period_year, period_month)
        """)
    
    @staticmethod
    def log(user: str, action: str, company_id: str, year: int, month: int,
            details: Optional[Dict] = None, record_count: Optional[int] = None):
        """Log data operation"""
        conn = DataManager.get_connection()
        
        import json
        details_json = json.dumps(details) if details else None
        
        conn.execute("""
            INSERT INTO audit_log 
            (user, action, company_id, period_year, period_month, details, record_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [user, action, company_id, year, month, details_json, record_count])
    
    @staticmethod
    def get_recent_logs(limit: int = 100) -> pl.DataFrame:
        """Get recent audit logs"""
        conn = DataManager.get_connection()
        result = conn.execute("""
            SELECT * FROM audit_log
            ORDER BY timestamp DESC
            LIMIT ?
        """, [limit]).pl()
        return result
    
    @staticmethod
    def get_period_logs(company_id: str, year: int, month: int) -> pl.DataFrame:
        """Get logs for specific period"""
        conn = DataManager.get_connection()
        result = conn.execute("""
            SELECT * FROM audit_log
            WHERE company_id = ? AND period_year = ? AND period_month = ?
            ORDER BY timestamp DESC
        """, [company_id, year, month]).pl()
        return result
    
    @staticmethod
    def get_user_activity(user: str, days: int = 30) -> pl.DataFrame:
        """Get user activity for last N days"""
        conn = DataManager.get_connection()
        result = conn.execute("""
            SELECT * FROM audit_log
            WHERE user = ? 
                AND timestamp >= CURRENT_TIMESTAMP - INTERVAL ? DAY
            ORDER BY timestamp DESC
        """, [user, days]).pl()
        return result

# Backward compatibility alias
DataConsolidation = DataManager
