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
from threading import Lock
from functools import lru_cache

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "payroll.duckdb"

# Thread-safe connection pool
_connection_pool = []
_pool_lock = Lock()
_MAX_POOL_SIZE = 4

class DataManager:
    """DuckDB-based payroll data management with connection pooling"""

    @staticmethod
    def get_connection() -> duckdb.DuckDBPyConnection:
        """
        Get a DuckDB connection from pool or create new

        Uses connection pooling for better performance while avoiding
        lock conflicts in Streamlit's hot-reload environment.
        """
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        with _pool_lock:
            if _connection_pool:
                conn = _connection_pool.pop()
                try:
                    # Test if connection is still valid
                    conn.execute("SELECT 1")
                    return conn
                except:
                    pass  # Connection invalid, create new

        # Create new connection
        conn = duckdb.connect(str(DB_PATH))
        # Optimize for read-heavy workload
        conn.execute("PRAGMA threads=4")
        conn.execute("PRAGMA memory_limit='2GB'")
        conn.execute("PRAGMA enable_object_cache=true")
        return conn

    @staticmethod
    def close_connection(conn: duckdb.DuckDBPyConnection):
        """Return connection to pool or close if pool full"""
        if not conn:
            return

        try:
            with _pool_lock:
                if len(_connection_pool) < _MAX_POOL_SIZE:
                    _connection_pool.append(conn)
                else:
                    conn.close()
        except Exception as e:
            logger.warning(f"Error returning connection to pool: {e}")
            try:
                conn.close()
            except:
                pass
    
    @staticmethod
    def init_schema():
        """Initialize database schema with indexes"""
        conn = DataManager.get_connection()

        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS payroll_data (
                company_id VARCHAR,
                period_year INTEGER,
                period_month INTEGER,
                matricule VARCHAR,
                nom VARCHAR,
                prenom VARCHAR,
                sexe VARCHAR,
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
                prime_non_cotisable DOUBLE,
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
                date_naissance DATE,
                affiliation_ac VARCHAR,
                affiliation_rc VARCHAR,
                affiliation_car VARCHAR,
                teletravail VARCHAR,
                pays_teletravail VARCHAR,
                administrateur_salarie VARCHAR,
                cp_date_debut DATE,
                cp_date_fin DATE,
                maladie_date_debut DATE,
                maladie_date_fin DATE,
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
        finally:
            DataManager.close_connection(conn)
    
    @staticmethod
    def save_period_data(df: pl.DataFrame, company_id: str, month: int, year: int):
        """Save period data (upsert operation) - optimized for bulk insert"""
        conn = DataManager.get_connection()

        try:
            # Add metadata if not present
            if 'company_id' not in df.columns:
                df = df.with_columns([
                    pl.lit(company_id).alias('company_id'),
                    pl.lit(year).alias('period_year'),
                    pl.lit(month).alias('period_month'),
                    pl.lit(datetime.now()).alias('last_modified')
                ])

            # Convert struct columns to JSON using cast (faster than map_elements)
            struct_columns = ['details_charges', 'tickets_restaurant_details']

            for col in struct_columns:
                if col in df.columns:
                    # Check if column is struct/object type
                    if df[col].dtype in (pl.Struct, pl.Object) or isinstance(df[col].dtype, pl.Struct):
                        # Use Polars native JSON serialization
                        df = df.with_columns(
                            pl.col(col).cast(pl.Utf8, strict=False).alias(col)
                        )

            # Delete existing period data
            conn.execute("""
                DELETE FROM payroll_data
                WHERE company_id = ? AND period_year = ? AND period_month = ?
            """, [company_id, year, month])

            # Use INSERT with SELECT for better performance
            conn.execute("INSERT INTO payroll_data SELECT * FROM df")

            logger.info(f"Saved {df.height} records for {company_id} {year}-{month:02d}")
        finally:
            DataManager.close_connection(conn)
    
    @staticmethod
    def load_period_data(company_id: str, month: int, year: int) -> pl.DataFrame:
        """Load period data (optimized query)"""
        import json

        conn = DataManager.get_connection()

        try:
            try:
                result = conn.execute("""
                    SELECT * FROM payroll_data
                    WHERE company_id = ? AND period_year = ? AND period_month = ?
                    ORDER BY matricule
                """, [company_id, year, month]).pl()
            except Exception as e:
                logger.warning(f"Error loading period data: {e}")
                return DataManager.create_empty_df()

            if result.height == 0:
                return DataManager.create_empty_df()

            # Parse JSON columns more efficiently using str.json_decode when available
            struct_columns = ['details_charges', 'tickets_restaurant_details']

            for col in struct_columns:
                if col in result.columns and result[col].dtype == pl.Utf8:
                    try:
                        # Use str.json_decode (faster) if available, fallback to map_elements
                        result = result.with_columns(
                            pl.col(col).str.json_decode().alias(col)
                        )
                    except:
                        # Fallback for older Polars versions
                        try:
                            result = result.with_columns(
                                pl.col(col).map_elements(
                                    lambda x: json.loads(x) if x and x != '' else None,
                                    return_dtype=pl.Object
                                ).alias(col)
                            )
                        except Exception as e:
                            logger.warning(f"Error parsing JSON column {col}: {e}")

            return result
        finally:
            DataManager.close_connection(conn)
    
    @staticmethod
    def get_employee_history(company_id: str, matricule: str,
                            start_year: int, start_month: int,
                            end_year: int, end_month: int) -> pl.DataFrame:
        """Get employee history across periods (historical analysis)"""
        conn = DataManager.get_connection()

        try:
            try:
                result = conn.execute("""
                    SELECT * FROM payroll_data
                    WHERE company_id = ?
                        AND matricule = ?
                        AND (period_year > ? OR (period_year = ? AND period_month >= ?))
                        AND (period_year < ? OR (period_year = ? AND period_month <= ?))
                    ORDER BY period_year, period_month
                """, [company_id, matricule, start_year, start_year, start_month,
                      end_year, end_year, end_month]).pl()
            except Exception as e:
                logger.warning(f"Error loading employee history: {e}")
                return DataManager.create_empty_df()

            return result
        finally:
            DataManager.close_connection(conn)
    
    @staticmethod
    def get_period_range(company_id: str,
                        start_year: int, start_month: int,
                        end_year: int, end_month: int) -> pl.DataFrame:
        """Get all payroll data for period range (cross-period aggregation)"""
        conn = DataManager.get_connection()

        try:
            try:
                result = conn.execute("""
                    SELECT * FROM payroll_data
                    WHERE company_id = ?
                        AND (period_year > ? OR (period_year = ? AND period_month >= ?))
                        AND (period_year < ? OR (period_year = ? AND period_month <= ?))
                    ORDER BY period_year, period_month, matricule
                """, [company_id, start_year, start_year, start_month,
                      end_year, end_year, end_month]).pl()
            except Exception as e:
                logger.warning(f"Error loading period range: {e}")
                return DataManager.create_empty_df()

            return result
        finally:
            DataManager.close_connection(conn)
    
    @staticmethod
    def get_company_summary(company_id: str, year: int, month: int) -> Dict:
        """Get aggregated summary for a period"""
        conn = DataManager.get_connection()

        try:
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
        finally:
            DataManager.close_connection(conn)
    
    @staticmethod
    def get_available_periods(company_id: str) -> List[Dict]:
        """Get list of available periods for a company"""
        conn = DataManager.get_connection()

        try:
            try:
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
            except Exception as e:
                logger.warning(f"Error loading available periods: {e}")
                return []
        finally:
            DataManager.close_connection(conn)

    @staticmethod
    @lru_cache(maxsize=1)
    def get_companies_list() -> tuple:
        """Get list of companies (cached)"""
        conn = DataManager.get_connection()

        try:
            try:
                result = conn.execute("SELECT * FROM companies ORDER BY name").pl()
                # Return as tuple for hashability
                return tuple(result.to_dicts())
            except Exception as e:
                logger.warning(f"Error loading companies list: {e}")
                return ()
        finally:
            DataManager.close_connection(conn)
    
    @staticmethod
    def get_company_creation_date(company_id: str) -> Optional[datetime]:
        """Get the creation date of a company"""
        conn = DataManager.get_connection()

        try:
            result = conn.execute("""
                SELECT created_at FROM companies
                WHERE id = ?
            """, [company_id]).fetchone()

            if result and result[0]:
                return result[0]

            return None
        finally:
            DataManager.close_connection(conn)

    @staticmethod
    def get_available_period_strings(company_id: str) -> List[str]:
        """
        Get list of all available periods for a company as strings

        Returns:
            List of periods in format "MM-YYYY", sorted newest first
        """
        conn = DataManager.get_connection()

        try:
            result = conn.execute("""
                SELECT DISTINCT
                    LPAD(CAST(period_month AS VARCHAR), 2, '0') || '-' || CAST(period_year AS VARCHAR) as period
                FROM payroll_data
                WHERE company_id = ?
                ORDER BY period_year DESC, period_month DESC
            """, [company_id]).fetchall()

            return [row[0] for row in result]
        finally:
            DataManager.close_connection(conn)

    @staticmethod
    def get_company_age_months(company_id: str) -> Optional[float]:
        """
        Get the age of a company in months
        
        Returns:
            Number of months since company creation, or None if not found
        """
        creation_date = DataManager.get_company_creation_date(company_id)
        
        if not creation_date:
            return None
        
        now = datetime.now()
        months_diff = (now.year - creation_date.year) * 12 + (now.month - creation_date.month)
        
        # Add fractional month based on days
        days_in_current_month = 30  # Approximation
        days_diff = now.day - creation_date.day
        months_diff += days_diff / days_in_current_month
        
        return max(0, months_diff)
    
    @staticmethod
    def create_empty_df() -> pl.DataFrame:
        """Create empty DataFrame with schema - optimized using schema dict"""
        schema = {
            col: pl.Utf8 for col in ['matricule', 'nom', 'prenom', 'email', 'ccss_number',
                                      'anciennete', 'emploi', 'qualification', 'niveau',
                                      'coefficient', 'pays_residence', 'type_absence',
                                      'type_prime', 'remarques', 'statut_validation', 'edge_case_reason']
        }
        schema.update({
            col: pl.Float64 for col in ['base_heures', 'heures_payees', 'taux_horaire', 'salaire_base',
                                         'heures_conges_payes', 'jours_cp_pris', 'indemnite_cp',
                                         'heures_absence', 'retenue_absence', 'prime', 'prime_non_cotisable', 'heures_sup_125',
                                         'montant_hs_125', 'heures_sup_150', 'montant_hs_150',
                                         'heures_jours_feries', 'montant_jours_feries', 'heures_dimanche',
                                         'tickets_restaurant', 'avantage_logement', 'avantage_transport',
                                         'salaire_brut', 'total_charges_salariales', 'total_charges_patronales',
                                         'salaire_net', 'cout_total_employeur', 'prelevement_source',
                                         'cumul_brut', 'cumul_base_ss', 'cumul_net_percu', 'cumul_charges_sal',
                                         'cumul_charges_pat', 'cp_acquis_n1', 'cp_pris_n1', 'cp_restants_n1',
                                         'cp_acquis_n', 'cp_pris_n', 'cp_restants_n']
        })
        schema.update({
            'date_entree': pl.Date,
            'date_sortie': pl.Date,
            'edge_case_flag': pl.Boolean
        })
        return pl.DataFrame(schema=schema)

class DataAuditLogger:
    """Audit logger for data operations"""
    
    @staticmethod
    def init_audit_table():
        """Initialize audit log table"""
        conn = DataManager.get_connection()

        try:
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
        finally:
            DataManager.close_connection(conn)
    
    @staticmethod
    def log(user: str, action: str, company_id: str, year: int, month: int,
            details: Optional[Dict] = None, record_count: Optional[int] = None):
        """Log data operation"""
        conn = DataManager.get_connection()

        try:
            import json
            details_json = json.dumps(details) if details else None

            conn.execute("""
                INSERT INTO audit_log
                (user, action, company_id, period_year, period_month, details, record_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [user, action, company_id, year, month, details_json, record_count])
        finally:
            DataManager.close_connection(conn)
    
    @staticmethod
    def get_recent_logs(limit: int = 100) -> pl.DataFrame:
        """Get recent audit logs"""
        conn = DataManager.get_connection()

        try:
            try:
                result = conn.execute("""
                    SELECT * FROM audit_log
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, [limit]).pl()
                return result
            except Exception as e:
                logger.warning(f"Error loading recent logs: {e}")
                return pl.DataFrame()
        finally:
            DataManager.close_connection(conn)

    @staticmethod
    def get_period_logs(company_id: str, year: int, month: int) -> pl.DataFrame:
        """Get logs for specific period"""
        conn = DataManager.get_connection()

        try:
            try:
                result = conn.execute("""
                    SELECT * FROM audit_log
                    WHERE company_id = ? AND period_year = ? AND period_month = ?
                    ORDER BY timestamp DESC
                """, [company_id, year, month]).pl()
                return result
            except Exception as e:
                logger.warning(f"Error loading period logs: {e}")
                return pl.DataFrame()
        finally:
            DataManager.close_connection(conn)

    @staticmethod
    def get_user_activity(user: str, days: int = 30) -> pl.DataFrame:
        """Get user activity for last N days"""
        conn = DataManager.get_connection()

        try:
            try:
                result = conn.execute("""
                    SELECT * FROM audit_log
                    WHERE user = ?
                        AND timestamp >= CURRENT_TIMESTAMP - INTERVAL ? DAY
                    ORDER BY timestamp DESC
                """, [user, days]).pl()
                return result
            except Exception as e:
                logger.warning(f"Error loading user activity: {e}")
                return pl.DataFrame()
        finally:
            DataManager.close_connection(conn)

# Backward compatibility alias
DataConsolidation = DataManager
