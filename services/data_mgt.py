import pyarrow
import pyarrow.parquet as pq
HAS_PYARROW = True
import pandas as pd
import polars as pl

from pathlib import Path
from datetime import datetime
from typing import List, Dict

DATA_DIR = Path("data")
PAYSTUBS_DIR = DATA_DIR / "paystubs"
COMPANIES_DIR = DATA_DIR / "companies"
CONSOLIDATED_DIR = DATA_DIR / "consolidated"

class DataManager:
    """Gestion des données de paie"""
    
    @staticmethod
    def load_paystub_data(company_id: str, period: str) -> pl.DataFrame:
        """Charger les données de paie pour une entreprise"""
        file_path = DataManager.get_company_file(company_id, period)
        if file_path.exists():
            return pl.read_parquet(file_path)
        else:
            return DataManager.create_empty_paystub_df()
    
    @staticmethod
    def save_paystub_data(df: pl.DataFrame, company_id: str, period: str):
        """Sauvegarder les données de paie"""
        file_path = DataManager.get_company_file(company_id, period)
        df.write_parquet(file_path)
    
    @staticmethod
    def create_empty_paystub_df() -> pl.DataFrame:
        """Créer un DataFrame vide avec la structure correcte"""
        return pl.DataFrame({
            'matricule': pl.Series([], dtype=pl.Utf8),
            'nom': pl.Series([], dtype=pl.Utf8),
            'prenom': pl.Series([], dtype=pl.Utf8),
            'email': pl.Series([], dtype=pl.Utf8),
            'base_heures': pl.Series([], dtype=pl.Float64),
            'heures_conges_payes': pl.Series([], dtype=pl.Float64),
            'heures_absence': pl.Series([], dtype=pl.Float64),
            'type_absence': pl.Series([], dtype=pl.Utf8),
            'prime': pl.Series([], dtype=pl.Float64),
            'type_prime': pl.Series([], dtype=pl.Utf8),
            'heures_sup_125': pl.Series([], dtype=pl.Float64),
            'heures_sup_150': pl.Series([], dtype=pl.Float64),
            'heures_jours_feries': pl.Series([], dtype=pl.Float64),
            'heures_dimanche': pl.Series([], dtype=pl.Float64),
            'tickets_restaurant': pl.Series([], dtype=pl.Float64),
            'avantage_logement': pl.Series([], dtype=pl.Float64),
            'avantage_transport': pl.Series([], dtype=pl.Float64),
            'date_sortie': pl.Series([], dtype=pl.Date),
            'remarques': pl.Series([], dtype=pl.Utf8),
            'pays_residence': pl.Series([], dtype=pl.Utf8),
            'salaire_base': pl.Series([], dtype=pl.Float64),
            'salaire_brut': pl.Series([], dtype=pl.Float64),
            'total_charges_salariales': pl.Series([], dtype=pl.Float64),
            'total_charges_patronales': pl.Series([], dtype=pl.Float64),
            'salaire_net': pl.Series([], dtype=pl.Float64),
            'statut_validation': pl.Series([], dtype=pl.Utf8),
            'edge_case_flag': pl.Series([], dtype=pl.Boolean),
            'edge_case_reason': pl.Series([], dtype=pl.Utf8)
        })
    
    @staticmethod
    def get_companies_list() -> List[Dict]:
        """Obtenir la liste des entreprises"""
        companies_file = COMPANIES_DIR / "companies.parquet"
        if companies_file.exists():
            df = pl.read_parquet(companies_file)
            return df.to_dicts()
        else:
            sample_companies = pl.DataFrame({
                'id': ['CARAX_MONACO', 'RG_CAPITAL_SERVICES'],
                'name': ['CARAX MONACO', 'RG CAPITAL SERVICES'],
                'siret': ['763000000', '169000000']
            })
            sample_companies.write_parquet(companies_file)
            return sample_companies.to_dicts()
        
class DataConsolidation:
    """Gestion de la consolidation des données par mois/année"""
    
    @staticmethod
    def save_period_data(df: pl.DataFrame, company_id: str, year: int, month: int) -> None:
        """Sauvegarder les données pour une période"""
        file_path = DataConsolidation.get_period_file(company_id, year, month)
        
        df = df.with_columns([
            pl.lit(company_id).alias('company_id'),
            pl.lit(year).alias('period_year'),
            pl.lit(month).alias('period_month'),
            pl.lit(f"{month:02d}-{year}").alias('period_str'),
            pl.lit(datetime.now()).alias('last_modified')
        ])
        
        df.write_parquet(file_path)
    
    @staticmethod
    def load_period_data(company_id: str, year: int, month: int) -> pl.DataFrame:
        """Charger les données pour une période"""
        file_path = DataConsolidation.get_period_file(company_id, year, month)
        
        if file_path.exists():
            return pl.read_parquet(file_path)
        
        return DataManager.create_empty_paystub_df()