"""
Module de calculs de paie spécifiques à Monaco
===============================================
Includes all Monaco-specific payroll calculations, social charges, and tax rules
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd

@dataclass
class MonacoPayrollConstants:
    """Constantes de paie pour Monaco (2024)"""
    
    # Plafonds mensuels de la Sécurité Sociale
    PLAFOND_SS_T1 = 3428.00  # Tranche 1
    PLAFOND_SS_T2 = 13712.00  # Tranche 2 (4 x plafond T1)
    
    # Base légale d'heures mensuelles
    BASE_HEURES_LEGALE = 169.00
    
    # SMIC Monaco
    SMIC_HORAIRE = 11.65
    
    # Taux horaires supplémentaires
    TAUX_HS_125 = 1.25  # 25% de majoration
    TAUX_HS_150 = 1.50  # 50% de majoration
    
    # Tickets restaurant
    TICKET_RESTO_VALEUR = 9.00
    TICKET_RESTO_PART_PATRONALE = 0.60  # 60% employeur
    TICKET_RESTO_PART_SALARIALE = 0.40  # 40% salarié

class ChargesSocialesMonaco:
    """Calcul des charges sociales selon la législation monégasque"""
    
    # Taux de cotisations salariales (en %)
    COTISATIONS_SALARIALES = {
        # CAR - Caisse Autonome des Retraites
        'CAR': {
            'taux': 6.85,
            'plafond': None,  # Pas de plafond
            'description': 'Caisse Autonome des Retraites'
        },
        
        # CCSS - Caisse de Compensation des Services Sociaux
        'CCSS': {
            'taux': 14.75,
            'plafond': None,
            'description': 'Caisse de Compensation des Services Sociaux'
        },
        
        # Assurance chômage
        'ASSEDIC_T1': {
            'taux': 2.40,
            'plafond': 'T1',
            'description': 'Assurance chômage Tranche 1'
        },
        'ASSEDIC_T2': {
            'taux': 2.40,
            'plafond': 'T2',
            'description': 'Assurance chômage Tranche 2'
        },
        
        # Retraite complémentaire
        'RETRAITE_COMP_T1': {
            'taux': 3.15,
            'plafond': 'T1',
            'description': 'Retraite complémentaire Tranche 1'
        },
        'RETRAITE_COMP_T2': {
            'taux': 8.64,
            'plafond': 'T2',
            'description': 'Retraite complémentaire Tranche 2'
        },
        
        # Contribution d'équilibre
        'CONTRIB_EQUILIBRE_TECH': {
            'taux': 0.14,
            'plafond': None,
            'description': 'Contribution équilibre technique'
        },
        'CONTRIB_EQUILIBRE_GEN_T1': {
            'taux': 0.86,
            'plafond': 'T1',
            'description': 'Contribution équilibre général T1'
        },
        'CONTRIB_EQUILIBRE_GEN_T2': {
            'taux': 1.08,
            'plafond': 'T2',
            'description': 'Contribution équilibre général T2'
        }
    }
    
    # Taux de cotisations patronales (en %)
    COTISATIONS_PATRONALES = {
        # CAR
        'CAR': {
            'taux': 8.35,
            'plafond': None,
            'description': 'Caisse Autonome des Retraites'
        },
        
        # CMRC - Caisse Monégasque de Retraite Complémentaire
        'CMRC': {
            'taux': 5.22,
            'plafond': None,
            'description': 'Caisse Monégasque de Retraite Complémentaire'
        },
        
        # Assurance chômage
        'ASSEDIC_T1': {
            'taux': 4.05,
            'plafond': 'T1',
            'description': 'Assurance chômage Tranche 1'
        },
        'ASSEDIC_T2': {
            'taux': 4.05,
            'plafond': 'T2',
            'description': 'Assurance chômage Tranche 2'
        },
        
        # Retraite complémentaire
        'RETRAITE_COMP_T1': {
            'taux': 4.72,
            'plafond': 'T1',
            'description': 'Retraite complémentaire Tranche 1'
        },
        'RETRAITE_COMP_T2': {
            'taux': 12.95,
            'plafond': 'T2',
            'description': 'Retraite complémentaire Tranche 2'
        },
        
        # Contribution d'équilibre
        'CONTRIB_EQUILIBRE_TECH': {
            'taux': 0.21,
            'plafond': None,
            'description': 'Contribution équilibre technique'
        },
        'CONTRIB_EQUILIBRE_GEN_T1': {
            'taux': 1.29,
            'plafond': 'T1',
            'description': 'Contribution équilibre général T1'
        },
        'CONTRIB_EQUILIBRE_GEN_T2': {
            'taux': 1.62,
            'plafond': 'T2',
            'description': 'Contribution équilibre général T2'
        },
        
        # Prévoyance (variable selon convention)
        'PREVOYANCE': {
            'taux': 1.50,  # Taux moyen, peut varier
            'plafond': None,
            'description': 'Prévoyance collective'
        }
    }
    
    @classmethod
    def calculate_base_tranches(cls, salaire_brut: float) -> Dict[str, float]:
        """Calculer les bases de cotisation par tranche"""
        constants = MonacoPayrollConstants()
        
        tranches = {
            'T1': min(salaire_brut, constants.PLAFOND_SS_T1),
            'T2': max(0, min(salaire_brut - constants.PLAFOND_SS_T1, 
                           constants.PLAFOND_SS_T2 - constants.PLAFOND_SS_T1)),
            'TOTAL': salaire_brut
        }
        
        return tranches
    
    @classmethod
    def calculate_cotisations(cls, salaire_brut: float, 
                            type_cotisation: str = 'salariales') -> Dict[str, float]:
        """
        Calculer les cotisations sociales
        
        Args:
            salaire_brut: Salaire brut mensuel
            type_cotisation: 'salariales' ou 'patronales'
        
        Returns:
            Dictionnaire des cotisations par type
        """
        tranches = cls.calculate_base_tranches(salaire_brut)
        
        cotisations = type_cotisation.upper() == 'SALARIALES' and cls.COTISATIONS_SALARIALES or cls.COTISATIONS_PATRONALES
        
        results = {}
        
        for key, params in cotisations.items():
            base = salaire_brut  # Par défaut, base = salaire total
            
            if params['plafond'] == 'T1':
                base = tranches['T1']
            elif params['plafond'] == 'T2':
                base = tranches['T1'] + tranches['T2']
            
            montant = round(base * params['taux'] / 100, 2)
            results[key] = montant
        
        return results
    
    @classmethod
    def calculate_total_charges(cls, salaire_brut: float) -> Tuple[float, float, Dict]:
        """
        Calculer le total des charges salariales et patronales
        
        Returns:
            Tuple (total_salarial, total_patronal, details)
        """
        charges_salariales = cls.calculate_cotisations(salaire_brut, 'salariales')
        charges_patronales = cls.calculate_cotisations(salaire_brut, 'patronales')
        
        total_salarial = sum(charges_salariales.values())
        total_patronal = sum(charges_patronales.values())
        
        details = {
            'charges_salariales': charges_salariales,
            'charges_patronales': charges_patronales,
            'total_salarial': total_salarial,
            'total_patronal': total_patronal,
            'cout_total': salaire_brut + total_patronal
        }
        
        return total_salarial, total_patronal, details

class CalculateurPaieMonaco:
    """Calculateur principal de paie pour Monaco"""
    
    def __init__(self):
        self.constants = MonacoPayrollConstants()
        self.charges_calculator = ChargesSocialesMonaco()
    
    def calculate_hourly_rate(self, salaire_base: float, base_heures: float = 169) -> float:
        """Calculer le taux horaire"""
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
            'nombre': nombre_tickets
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
    
    def process_employee_payslip(self, employee_data: Dict) -> Dict:
        """
        Traiter une fiche de paie complète pour un employé
        
        Args:
            employee_data: Dictionnaire contenant toutes les données de l'employé
        
        Returns:
            Dictionnaire avec tous les calculs de paie
        """
        # Extraction des données
        salaire_base = employee_data.get('salaire_base', 0)
        base_heures = employee_data.get('base_heures', self.constants.BASE_HEURES_LEGALE)
        heures_sup_125 = employee_data.get('heures_sup_125', 0)
        heures_sup_150 = employee_data.get('heures_sup_150', 0)
        heures_absence = employee_data.get('heures_absence', 0)
        type_absence = employee_data.get('type_absence', 'non_payee')
        prime = employee_data.get('prime', 0)
        type_prime = employee_data.get('type_prime', 'performance')
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
        
        # Calcul des charges sociales
        charges_sal, charges_pat, charges_details = self.charges_calculator.calculate_total_charges(salaire_brut)
        
        # Ajout de la retenue tickets restaurant
        charges_sal += tickets_details.get('part_salariale', 0)
        
        # Salaire net
        salaire_net = salaire_brut - charges_sal
        
        # Coût total employeur
        cout_total = salaire_brut + charges_pat + tickets_details.get('part_patronale', 0)
        
        return {
            'matricule': employee_data.get('matricule'),
            'nom': employee_data.get('nom'),
            'prenom': employee_data.get('prenom'),
            
            # Éléments de salaire
            'salaire_base': salaire_base,
            'taux_horaire': hourly_rate,
            'heures_travaillees': base_heures,
            
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
            'avantages_nature': total_avantages_nature,
            
            # Tickets restaurant
            'tickets_restaurant': tickets_details,
            
            # Congés payés
            'jours_conges_pris': jours_conges_pris,
            'indemnite_conges_payes': indemnite_cp,
            
            # Totaux
            'salaire_brut': round(salaire_brut, 2),
            'total_charges_salariales': round(charges_sal, 2),
            'total_charges_patronales': round(charges_pat, 2),
            'salaire_net': round(salaire_net, 2),
            'cout_total_employeur': round(cout_total, 2),
            
            # Détails des charges
            'details_charges': charges_details
        }

class ValidateurPaieMonaco:
    """Validateur et détecteur de cas particuliers"""
    
    @staticmethod
    def validate_payslip(payslip_data: Dict) -> Tuple[bool, List[str]]:
        """
        Valider une fiche de paie et détecter les anomalies
        
        Returns:
            Tuple (is_valid, list_of_issues)
        """
        issues = []
        
        # Vérifications de base
        if payslip_data.get('salaire_brut', 0) < MonacoPayrollConstants.SMIC_HORAIRE * 169:
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
        ratio_charges = payslip_data.get('total_charges_salariales', 0) / payslip_data.get('salaire_brut', 1)
        if ratio_charges < 0.10 or ratio_charges > 0.50:
            issues.append(f"Ratio charges salariales anormal: {ratio_charges:.1%}")
        
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
    def calculate_provision_cp_global(cls, employees_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculer la provision globale pour congés payés
        
        Args:
            employees_df: DataFrame avec les données des employés
            
        Returns:
            DataFrame avec le calcul des provisions
        """
        provisions = []
        
        for _, employee in employees_df.iterrows():
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
        
        return pd.DataFrame(provisions)

