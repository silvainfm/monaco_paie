"""
Import/Export Module with Cross-Border Worker Support
=====================================================
Handles Excel import/export and calculations for Monaco, French, and Italian residents
"""

import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
import io
from pathlib import Path
import json

class CrossBorderTaxation:
    """
    Gestion de la fiscalité transfrontalière Monaco/France/Italie
    """
    
    # Accord France-Monaco: Les français travaillant à Monaco sont imposés en France
    # Accord Italie-Monaco: Imposition à la source à Monaco avec crédit d'impôt en Italie
    
    @dataclass
    class ResidencyRules:
        """Règles selon le pays de résidence"""
        
        MONACO_RESIDENT = {
            'income_tax': 0,  # Pas d'impôt sur le revenu à Monaco
            'social_charges': 'MONACO_FULL',
            'tax_treaty': None,
            'withholding_tax': 0
        }
        
        FRANCE_RESIDENT = {
            'income_tax': 'FRANCE_PROGRESSIVE',  # Barème progressif français
            'social_charges': 'MONACO_FULL',  # Charges sociales Monaco
            'csg_crds': True,  # CSG/CRDS pour résidents français
            'tax_treaty': 'FRANCE_MONACO_1963',
            'withholding_tax': 0,  # Pas de retenue à la source à Monaco
            'prelevement_source': True  # Prélèvement à la source en France
        }
        
        ITALY_RESIDENT = {
            'income_tax': 'ITALY_PROGRESSIVE',
            'social_charges': 'MONACO_FULL',
            'tax_treaty': 'ITALY_MONACO_FRONTALIERS',
            'withholding_tax': 0.15,  # 15% retenue à la source Monaco
            'frontalier_status': True  # Statut frontalier possible
        }
    
    # CSG/CRDS pour résidents français (2024)
    CSG_CRDS_RATES = {
        'CSG_DEDUCTIBLE': 6.80,
        'CSG_NON_DEDUCTIBLE': 2.40,
        'CRDS': 0.50,
        'TOTAL': 9.70
    }
    
    # Barème impôt sur le revenu France 2024 (mensuel)
    FRANCE_TAX_BRACKETS = [
        (10777 / 12, 0),      # Jusqu'à 898€/mois: 0%
        (27478 / 12, 0.11),   # 898€ à 2290€/mois: 11%
        (78570 / 12, 0.30),   # 2290€ à 6547€/mois: 30%
        (168994 / 12, 0.41),  # 6547€ à 14083€/mois: 41%
        (float('inf'), 0.45)  # Au-delà: 45%
    ]
    
    # Barème IRPEF Italie 2024 (annuel, converti en mensuel)
    ITALY_TAX_BRACKETS = [
        (15000 / 12, 0.23),   # Jusqu'à 1250€/mois: 23%
        (28000 / 12, 0.25),   # 1250€ à 2333€/mois: 25%
        (50000 / 12, 0.35),   # 2333€ à 4167€/mois: 35%
        (float('inf'), 0.43)  # Au-delà: 43%
    ]
    
    @classmethod
    def calculate_csg_crds(cls, salaire_brut: float) -> Dict[str, float]:
        """
        Calculer CSG/CRDS pour résidents français
        Base: 98.25% du salaire brut (après abattement de 1.75%)
        """
        base_csg = salaire_brut * 0.9825
        
        return {
            'base_csg': round(base_csg, 2),
            'csg_deductible': round(base_csg * cls.CSG_CRDS_RATES['CSG_DEDUCTIBLE'] / 100, 2),
            'csg_non_deductible': round(base_csg * cls.CSG_CRDS_RATES['CSG_NON_DEDUCTIBLE'] / 100, 2),
            'crds': round(base_csg * cls.CSG_CRDS_RATES['CRDS'] / 100, 2),
            'total_csg_crds': round(base_csg * cls.CSG_CRDS_RATES['TOTAL'] / 100, 2)
        }
    
    @classmethod
    def calculate_french_withholding(cls, salaire_net_imposable: float, 
                                    taux_personnalise: Optional[float] = None) -> float:
        """
        Calculer le prélèvement à la source français
        
        Args:
            salaire_net_imposable: Salaire net imposable mensuel
            taux_personnalise: Taux personnalisé communiqué par l'administration fiscale
        """
        if taux_personnalise:
            return round(salaire_net_imposable * taux_personnalise, 2)
        
        # Calcul avec le barème par défaut
        tax = 0
        remaining = salaire_net_imposable
        previous_limit = 0
        
        for limit, rate in cls.FRANCE_TAX_BRACKETS:
            if remaining <= 0:
                break
            
            taxable_in_bracket = min(remaining, limit - previous_limit)
            tax += taxable_in_bracket * rate
            remaining -= taxable_in_bracket
            previous_limit = limit
        
        return round(tax, 2)
    
    @classmethod
    def calculate_italian_withholding(cls, salaire_brut: float) -> float:
        """
        Calculer la retenue à la source italienne (15% pour frontaliers)
        """
        return round(salaire_brut * 0.15, 2)
    
    @classmethod
    def apply_residency_rules(cls, payslip_data: Dict, residency: str) -> Dict:
        """
        Appliquer les règles fiscales selon la résidence
        
        Args:
            payslip_data: Données de paie calculées
            residency: 'MONACO', 'FRANCE', ou 'ITALY'
        """
        enhanced_data = payslip_data.copy()
        
        if residency == 'FRANCE':
            # Ajouter CSG/CRDS
            csg_crds = cls.calculate_csg_crds(payslip_data['salaire_brut'])
            enhanced_data['csg_crds'] = csg_crds
            enhanced_data['total_charges_salariales'] += csg_crds['total_csg_crds']
            
            # Calculer le net imposable
            net_imposable = payslip_data['salaire_brut'] - payslip_data['total_charges_salariales']
            
            # Prélèvement à la source
            taux_pas = payslip_data.get('taux_prelevement_source')
            pas = cls.calculate_french_withholding(net_imposable, taux_pas)
            enhanced_data['prelevement_source'] = pas
            enhanced_data['salaire_net'] = payslip_data['salaire_net'] - csg_crds['total_csg_crds'] - pas
            
        elif residency == 'ITALY':
            # Retenue à la source italienne
            withholding = cls.calculate_italian_withholding(payslip_data['salaire_brut'])
            enhanced_data['retenue_source_italie'] = withholding
            enhanced_data['salaire_net'] = payslip_data['salaire_net'] - withholding
            
        enhanced_data['pays_residence'] = residency
        
        return enhanced_data

