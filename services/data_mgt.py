import pyarrow
import pyarrow.parquet as pq
HAS_PYARROW = True
import pandas as pd
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
    def get_company_file(company_id: str, period: str) -> Path:
        """Obtenir le chemin du fichier pour une entreprise et période"""
        return PAYSTUBS_DIR / f"{company_id}_{period}.parquet"
    
    @staticmethod
    def load_paystub_data(company_id: str, period: str) -> pd.DataFrame:
        """Charger les données de paie pour une entreprise"""
        file_path = DataManager.get_company_file(company_id, period)
        if file_path.exists():
            if HAS_PYARROW:
                return pd.read_parquet(file_path)
            else:
                return pd.read_pickle(file_path.with_suffix('.pkl'))
        else:
            return DataManager.create_empty_paystub_df()
    
    @staticmethod
    def save_paystub_data(df: pd.DataFrame, company_id: str, period: str):
        """Sauvegarder les données de paie"""
        file_path = DataManager.get_company_file(company_id, period)
        if HAS_PYARROW:
            df.to_parquet(file_path)
        else:
            df.to_pickle(file_path.with_suffix('.pkl'))
    
    @staticmethod
    def create_empty_paystub_df() -> pd.DataFrame:
        """Créer un DataFrame vide avec la structure correcte"""
        columns = [
            'matricule', 'nom', 'prenom', 'email', 'base_heures', 'heures_conges_payes',
            'heures_absence', 'type_absence', 'prime', 'type_prime',
            'heures_sup_125', 'heures_sup_150', 'heures_jours_feries',
            'heures_dimanche', 'tickets_restaurant', 'avantage_logement',
            'avantage_transport', 'date_sortie', 'remarques', 'pays_residence',
            'salaire_base', 'salaire_brut', 'total_charges_salariales',
            'total_charges_patronales', 'salaire_net', 'statut_validation',
            'edge_case_flag', 'edge_case_reason'
        ]
        return pd.DataFrame(columns=columns)
    
    @staticmethod
    def get_companies_list() -> List[Dict]:
        """Obtenir la liste des entreprises"""
        companies_file = COMPANIES_DIR / "companies.parquet"
        if companies_file.exists():
            if HAS_PYARROW:
                df = pd.read_parquet(companies_file)
            else:
                df = pd.read_pickle(companies_file.with_suffix('.pkl'))
            return df.to_dict('records')
        else:
            sample_companies = pd.DataFrame([
                {'id': 'CARAX_MONACO', 'name': 'CARAX MONACO', 'siret': '763000000'},
                {'id': 'RG_CAPITAL_SERVICES', 'name': 'RG CAPITAL SERVICES', 'siret': '169000000'}
            ])
            if HAS_PYARROW:
                sample_companies.to_parquet(companies_file)
            else:
                sample_companies.to_pickle(companies_file.with_suffix('.pkl'))
            return sample_companies.to_dict('records')

class DataConsolidation:
    """Gestion de la consolidation des données par mois/année"""
    
    @staticmethod
    def get_period_file(company_id: str, year: int, month: int) -> Path:
        """Obtenir le chemin du fichier consolidé pour une période"""
        data_dir = CONSOLIDATED_DIR / str(year)
        data_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{company_id}_{month:02d}_{year}.parquet"
        return data_dir / filename
    
    @staticmethod
    def save_period_data(df: pd.DataFrame, company_id: str, year: int, month: int) -> None:
        """Sauvegarder les données pour une période"""
        file_path = DataConsolidation.get_period_file(company_id, year, month)
        
        df['company_id'] = company_id
        df['period_year'] = year
        df['period_month'] = month
        df['period_str'] = f"{month:02d}-{year}"
        df['last_modified'] = datetime.now()
        
        if HAS_PYARROW:
            df.to_parquet(file_path, index=False)
        else:
            df.to_pickle(file_path.with_suffix('.pkl'))
    
    @staticmethod
    def load_period_data(company_id: str, year: int, month: int) -> pd.DataFrame:
        """Charger les données pour une période"""
        file_path = DataConsolidation.get_period_file(company_id, year, month)
        
        if file_path.exists():
            if HAS_PYARROW:
                return pd.read_parquet(file_path)
            else:
                pkl_path = file_path.with_suffix('.pkl')
                if pkl_path.exists():
                    return pd.read_pickle(pkl_path)
        
        return DataManager.create_empty_paystub_df()