# Exemple d'utilisation
if __name__ == "__main__":
    # Test avec un employé exemple
    calculateur = CalculateurPaieMonaco()
    
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
        'jours_conges_pris': 2
    }
    
    resultat = calculateur.process_employee_payslip(employee_test)
    
    print("=== BULLETIN DE PAIE TEST ===")
    print(f"Employé: {resultat['nom']} {resultat['prenom']}")
    print(f"Salaire de base: {resultat['salaire_base']:.2f} €")
    print(f"Heures supplémentaires: {resultat['total_heures_sup']:.2f} €")
    print(f"Prime: {resultat['prime']:.2f} €")
    print(f"SALAIRE BRUT: {resultat['salaire_brut']:.2f} €")
    print(f"Charges salariales: -{resultat['total_charges_salariales']:.2f} €")
    print(f"SALAIRE NET: {resultat['salaire_net']:.2f} €")
    print(f"Charges patronales: {resultat['total_charges_patronales']:.2f} €")
    print(f"Coût total employeur: {resultat['cout_total_employeur']:.2f} €")
    
    # Validation
    validateur = ValidateurPaieMonaco()
    is_valid, issues = validateur.validate_payslip(resultat)
    
    if not is_valid:
        print("\n⚠️ Anomalies détectées:")
        for issue in issues:
            print(f"  - {issue}")