class ExcelImportExport:
    """
    Gestionnaire d'import/export Excel pour les données de paie
    """
    
    # Mapping des colonnes Excel vers système interne
    EXCEL_COLUMN_MAPPING = {
        # Colonnes d'entrée (from Excel)
        "Matricule": "matricule",
        "Nom": "nom",
        "Prénom": "prenom",
        "Base heures": "base_heures",
        "Heures congés payés": "heures_conges_payes",
        "Heures absence": "heures_absence",
        "Type absence": "type_absence",
        "Prime": "prime",
        "Type de prime": "type_prime",
        "Heures Sup 125": "heures_sup_125",
        "Heures Sup 150": "heures_sup_150",
        "Heures jours fériés": "heures_jours_feries",
        "Heures dimanche": "heures_dimanche",
        "Tickets restaurant": "tickets_restaurant",
        "Avantage logement": "avantage_logement",
        "Avantage transport": "avantage_transport",
        "Date de Sortie": "date_sortie",
        "Remarques": "remarques",
        "Salaire de base": "salaire_base",
        "Pays résidence": "pays_residence",
        "Taux prélèvement source": "taux_prelevement_source",
        "Email": "email"
    }
    
    # Colonnes requises pour l'import
    REQUIRED_COLUMNS = [
        "Matricule", "Nom", "Prénom", "Base heures", "Salaire de base"
    ]
    
    # Colonnes de sortie (calculées)
    OUTPUT_COLUMNS = [
        "matricule", "nom", "prenom", "salaire_base", "base_heures",
        "heures_sup_125", "montant_hs_125", "heures_sup_150", "montant_hs_150",
        "prime", "type_prime", "heures_jours_feries", "montant_jours_feries",
        "heures_dimanche", "montant_dimanches", "heures_absence", "type_absence",
        "retenue_absence", "tickets_restaurant", "avantage_logement", 
        "avantage_transport", "salaire_brut", "total_charges_salariales",
        "total_charges_patronales", "salaire_net", "cout_total_employeur",
        "pays_residence", "csg_crds_total", "prelevement_source",
        "retenue_source_italie", "date_sortie", "remarques", "statut_validation",
        "edge_case_flag", "edge_case_reason"
    ]
    
    @classmethod
    def validate_excel_format(cls, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Valider le format du fichier Excel importé
        
        Returns:
            Tuple (is_valid, list_of_errors)
        """
        errors = []
        
        # Vérifier les colonnes requises
        missing_columns = set(cls.REQUIRED_COLUMNS) - set(df.columns)
        if missing_columns:
            errors.append(f"Colonnes manquantes: {', '.join(missing_columns)}")
        
        # Vérifier les types de données
        if 'Base heures' in df.columns:
            try:
                pd.to_numeric(df['Base heures'], errors='coerce')
            except:
                errors.append("'Base heures' doit contenir des valeurs numériques")
        
        if 'Salaire de base' in df.columns:
            try:
                pd.to_numeric(df['Salaire de base'], errors='coerce')
            except:
                errors.append("'Salaire de base' doit contenir des valeurs numériques")
        
        # Vérifier les matricules uniques
        if 'Matricule' in df.columns:
            duplicates = df['Matricule'].duplicated().sum()
            if duplicates > 0:
                errors.append(f"{duplicates} matricules en double détectés")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    @classmethod
    def import_from_excel(cls, file_path: Union[str, Path, io.BytesIO]) -> pd.DataFrame:
        """
        Importer les données depuis un fichier Excel
        
        Args:
            file_path: Chemin vers le fichier ou buffer
            
        Returns:
            DataFrame avec les données importées et mappées
        """
        # Lire le fichier Excel
        df = pd.read_excel(file_path, sheet_name=0)
        
        # Valider le format
        is_valid, errors = cls.validate_excel_format(df)
        if not is_valid:
            raise ValueError(f"Erreurs de validation: {'; '.join(errors)}")
        
        # Mapper les colonnes
        df_mapped = df.rename(columns=cls.EXCEL_COLUMN_MAPPING)
        
        # Ajouter les colonnes manquantes avec valeurs par défaut
        for col in cls.EXCEL_COLUMN_MAPPING.values():
            if col not in df_mapped.columns:
                if 'heures' in col or 'montant' in col or 'charges' in col:
                    df_mapped[col] = 0
                elif col == 'pays_residence':
                    df_mapped[col] = 'MONACO'  # Par défaut
                elif col == 'type_absence':
                    df_mapped[col] = 'non_payee'
                elif col == 'type_prime':
                    df_mapped[col] = 'performance'
                else:
                    df_mapped[col] = None
        
        # Convertir les types
        numeric_columns = [
            'base_heures', 'salaire_base', 'heures_sup_125', 'heures_sup_150',
            'heures_jours_feries', 'heures_dimanche', 'heures_absence',
            'prime', 'tickets_restaurant', 'avantage_logement', 'avantage_transport',
            'heures_conges_payes', 'taux_prelevement_source'
        ]
        
        for col in numeric_columns:
            if col in df_mapped.columns:
                df_mapped[col] = pd.to_numeric(df_mapped[col], errors='coerce').fillna(0)
        
        # Convertir les dates
        if 'date_sortie' in df_mapped.columns:
            df_mapped['date_sortie'] = pd.to_datetime(df_mapped['date_sortie'], errors='coerce')
        
        # Standardiser le pays de résidence
        if 'pays_residence' in df_mapped.columns:
            df_mapped['pays_residence'] = df_mapped['pays_residence'].str.upper().replace({
                'FR': 'FRANCE',
                'IT': 'ITALY',
                'ITALIE': 'ITALY',
                'MC': 'MONACO',
                'MONACO': 'MONACO'
            }).fillna('MONACO')
        
        # Ajouter les colonnes de statut
        df_mapped['statut_validation'] = 'À traiter'
        df_mapped['edge_case_flag'] = False
        df_mapped['edge_case_reason'] = ''
        df_mapped['date_import'] = datetime.now()
        
        return df_mapped
    
    @classmethod
    def export_to_excel(cls, df: pd.DataFrame, 
                       include_calculations: bool = True,
                       include_details: bool = False) -> io.BytesIO:
        """
        Exporter les données vers Excel
        
        Args:
            df: DataFrame à exporter
            include_calculations: Inclure les colonnes calculées
            include_details: Inclure le détail des charges
            
        Returns:
            BytesIO buffer contenant le fichier Excel
        """
        output = io.BytesIO()
        
        # Use a simpler approach if xlsxwriter not available
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # Feuille principale
                if include_calculations:
                    # Use available columns from OUTPUT_COLUMNS
                    export_cols = [col for col in cls.OUTPUT_COLUMNS if col in df.columns]
                    export_df = df[export_cols].copy()
                else:
                    # Seulement les colonnes d'entrée
                    export_df = df[[col for col in cls.EXCEL_COLUMN_MAPPING.values() 
                                   if col in df.columns]].copy()
                
                # Formater les colonnes monétaires
                money_columns = [
                    'salaire_base', 'salaire_brut', 'salaire_net',
                    'total_charges_salariales', 'total_charges_patronales',
                    'cout_total_employeur', 'prime', 'avantage_logement',
                    'avantage_transport', 'montant_hs_125', 'montant_hs_150',
                    'montant_jours_feries', 'montant_dimanches', 'retenue_absence',
                    'csg_crds_total', 'prelevement_source', 'retenue_source_italie'
                ]
                
                for col in money_columns:
                    if col in export_df.columns:
                        export_df[col] = export_df[col].round(2)
                
                # Écrire la feuille principale
                export_df.to_excel(writer, sheet_name='Paie', index=False)
                
                # Ajouter une feuille de synthèse
                if include_calculations and 'salaire_brut' in df.columns:
                    summary_data = {
                        'Statistiques': [
                            'Nombre de salariés', 
                            'Masse salariale brute', 
                            'Total charges salariales', 
                            'Total charges patronales',
                            'Coût total', 
                            'Salaire net moyen'
                        ],
                        'Valeurs': [
                            len(df),
                            df['salaire_brut'].sum() if 'salaire_brut' in df.columns else 0,
                            df['total_charges_salariales'].sum() if 'total_charges_salariales' in df.columns else 0,
                            df['total_charges_patronales'].sum() if 'total_charges_patronales' in df.columns else 0,
                            df['cout_total_employeur'].sum() if 'cout_total_employeur' in df.columns else 0,
                            df['salaire_net'].mean() if 'salaire_net' in df.columns else 0
                        ]
                    }
                    
                    summary_df = pd.DataFrame(summary_data)
                    summary_df.to_excel(writer, sheet_name='Synthèse', index=False)
                
        except ImportError:
            # Fallback to basic Excel export
            export_df.to_excel(output, index=False)
        
        output.seek(0)
        return output
    
    @classmethod
    def create_template(cls) -> io.BytesIO:
        """
        Créer un fichier Excel template pour l'import
        
        Returns:
            BytesIO buffer contenant le template Excel
        """
        # Créer un DataFrame exemple
        template_data = {
            'Matricule': ['S000001', 'S000002'],
            'Nom': ['EXEMPLE', 'TEST'],
            'Prénom': ['Jean', 'Marie'],
            'Email': ['jean.exemple@email.com', 'marie.test@email.com'],
            'Salaire de base': [3500.00, 4200.00],
            'Base heures': [169, 169],
            'Heures congés payés': [0, 7],
            'Heures absence': [0, 0],
            'Type absence': ['', ''],
            'Prime': [0, 500],
            'Type de prime': ['', 'performance'],
            'Heures Sup 125': [0, 10],
            'Heures Sup 150': [0, 0],
            'Heures jours fériés': [0, 0],
            'Heures dimanche': [0, 0],
            'Tickets restaurant': [20, 20],
            'Avantage logement': [0, 0],
            'Avantage transport': [50, 0],
            'Pays résidence': ['MONACO', 'FRANCE'],
            'Taux prélèvement source': [0, 0.15],
            'Date de Sortie': ['', ''],
            'Remarques': ['', 'À vérifier']
        }
        
        template_df = pd.DataFrame(template_data)
        
        output = io.BytesIO()
        
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                template_df.to_excel(writer, sheet_name='Données', index=False)
                
                # Ajouter une feuille d'instructions
                instructions = pd.DataFrame({
                    'Instructions': [
                        'Ce fichier est un template pour importer les données de paie',
                        '',
                        'Colonnes obligatoires:',
                        '- Matricule: Identifiant unique du salarié',
                        '- Nom: Nom de famille',
                        '- Prénom: Prénom',
                        '- Salaire de base: Salaire mensuel de base',
                        '- Base heures: Nombre d\'heures de base (généralement 169)',
                        '',
                        'Colonnes optionnelles:',
                        '- Email: Adresse email pour l\'envoi des bulletins',
                        '- Heures Sup 125/150: Heures supplémentaires',
                        '- Prime: Montant de la prime',
                        '- Type de prime: performance, anciennete, 13eme_mois, etc.',
                        '- Tickets restaurant: Nombre de tickets',
                        '- Pays résidence: MONACO, FRANCE, ou ITALY',
                        '- Taux prélèvement source: Pour résidents français (ex: 0.15 pour 15%)',
                        '- Date de Sortie: Date de départ du salarié',
                        '- Remarques: Notes particulières (déclenche vérification manuelle)',
                        '',
                        'Types d\'absence possibles:',
                        '- maladie_maintenue: Maladie avec maintien de salaire',
                        '- conges_sans_solde: Congés sans solde',
                        '- conges_payes: Congés payés',
                        '- non_payee: Absence non payée (par défaut)'
                    ]
                })
                
                instructions.to_excel(writer, sheet_name='Instructions', index=False)
        except ImportError:
            # Fallback to basic Excel
            template_df.to_excel(output, index=False)
        
        output.seek(0)
        return output

class DataConsolidation:
    """
    Gestion de la consolidation des données par mois/année
    """
    
    @staticmethod
    def get_period_file(company_id: str, month: int, year: int) -> Path:
        """
        Obtenir le chemin du fichier consolidé pour une période
        
        Args:
            company_id: Identifiant de l'entreprise
            year: Année
            month: Mois
            
        Returns:
            Path vers le fichier parquet
        """
        from pathlib import Path
        
        data_dir = Path("data") / "consolidated" / str(year)
        data_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{company_id}_{month:02d}_{year}.parquet"
        return data_dir / filename
    
    @staticmethod
    def save_period_data(df: pd.DataFrame, company_id: str, 
                        month: int, year: int) -> None:
        """
        Sauvegarder les données pour une période
        """
        file_path = DataConsolidation.get_period_file(company_id, month, year)
        
        # Ajouter les métadonnées
        df['company_id'] = company_id
        df['period_year'] = year
        df['period_month'] = month
        df['period_str'] = f"{month:02d}-{year}"
        df['last_modified'] = datetime.now()
        
        # Sauvegarder - try parquet first, fallback to pickle
        try:
            df.to_parquet(file_path, index=False)
        except:
            df.to_pickle(file_path.with_suffix('.pkl'))
    
    @staticmethod
    def load_period_data(company_id: str, month: int, year: int) -> pd.DataFrame:
        """
        Charger les données pour une période
        """
        file_path = DataConsolidation.get_period_file(company_id, month, year)
        
        if file_path.exists():
            try:
                return pd.read_parquet(file_path)
            except:
                pkl_path = file_path.with_suffix('.pkl')
                if pkl_path.exists():
                    return pd.read_pickle(pkl_path)
        
        # Retourner un DataFrame vide avec la structure correcte
        return pd.DataFrame(columns=ExcelImportExport.OUTPUT_COLUMNS + [
            'company_id', 'period_year', 'period_month', 
            'period_str', 'last_modified', 'email'
        ])
    
    @staticmethod
    def get_year_summary(company_id: str, year: int) -> pd.DataFrame:
        """
        Obtenir un résumé annuel consolidé
        """
        summaries = []
        
        for month in range(1, 13):
            df = DataConsolidation.load_period_data(company_id, month, year)
            
            if not df.empty:
                summary = {
                    'month': month,
                    'period': f"{month:02d}-{year}",
                    'employee_count': len(df),
                    'total_brut': df['salaire_brut'].sum() if 'salaire_brut' in df.columns else 0,
                    'total_net': df['salaire_net'].sum() if 'salaire_net' in df.columns else 0,
                    'total_charges_sal': df['total_charges_salariales'].sum() if 'total_charges_salariales' in df.columns else 0,
                    'total_charges_pat': df['total_charges_patronales'].sum() if 'total_charges_patronales' in df.columns else 0,
                    'total_cost': df['cout_total_employeur'].sum() if 'cout_total_employeur' in df.columns else 0,
                    'edge_cases': df['edge_case_flag'].sum() if 'edge_case_flag' in df.columns else 0,
                    'validated': (df['statut_validation'] == 'Validé').sum() if 'statut_validation' in df.columns else 0
                }
                summaries.append(summary)
        
        return pd.DataFrame(summaries)
    
    @staticmethod
    def archive_period(company_id: str, month: int, year: int) -> bool:
        """
        Archiver les données d'une période (pour audit)
        """
        from shutil import copy2
        
        source_file = DataConsolidation.get_period_file(company_id, month, year)
        
        if not source_file.exists():
            return False
        
        # Créer le répertoire d'archive
        archive_dir = Path("data") / "archives" / str(year) / str(month)
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Nom du fichier d'archive avec timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = archive_dir / f"{company_id}_{year}_{month:02d}_{timestamp}.parquet"

        # Copier le fichier
        copy2(source_file, archive_file)
        
        return True

# Tests
if __name__ == "__main__":
    # Test cross-border calculations
    test_employee_france = {
        'matricule': 'S000001',
        'nom': 'DUPONT',
        'prenom': 'Jean',
        'salaire_brut': 4500.00,
        'total_charges_salariales': 990.00,
        'salaire_net': 3510.00,
        'taux_prelevement_source': 0.12
    }
    
    # Appliquer les règles pour résident français
    result = CrossBorderTaxation.apply_residency_rules(test_employee_france, 'FRANCE')
    
    print("=== Test Résident Français ===")
    print(f"Salaire brut: {test_employee_france['salaire_brut']} €")
    print(f"CSG/CRDS: {result['csg_crds']['total_csg_crds']} €")
    print(f"Prélèvement à la source: {result.get('prelevement_source', 0)} €")
    print(f"Salaire net final: {result['salaire_net']} €")
