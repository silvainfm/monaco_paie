"""
Module de calculs de paie spécifiques à Monaco
===============================================
Includes all Monaco-specific payroll calculations, social charges, and tax rules
Rates are loaded from CSV files for easy yearly updates
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import polars as pl
import os
from pathlib import Path
import math

@dataclass
class MonacoPayrollConstants:
    """Constantes de paie pour Monaco - loaded from CSV by year"""

    def __init__(self, year: int = None):
        """Initialize constants for a specific year"""
        if year is None:
            year = datetime.now().year
        self.year = year
        self._load_constants_from_csv()

    def _load_constants_from_csv(self):
        """Load constants from CSV file for the specific year"""
        csv_path = Path("data/config") / "payroll_rates.csv"

        # Default values (2024)
        defaults = {
            'PLAFOND_SS_T1': 3428.00,
            'PLAFOND_SS_T2': 13712.00,
            'BASE_HEURES_LEGALE': 169.00,
            'SMIC_HORAIRE': 11.88,
            'TAUX_HS_125': 1.25,
            'TAUX_HS_150': 1.50,
            'TICKET_RESTO_VALEUR': 9.00,
            'TICKET_RESTO_PART_PATRONALE': 0.60,
            'TICKET_RESTO_PART_SALARIALE': 0.40
        }

        if csv_path.exists():
            try:
                df = pl.read_csv(csv_path)
                year_col = f"taux_{self.year}"

                # Check if year column exists
                if year_col not in df.columns:
                    print(f"Attention: pas de taux pour {self.year} dans le fichier CSV. Utilisation des valeurs par défaut.")
                    for key, value in defaults.items():
                        setattr(self, key, value)
                    return

                # Filter constants
                constants_df = df.filter(pl.col("category") == "CONSTANT")

                # Load each constant
                for row in constants_df.iter_rows(named=True):
                    const_name = row["code"]
                    if const_name in defaults:
                        raw_val = row.get(year_col)
                        value = (
                            float(raw_val)
                            if raw_val is not None and str(raw_val).strip() != ""
                            else defaults[const_name]
                        )
                        setattr(self, const_name, value)

                # Set missing constants to defaults
                for key, value in defaults.items():
                    if not hasattr(self, key):
                        setattr(self, key, value)

            except Exception as e:
                print(f"Erreur lors du chargement des constantes depuis le CSV : {e}. Utilisation des valeurs par défaut.")
                for key, value in defaults.items():
                    setattr(self, key, value)
        else:
            # Use defaults if no CSV file exists
            for key, value in defaults.items():
                setattr(self, key, value)
            # Create default CSV for future use
            self._create_default_csv(csv_path)

    def _create_default_csv(self, csv_path: Path):
        """Create default CSV file with all rates and constants"""
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        data = [
            # Constants
            {'category': 'CONSTANT', 'type': '', 'code': 'PLAFOND_SS_T1', 'description': 'Plafond Sécurité Sociale Tranche 1',
             'plafond': '', 'taux_2024': 3428.00, 'taux_2025': 3428.00},
            {'category': 'CONSTANT', 'type': '', 'code': 'PLAFOND_SS_T2', 'description': 'Plafond Sécurité Sociale Tranche 2',
             'plafond': '', 'taux_2024': 13712.00, 'taux_2025': 13712.00},
            {'category': 'CONSTANT', 'type': '', 'code': 'BASE_HEURES_LEGALE', 'description': 'Base légale heures mensuelles',
             'plafond': '', 'taux_2024': 169.00, 'taux_2025': 169.00},
            {'category': 'CONSTANT', 'type': '', 'code': 'SMIC_HORAIRE', 'description': 'SMIC horaire Monaco',
             'plafond': '', 'taux_2024': 11.88, 'taux_2025': 11.88},
            {'category': 'CONSTANT', 'type': '', 'code': 'TAUX_HS_125', 'description': 'Taux heures sup 125%',
             'plafond': '', 'taux_2024': 1.25, 'taux_2025': 1.25},
            {'category': 'CONSTANT', 'type': '', 'code': 'TAUX_HS_150', 'description': 'Taux heures sup 150%',
             'plafond': '', 'taux_2024': 1.50, 'taux_2025': 1.50},
            {'category': 'CONSTANT', 'type': '', 'code': 'TICKET_RESTO_VALEUR', 'description': 'Valeur unitaire ticket restaurant',
             'plafond': '', 'taux_2024': 9.00, 'taux_2025': 9.00},
            {'category': 'CONSTANT', 'type': '', 'code': 'TICKET_RESTO_PART_PATRONALE', 'description': 'Part patronale ticket restaurant',
             'plafond': '', 'taux_2024': 0.60, 'taux_2025': 0.60},
            {'category': 'CONSTANT', 'type': '', 'code': 'TICKET_RESTO_PART_SALARIALE', 'description': 'Part salariale ticket restaurant',
             'plafond': '', 'taux_2024': 0.40, 'taux_2025': 0.40}
        ]

        df = pl.DataFrame(data)
        df.write_csv(csv_path)
        print(f"Created default rates CSV: {csv_path}")

class ChargesSocialesMonaco:
    """Calcul des charges sociales selon la législation monégasque"""

    def __init__(self, year: int = None, month: int = None):
        """
        Initialize with rates for a specific year and month

        Args:
            year: Year for rate calculation
            month: Month for rate calculation (1-12). Determines which rates apply
                   for October-effective charges (CAR, CCSS, CMRC)
        """
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month
        self.year = year
        self.month = month
        self._load_rates_from_csv()

    def _get_rate_year(self, effective_date: str) -> int:
        """
        Determine which year's rate to use based on effective date and current month

        Args:
            effective_date: "OCTOBER" or "JANUARY"

        Returns:
            Year to use for rate lookup

        Logic:
            - OCTOBER charges (CAR, CCSS, CMRC): Change on October 1st
              * Jan-Sep: use current year rates
              * Oct-Dec: use next year rates
            - JANUARY charges: Change on January 1st
              * All months: use current year rates
        """
        if effective_date == "OCTOBER" and self.month >= 10:
            return self.year + 1
        return self.year

    def _load_rates_from_csv(self):
        """Load social charge rates from unified CSV file"""
        csv_path = Path("data/config") / "payroll_rates.csv"
        
        # Default rates for fallback
        default_salarial = {
            'CAR': {'taux': 6.85, 'plafond': None, 'description': 'Caisse Autonome des Retraites'},
            'CCSS': {'taux': 14.75, 'plafond': None, 'description': 'Caisse de Compensation des Services Sociaux'},
            'ASSEDIC_T1': {'taux': 2.40, 'plafond': 'T1', 'description': 'Assurance chômage Tranche 1'},
            'ASSEDIC_T2': {'taux': 2.40, 'plafond': 'T2', 'description': 'Assurance chômage Tranche 2'},
            'RETRAITE_COMP_T1': {'taux': 3.15, 'plafond': 'T1', 'description': 'Retraite complémentaire Tranche 1'},
            'RETRAITE_COMP_T2': {'taux': 8.64, 'plafond': 'T2', 'description': 'Retraite complémentaire Tranche 2'},
            'CONTRIB_EQUILIBRE_TECH': {'taux': 0.14, 'plafond': None, 'description': 'Contribution équilibre technique'},
            'CONTRIB_EQUILIBRE_GEN_T1': {'taux': 0.86, 'plafond': 'T1', 'description': 'Contribution équilibre général T1'},
            'CONTRIB_EQUILIBRE_GEN_T2': {'taux': 1.08, 'plafond': 'T2', 'description': 'Contribution équilibre général T2'}
        }
        
        default_patronal = {
            'CAR': {'taux': 8.35, 'plafond': None, 'description': 'Caisse Autonome des Retraites'},
            'CMRC': {'taux': 5.22, 'plafond': None, 'description': 'Caisse Monégasque de Retraite Complémentaire'},
            'ASSEDIC_T1': {'taux': 4.05, 'plafond': 'T1', 'description': 'Assurance chômage Tranche 1'},
            'ASSEDIC_T2': {'taux': 4.05, 'plafond': 'T2', 'description': 'Assurance chômage Tranche 2'},
            'RETRAITE_COMP_T1': {'taux': 4.72, 'plafond': 'T1', 'description': 'Retraite complémentaire Tranche 1'},
            'RETRAITE_COMP_T2': {'taux': 12.95, 'plafond': 'T2', 'description': 'Retraite complémentaire Tranche 2'},
            'CONTRIB_EQUILIBRE_TECH': {'taux': 0.21, 'plafond': None, 'description': 'Contribution équilibre technique'},
            'CONTRIB_EQUILIBRE_GEN_T1': {'taux': 1.29, 'plafond': 'T1', 'description': 'Contribution équilibre général T1'},
            'CONTRIB_EQUILIBRE_GEN_T2': {'taux': 1.62, 'plafond': 'T2', 'description': 'Contribution équilibre général T2'},
            'PREVOYANCE': {'taux': 1.50, 'plafond': None, 'description': 'Prévoyance collective'}
        }
        

        if csv_path.exists():
            try:
                df = pl.read_csv(csv_path)

                # Charges salariales
                salarial_df = df.filter((pl.col("category") == "CHARGE") & (pl.col("type") == "SALARIAL"))
                self.COTISATIONS_SALARIALES = {}
                for row in salarial_df.iter_rows(named=True):
                    code = row["code"]
                    effective_date = row.get("effective_date", "JANUARY")

                    # Determine which year's rate to use
                    rate_year = self._get_rate_year(effective_date)
                    year_col = f"taux_{rate_year}"

                    # Check if column exists
                    if year_col not in df.columns:
                        print(f"Avertissement : aucun taux pour l'année {rate_year} dans le CSV pour {code}. Utilisation des valeurs par défaut.")
                        taux = default_salarial.get(code, {}).get("taux", 0)
                    else:
                        raw_val = row.get(year_col)
                        is_valid = raw_val is not None and not (isinstance(raw_val, float) and math.isnan(raw_val))
                        taux = float(raw_val) if is_valid and str(raw_val) != "" else default_salarial.get(code, {}).get("taux", 0)

                    plafond_val = row.get("plafond")
                    # Convert plafond to numeric if possible, otherwise keep as string
                    if plafond_val and plafond_val != "None" and str(plafond_val).strip():
                        try:
                            plafond_val = float(plafond_val)
                        except (ValueError, TypeError):
                            # Keep as string for T1/T2 type plafonds
                            pass
                    else:
                        plafond_val = None

                    self.COTISATIONS_SALARIALES[code] = {
                        "taux": taux,
                        "plafond": plafond_val,
                        "description": row.get("description"),
                        "effective_date": effective_date
                    }

                # Charges patronales
                patronal_df = df.filter((pl.col("category") == "CHARGE") & (pl.col("type") == "PATRONAL"))
                self.COTISATIONS_PATRONALES = {}
                for row in patronal_df.iter_rows(named=True):
                    code = row["code"]
                    effective_date = row.get("effective_date", "JANUARY")

                    # Determine which year's rate to use
                    rate_year = self._get_rate_year(effective_date)
                    year_col = f"taux_{rate_year}"

                    # Check if column exists
                    if year_col not in df.columns:
                        print(f"Avertissement : aucun taux pour l'année {rate_year} dans le CSV pour {code}. Utilisation des valeurs par défaut.")
                        taux = default_patronal.get(code, {}).get("taux", 0)
                    else:
                        raw_val = row.get(year_col)
                        is_valid = raw_val is not None and not (isinstance(raw_val, float) and math.isnan(raw_val))
                        taux = float(raw_val) if is_valid and str(raw_val) != "" else default_patronal.get(code, {}).get("taux", 0)

                    plafond_val = row.get("plafond")
                    # Convert plafond to numeric if possible, otherwise keep as string
                    if plafond_val and plafond_val != "None" and str(plafond_val).strip():
                        try:
                            plafond_val = float(plafond_val)
                        except (ValueError, TypeError):
                            # Keep as string for T1/T2 type plafonds
                            pass
                    else:
                        plafond_val = None

                    self.COTISATIONS_PATRONALES[code] = {
                        "taux": taux,
                        "plafond": plafond_val,
                        "description": row.get("description"),
                        "effective_date": effective_date
                    }

            except Exception as e:
                print(f"Erreur lors du chargement des taux depuis le CSV : {e}. Utilisation des valeurs par défaut.")
                self.COTISATIONS_SALARIALES = default_salarial
                self.COTISATIONS_PATRONALES = default_patronal
        else:
            # Créer le CSV par défaut et utiliser les valeurs par défaut
            self.COTISATIONS_SALARIALES = default_salarial
            self.COTISATIONS_PATRONALES = default_patronal
            constants = MonacoPayrollConstants(self.year)  # Génère le CSV par défaut

    
    @classmethod
    def calculate_base_tranches(cls, salaire_brut: float, year: int = None) -> Dict[str, float]:
        """Calculer les bases de cotisation par tranche"""
        constants = MonacoPayrollConstants(year)
        
        tranches = {
            'T1': min(salaire_brut, constants.PLAFOND_SS_T1),
            'T2': max(0, min(salaire_brut - constants.PLAFOND_SS_T1, 
                           constants.PLAFOND_SS_T2 - constants.PLAFOND_SS_T1)),
            'TOTAL': salaire_brut
        }
        
        return tranches
    
    def calculate_cotisations(self, salaire_brut: float,
                            type_cotisation: str = 'salariales',
                            cumul_brut_annuel: float = 0.0) -> Dict[str, float]:
        """
        Calculer les cotisations sociales with plafond-based tranches

        Args:
            salaire_brut: Salaire brut mensuel
            type_cotisation: 'salariales' ou 'patronales'
            cumul_brut_annuel: Cumul annuel brut before this period (for plafond calculations)

        Returns:
            Dictionnaire des cotisations par type
        """
        tranches = self.calculate_base_tranches(salaire_brut, self.year)

        cotisations = self.COTISATIONS_SALARIALES if type_cotisation.upper() == 'SALARIALES' else self.COTISATIONS_PATRONALES

        results = {}

        for key, params in cotisations.items():
            base = salaire_brut  # Par défaut, base = salaire total

            # Handle T1/T2 tranches (per-period tranches)
            if params['plafond'] == 'T1':
                base = tranches['T1']
            elif params['plafond'] == 'T2':
                base = tranches['T1'] + tranches['T2']
            # Handle numeric plafonds (annual cumulative tranches)
            elif params['plafond'] and isinstance(params['plafond'], (int, float)):
                plafond = float(params['plafond'])
                base = self._calculate_base_with_annual_plafond(
                    salaire_brut,
                    cumul_brut_annuel,
                    plafond
                )

            montant = round(base * params['taux'] / 100, 2)
            results[key] = montant

        return results

    def _calculate_base_with_annual_plafond(self, salaire_brut: float,
                                           cumul_brut_annuel: float,
                                           plafond: float) -> float:
        """
        Calculate the base amount for a charge with an annual plafond

        Args:
            salaire_brut: Current period's gross salary
            cumul_brut_annuel: Cumulative gross salary before this period
            plafond: Annual plafond for this tranche

        Returns:
            Amount of current salary subject to this charge
        """
        # Calculate new cumulative after this period
        new_cumul = cumul_brut_annuel + salaire_brut

        # If we haven't reached the plafond yet
        if cumul_brut_annuel >= plafond:
            # Already exceeded plafond, no charge applies
            return 0.0
        elif new_cumul <= plafond:
            # Entirely within plafond
            return salaire_brut
        else:
            # Partially exceeds plafond - only charge the portion within plafond
            return plafond - cumul_brut_annuel
    
    def calculate_total_charges(self, salaire_brut: float, cumul_brut_annuel: float = 0.0) -> Tuple[float, float, Dict]:
        """
        Calculer le total des charges salariales et patronales

        Args:
            salaire_brut: Salaire brut mensuel
            cumul_brut_annuel: Cumul annuel brut before this period

        Returns:
            Tuple (total_salarial, total_patronal, details)
        """
        charges_salariales = self.calculate_cotisations(salaire_brut, 'salariales', cumul_brut_annuel)
        charges_patronales = self.calculate_cotisations(salaire_brut, 'patronales', cumul_brut_annuel)

        total_salarial = sum(charges_salariales.values())
        total_patronal = sum(charges_patronales.values())

        details = {
            'charges_salariales': charges_salariales,
            'charges_patronales': charges_patronales,
            'total_salarial': total_salarial,
            'total_patronal': total_patronal,
            'cout_total': salaire_brut + total_patronal,
            'year': self.year
        }

        return total_salarial, total_patronal, details

class CalculateurPaieMonaco:
    """Calculateur principal de paie pour Monaco"""

    def __init__(self, year: int = None, month: int = None):
        """
        Initialize calculator for a specific year and month

        Args:
            year: Year for calculations
            month: Month for calculations (determines rate effective dates)
        """
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month
        self.year = year
        self.month = month
        self.constants = MonacoPayrollConstants(year)
        self.charges_calculator = ChargesSocialesMonaco(year, month)
    
    def calculate_hourly_rate(self, salaire_base: float, base_heures: float = None) -> float:
        """Calculer le taux horaire"""
        if base_heures is None:
            base_heures = self.constants.BASE_HEURES_LEGALE
        if base_heures == 0:
            return 0
        return salaire_base / base_heures
    
    def calculate_overtime(self, hourly_rate: float, 
                          heures_sup_125: float = 0, 
                          heures_sup_150: float = 0) -> float:
        """Calculer les heures supplémentaires"""
        montant_125 = heures_sup_125 * hourly_rate * self.constants.TAUX_HS_125
        montant_150 = heures_sup_150 * hourly_rate * self.constants.TAUX_HS_150
        return round(montant_125 + montant_150, 2)
    
    def calculate_absences(self, hourly_rate: float, heures_absence: float,
                          type_absence: str = 'non_payee') -> float:
        """
        Calculer les retenues pour absence
        
        Args:
            hourly_rate: Taux horaire
            heures_absence: Nombre d'heures d'absence
            type_absence: Type d'absence (maladie, conges_sans_solde, etc.)
        """
        if type_absence == 'maladie_maintenue':
            return 0  # Pas de retenue si maintien de salaire
        elif type_absence == 'conges_payes':
            return 0  # Les congés payés sont calculés séparément
        else:
            return round(heures_absence * hourly_rate, 2)
    
    def calculate_prime(self, prime_amount: float, type_prime: str) -> Dict:
        """
        Calculer les primes et leur traitement social/fiscal
        
        Args:
            prime_amount: Montant de la prime
            type_prime: Type de prime (performance, anciennete, 13eme_mois, etc.)
        """
        # Certaines primes peuvent avoir des traitements spéciaux
        soumis_cotisations = True
        
        if type_prime == 'transport':
            # Exonération partielle possible
            soumis_cotisations = prime_amount > 50  # Exemple de seuil
        
        return {
            'montant': prime_amount,
            'type': type_prime,
            'soumis_cotisations': soumis_cotisations
        }
    
    def calculate_avantages_nature(self, logement: float = 0, 
                                  transport: float = 0,
                                  autres: float = 0) -> float:
        """
        Calculer les avantages en nature
        Ces montants sont ajoutés au brut pour les cotisations
        """
        return logement + transport + autres
    
    def calculate_tickets_restaurant(self, nombre_tickets: int) -> Dict:
        """
        Calculer la participation tickets restaurant
        
        Returns:
            Dict avec part_salariale et part_patronale
        """
        valeur_totale = nombre_tickets * self.constants.TICKET_RESTO_VALEUR
        part_patronale = round(valeur_totale * self.constants.TICKET_RESTO_PART_PATRONALE, 2)
        part_salariale = round(valeur_totale * self.constants.TICKET_RESTO_PART_SALARIALE, 2)
        
        return {
            'valeur_totale': valeur_totale,
            'part_patronale': part_patronale,
            'part_salariale': part_salariale,
            'nombre': nombre_tickets,
            'valeur_unitaire': self.constants.TICKET_RESTO_VALEUR
        }
    
    def calculate_conges_payes(self, salaire_base: float, jours_pris: float) -> float:
        """
        Calculer l'indemnité de congés payés
        Méthode du maintien de salaire (la plus favorable généralement)
        """
        # Monaco: 2.5 jours ouvrables par mois, soit 30 jours/an
        # Calcul simplifié: salaire journalier x jours pris
        salaire_journalier = salaire_base / 30  # Approximation mensuelle
        return round(salaire_journalier * jours_pris, 2)
    
    def calculate_provision_cp(self, salaire_base: float, jours_acquis: float) -> float:
        """Calculer la provision pour congés payés"""
        salaire_journalier = salaire_base / 30
        provision = salaire_journalier * jours_acquis * 1.1  # +10% pour charges
        return round(provision, 2)
    
    def process_employee_payslip(self, employee_data: Dict,
                                processing_date: date = None,
                                cumul_brut_annuel: float = 0.0) -> Dict:
        """
        Traiter une fiche de paie complète pour un employé

        Args:
            employee_data: Dictionnaire contenant toutes les données de l'employé
            processing_date: Date de traitement (pour déterminer l'année des taux)
            cumul_brut_annuel: Cumul annuel brut before this period (for plafond calculations)

        Returns:
            Dictionnaire avec tous les calculs de paie
        """
        # Determine the year and month for rates (from processing date or payslip period)
        if processing_date:
            calc_year = processing_date.year
            calc_month = processing_date.month
        elif 'period_year' in employee_data and 'period_month' in employee_data:
            calc_year = employee_data['period_year']
            calc_month = employee_data['period_month']
        else:
            calc_year = self.year
            calc_month = self.month

        # Reinitialize if year or month is different
        if calc_year != self.year or calc_month != self.month:
            self.year = calc_year
            self.month = calc_month
            self.constants = MonacoPayrollConstants(calc_year)
            self.charges_calculator = ChargesSocialesMonaco(calc_year, calc_month)
        
        # Extraction des données
        salaire_base = employee_data.get('salaire_base', 0)
        base_heures = employee_data.get('base_heures', self.constants.BASE_HEURES_LEGALE)
        heures_sup_125 = employee_data.get('heures_sup_125', 0)
        heures_sup_150 = employee_data.get('heures_sup_150', 0)
        heures_absence = employee_data.get('heures_absence', 0)
        type_absence = employee_data.get('type_absence', 'non_payee')
        prime = employee_data.get('prime', 0)
        type_prime = employee_data.get('type_prime', 'performance')
        prime_non_cotisable = employee_data.get('prime_non_cotisable', 0)
        heures_jours_feries = employee_data.get('heures_jours_feries', 0)
        heures_dimanche = employee_data.get('heures_dimanche', 0)
        tickets_restaurant = employee_data.get('tickets_restaurant', 0)
        avantage_logement = employee_data.get('avantage_logement', 0)
        avantage_transport = employee_data.get('avantage_transport', 0)
        jours_conges_pris = employee_data.get('jours_conges_pris', 0)
        
        # Calculs
        hourly_rate = self.calculate_hourly_rate(salaire_base, base_heures)
        
        # Heures supplémentaires
        montant_heures_sup = self.calculate_overtime(hourly_rate, heures_sup_125, heures_sup_150)
        
        # Jours fériés et dimanches (majorés à 100% généralement)
        montant_jours_feries = round(heures_jours_feries * hourly_rate * 2, 2)
        montant_dimanches = round(heures_dimanche * hourly_rate * 2, 2)
        
        # Absences
        retenue_absence = self.calculate_absences(hourly_rate, heures_absence, type_absence)
        
        # Primes
        prime_details = self.calculate_prime(prime, type_prime)
        
        # Avantages en nature
        total_avantages_nature = self.calculate_avantages_nature(
            avantage_logement, avantage_transport
        )
        
        # Tickets restaurant
        tickets_details = self.calculate_tickets_restaurant(tickets_restaurant)
        
        # Congés payés
        indemnite_cp = self.calculate_conges_payes(salaire_base, jours_conges_pris)
        
        # Calcul du salaire brut
        salaire_brut = (
            salaire_base +
            montant_heures_sup +
            montant_jours_feries +
            montant_dimanches +
            prime_details['montant'] +
            total_avantages_nature +
            indemnite_cp -
            retenue_absence
        )

        # Automatic 5% bonus for employees earning between SMIC and 1.55x SMIC (exempt from charges)
        smic_monthly = self.constants.SMIC_HORAIRE * self.constants.BASE_HEURES_LEGALE
        smic_threshold_max = smic_monthly * 1.55

        if smic_monthly <= salaire_brut <= smic_threshold_max:
            bonus_low_wage = round(salaire_brut * 0.05, 2)
            prime_non_cotisable += bonus_low_wage

        # Calcul des charges sociales
        charges_sal, charges_pat, charges_details = self.charges_calculator.calculate_total_charges(
            salaire_brut, cumul_brut_annuel
        )
        
        # Ajout de la retenue tickets restaurant
        charges_sal += tickets_details.get('part_salariale', 0)

        # Salaire net (brut - charges + prime non cotisable)
        salaire_net = salaire_brut - charges_sal + prime_non_cotisable

        # Coût total employeur (includes prime_non_cotisable as it's paid by employer)
        cout_total = salaire_brut + charges_pat + tickets_details.get('part_patronale', 0) + prime_non_cotisable
        
        return {
            'matricule': employee_data.get('matricule'),
            'nom': employee_data.get('nom'),
            'prenom': employee_data.get('prenom'),
            
            # Éléments de salaire
            'salaire_base': salaire_base,
            'taux_horaire': hourly_rate,
            'heures_travaillees': base_heures,
            'base_heures': base_heures,
            'heures_payees': base_heures,
            
            # Heures supplémentaires et majorations
            'heures_sup_125': heures_sup_125,
            'montant_hs_125': round(heures_sup_125 * hourly_rate * 1.25, 2),
            'heures_sup_150': heures_sup_150,
            'montant_hs_150': round(heures_sup_150 * hourly_rate * 1.50, 2),
            'total_heures_sup': montant_heures_sup,
            
            # Jours spéciaux
            'heures_jours_feries': heures_jours_feries,
            'montant_jours_feries': montant_jours_feries,
            'heures_dimanche': heures_dimanche,
            'montant_dimanches': montant_dimanches,
            
            # Absences
            'heures_absence': heures_absence,
            'type_absence': type_absence,
            'retenue_absence': retenue_absence,
            
            # Primes et avantages
            'prime': prime,
            'type_prime': type_prime,
            'prime_non_cotisable': prime_non_cotisable,
            'avantages_nature': total_avantages_nature,
            
            # Tickets restaurant
            'tickets_restaurant': tickets_restaurant,
            'tickets_restaurant_details': tickets_details,
            
            # Congés payés
            'jours_cp_pris': jours_conges_pris,
            'indemnite_cp': indemnite_cp,
            
            # Totaux
            'salaire_brut': round(salaire_brut, 2),
            'total_charges_salariales': round(charges_sal, 2),
            'total_charges_patronales': round(charges_pat, 2),
            'salaire_net': round(salaire_net, 2),
            'cout_total_employeur': round(cout_total, 2),
            
            # Détails des charges
            'details_charges': charges_details,
            
            # Year for rates used
            'calculation_year': calc_year
        }

class ValidateurPaieMonaco:
    """Validateur et détecteur de cas particuliers"""
    
    @staticmethod
    def validate_payslip(payslip_data: Dict, year: int = None) -> Tuple[bool, List[str]]:
        """
        Valider une fiche de paie et détecter les anomalies
        
        Returns:
            Tuple (is_valid, list_of_issues)
        """
        if year is None:
            year = payslip_data.get('calculation_year', datetime.now().year)
        
        constants = MonacoPayrollConstants(year)
        issues = []
        
        # Vérifications de base
        if payslip_data.get('salaire_brut', 0) < constants.SMIC_HORAIRE * constants.BASE_HEURES_LEGALE:
            issues.append("Salaire inférieur au SMIC")
        
        if payslip_data.get('salaire_brut', 0) > 100000:
            issues.append("Salaire très élevé - vérification recommandée")
        
        # Heures supplémentaires excessives
        total_hs = payslip_data.get('heures_sup_125', 0) + payslip_data.get('heures_sup_150', 0)
        if total_hs > 48:  # Limite légale mensuelle
            issues.append(f"Heures supplémentaires excessives: {total_hs}h")
        
        # Absences importantes
        if payslip_data.get('heures_absence', 0) > 80:
            issues.append("Nombre d'heures d'absence élevé")
        
        # Cohérence des charges
        salaire_brut = payslip_data.get('salaire_brut', 0)
        if salaire_brut > 0:
            ratio_charges = payslip_data.get('total_charges_salariales', 0) / salaire_brut
            if ratio_charges < 0.10 or ratio_charges > 0.50:
                issues.append(f"Ratio charges salariales anormal: {ratio_charges:.1%}")
        else:
            issues.append("Salaire brut nul ou négatif")
        
        # Cas de sortie
        if payslip_data.get('date_sortie'):
            issues.append("Salarié sortant - calcul au prorata à vérifier")
        
        is_valid = len(issues) == 0
        
        return is_valid, issues

class GestionnaireCongesPayes:
    """Gestionnaire des congés payés selon la législation monégasque"""
    
    JOURS_ACQUIS_PAR_MOIS = 2.5  # 2.5 jours ouvrables par mois
    
    @classmethod
    def calculate_droits_cp(cls, date_entree: date, date_calcul: date) -> Dict:
        """
        Calculer les droits à congés payés
        
        Returns:
            Dict avec jours_acquis, jours_pris, jours_restants
        """
        # Calcul des mois travaillés
        mois_travailles = (date_calcul.year - date_entree.year) * 12 + (date_calcul.month - date_entree.month)
        
        # Droits acquis
        jours_acquis = mois_travailles * cls.JOURS_ACQUIS_PAR_MOIS
        
        return {
            'mois_travailles': mois_travailles,
            'jours_acquis': jours_acquis,
            'jours_maximum_annuel': 30  # Maximum légal à Monaco
        }
    
    @classmethod
    def calculate_provision_cp_global(cls, employees_df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculer la provision globale pour congés payés
        
        Args:
            employees_df: Polars DataFrame avec les données des employés
            
        Returns:
            Polars DataFrame avec le calcul des provisions
        """
        provisions = []
        
        for employee in employees_df.iter_rows(named=True):
            salaire_base = employee.get('salaire_base', 0)
            jours_acquis_non_pris = employee.get('cp_acquis', 0) - employee.get('cp_pris', 0)
            
            # Provision = (salaire journalier * jours restants) * 1.45 (charges comprises)
            salaire_journalier = salaire_base / 30
            provision = salaire_journalier * jours_acquis_non_pris * 1.45
            
            provisions.append({
                'matricule': employee.get('matricule'),
                'nom': employee.get('nom'),
                'prenom': employee.get('prenom'),
                'jours_acquis': employee.get('cp_acquis', 0),
                'jours_pris': employee.get('cp_pris', 0),
                'jours_restants': jours_acquis_non_pris,
                'salaire_base': salaire_base,
                'provision_cp': round(provision, 2)
            })
        
        return pl.DataFrame(provisions)
    
# Utility functions for managing rates
def add_year_to_rates_csv(year: int):
    """Add a new year column to the existing rates CSV"""
    csv_path = Path("data/config") / "payroll_rates.csv"
    
    if not csv_path.exists():
        # Create default CSV first
        constants = MonacoPayrollConstants(year)
        return
    
    df = pl.read_csv(csv_path)
    new_col = f'taux_{year}'
    
    if new_col in df.columns:
        print(f"Year {year} already exists in rates CSV")
        return
    
    # Copy rates from the most recent year
    existing_years = [col for col in df.columns if col.startswith('taux_')]
    if existing_years:
        latest_year = sorted(existing_years)[-1]
        df = df.with_columns(pl.col(latest_year).alias(new_col))
    else:
        # Use defaults
        df = df.with_columns(pl.col('taux_2024').alias(new_col))  # Assuming 2024 is base year
    
    df.write_csv(csv_path)
    print(f"Added year {year} to rates CSV with rates copied from previous year")

def update_rate_in_csv(year: int, category: str, rate_type: str, code: str, new_rate: float):
    """
    Update a specific rate in the CSV
    
    Args:
        year: The year to update
        category: 'CHARGE' or 'CONSTANT'
        rate_type: 'SALARIAL' or 'PATRONAL' (for charges only)
        code: The code of the rate (e.g., 'CAR', 'CCSS')
        new_rate: The new rate value
    """
    csv_path = Path("data/config") / "payroll_rates.csv"
    
    if not csv_path.exists():
        print("Rates CSV does not exist. Creating default...")
        constants = MonacoPayrollConstants(year)
        
    df = pl.read_csv(csv_path)
    year_col = f'taux_{year}'
    
    if year_col not in df.columns:
        print(f"Adding year {year} to CSV...")
        add_year_to_rates_csv(year)
        df = pl.read_csv(csv_path)
    
    # Find the row to update
    if category == 'CONSTANT':
        mask = (df['category'] == category) & (df['code'] == code)
    else:  # CHARGE
        mask = (df['category'] == category) & (df['type'] == rate_type) & (df['code'] == code)
    
    if mask.any():
        df = df.with_columns(pl.when(mask).then(new_rate).otherwise(pl.col(year_col)).alias(year_col))
        df.write_csv(csv_path)
        print(f"Updated {code} rate to {new_rate} for year {year}")
    else:
        print(f"Could not find {category} {rate_type} {code} in CSV")

def display_rates_for_year(year: int):
    """Display all rates for a specific year"""
    csv_path = Path("data/config") / "payroll_rates.csv"
    
    if not csv_path.exists():
        print("Rates CSV does not exist")
        return
    
    df = pl.read_csv(csv_path)
    year_col = f'taux_{year}'
    
    if year_col not in df.columns:
        print(f"No rates for year {year}")
        return
    
    print(f"\n=== RATES FOR {year} ===")
    
    # Display constants
    print("\nCONSTANTS:")
    constants_df = df.filter(pl.col('category') == 'CONSTANT')
    for row in constants_df.iter_rows(named=True):
        print(f"  {row['code']}: {row[year_col]} - {row['description']}")
    
    # Display salarial charges
    print("\nSALARIAL CHARGES:")
    salarial_df = df.filter((pl.col('category') == 'CHARGE') & (pl.col('type') == 'SALARIAL'))
    for row in salarial_df.iter_rows(named=True):
        plafond_str = f" (Plafond: {row['plafond']})" if row['plafond'] != 'None' else ""
        print(f"  {row['code']}: {row[year_col]}%{plafond_str} - {row['description']}")
    
    # Display patronal charges
    print("\nPATRONAL CHARGES:")
    patronal_df = df.filter((pl.col('category') == 'CHARGE') & (pl.col('type') == 'PATRONAL'))
    for row in patronal_df.iter_rows(named=True):
        plafond_str = f" (Plafond: {row['plafond']})" if row['plafond'] != 'None' else ""
        print(f"  {row['code']}: {row[year_col]}%{plafond_str} - {row['description']}")

# Example usage
if __name__ == "__main__":
    # Create or ensure rates CSV exists
    csv_path = Path("data/config") / "payroll_rates.csv"
    if not csv_path.exists():
        print("Creating default rates CSV...")
        constants = MonacoPayrollConstants(2024)
    
    # Display current rates
    display_rates_for_year(2024)
    display_rates_for_year(2025)
    
    # Example: Update CAR rate for 2025
    print("\n=== Updating CAR salarial rate to 6.90% for 2025 ===")
    update_rate_in_csv(2025, 'CHARGE', 'SALARIAL', 'CAR', 6.90)
    
    # Test with an employee for 2024
    print("\n=== TESTING 2024 CALCULATION ===")
    calculateur_2024 = CalculateurPaieMonaco(year=2024)
    
    employee_test = {
        'matricule': 'S000000001',
        'nom': 'DUPONT',
        'prenom': 'Jean',
        'salaire_base': 3500.00,
        'base_heures': 169,
        'heures_sup_125': 10,
        'heures_sup_150': 5,
        'prime': 500,
        'type_prime': 'performance',
        'tickets_restaurant': 20,
        'avantage_logement': 0,
        'avantage_transport': 50,
        'heures_absence': 0,
        'jours_conges_pris': 2,
        'period_year': 2024
    }
    
    resultat_2024 = calculateur_2024.process_employee_payslip(employee_test)
    
    print(f"Employé: {resultat_2024['nom']} {resultat_2024['prenom']}")
    print(f"Année de calcul: {resultat_2024['calculation_year']}")
    print(f"SALAIRE BRUT: {resultat_2024['salaire_brut']:.2f} €")
    print(f"Charges salariales: -{resultat_2024['total_charges_salariales']:.2f} €")
    print(f"  dont CAR: {resultat_2024['details_charges']['charges_salariales']['CAR']:.2f} €")
    print(f"SALAIRE NET: {resultat_2024['salaire_net']:.2f} €")
    
    # Test with 2025 (with updated CAR rate)
    print("\n=== TESTING 2025 CALCULATION (with updated CAR) ===")
    calculateur_2025 = CalculateurPaieMonaco(year=2025)
    employee_test['period_year'] = 2025
    resultat_2025 = calculateur_2025.process_employee_payslip(employee_test)
    
    print(f"Employé: {resultat_2025['nom']} {resultat_2025['prenom']}")
    print(f"Année de calcul: {resultat_2025['calculation_year']}")
    print(f"SALAIRE BRUT: {resultat_2025['salaire_brut']:.2f} €")
    print(f"Charges salariales: -{resultat_2025['total_charges_salariales']:.2f} €")
    print(f"  dont CAR (6.90%): {resultat_2025['details_charges']['charges_salariales']['CAR']:.2f} €")
    print(f"SALAIRE NET: {resultat_2025['salaire_net']:.2f} €")