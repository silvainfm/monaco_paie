"""
DSM XML Generator for Monaco Caisses Sociales
==============================================
Generates XML declarations for Monaco social security authorities
Format: DSM 2.0 (Déclaration Sociale Monaco)
"""

from datetime import datetime
from typing import Dict, List, Optional
import polars as pl
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
import io


class DSMXMLGenerator:
    """Generator for Monaco DSM XML declarations"""

    # DTD and schema URLs
    DTD_PUBLIC_ID = "-//CSM//DSM 2.0//FR"
    DTD_SYSTEM_ID = "http://www.caisses-sociales.mc/DSM/2.0/dsm.dtd"
    NAMESPACE = "http://www.caisses-sociales.mc/DSM/2.0"
    XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
    SCHEMA_LOCATION = "http://www.caisses-sociales.mc/DSM/2.0 http://www.caisses-sociales.mc/DSM/2.0/dsm.xsd"

    def __init__(self, employer_number: str, plafond_ss_t1: float = 3428.00):
        """
        Initialize DSM XML generator

        Args:
            employer_number: Employer registration number with Caisses Sociales
            plafond_ss_t1: Social security ceiling Tranche 1 (default: 3428.00)
        """
        self.employer_number = employer_number
        self.plafond_ss_t1 = plafond_ss_t1

    def calculate_contribution_bases(self, salaire_brut: float) -> Dict[str, float]:
        """
        Calculate contribution bases for Monaco social charges

        Args:
            salaire_brut: Gross salary

        Returns:
            Dictionary with base amounts for each contribution type
        """
        # baseCCSS = total gross salary
        base_ccss = salaire_brut

        # baseCAR = capped at plafond T2 (but usually equals gross for most salaries)
        # In practice, CAR has its own ceiling
        base_car = salaire_brut

        # baseCMRCTA = Tranche A (up to plafond T1)
        base_cmrc_ta = min(salaire_brut, self.plafond_ss_t1)

        # baseCMRCTB = Tranche B (amount above plafond T1)
        base_cmrc_tb = max(0, salaire_brut - self.plafond_ss_t1)

        # Assurance Chomage = total gross salary
        base_ac = salaire_brut

        return {
            'baseCCSS': round(base_ccss, 2),
            'baseCAR': round(base_car, 2),
            'baseCMRCTA': round(base_cmrc_ta, 2),
            'baseCMRCTB': round(base_cmrc_tb, 2),
            'baseAssuranceChomage': round(base_ac, 2)
        }

    def generate_dsm_xml(self, employees_df: pl.DataFrame, period: str,
                         output_path: Optional[str] = None) -> io.BytesIO:
        """
        Generate DSM XML declaration

        Args:
            employees_df: Polars DataFrame with employee payroll data
            period: Period in format "YYYY-MM"
            output_path: Optional file path to save XML

        Returns:
            BytesIO buffer containing XML content
        """
        # Create root element with namespaces
        root = ET.Element('declaration')
        root.set('xmlns', self.NAMESPACE)
        root.set('xmlns:xsi', self.XSI_NAMESPACE)
        root.set('xsi:schemaLocation', self.SCHEMA_LOCATION)

        # Employer number
        employeur = ET.SubElement(root, 'employeur')
        employeur.text = str(self.employer_number)

        # Period (YYYY-MM format)
        periode = ET.SubElement(root, 'periode')
        periode.text = period

        # Effectif (employees section)
        effectif = ET.SubElement(root, 'effectif')

        # Initialize totals for assiettes (contribution bases summary)
        totals = {
            'CCSS': 0.0,
            'CAR': 0.0,
            'CMRCTA': 0.0,
            'CMRCTB': 0.0,
            'AssuranceChomage': 0.0
        }

        # Process each employee
        for employee in employees_df.to_dicts():
            salarie = self._create_employee_element(employee, totals)
            effectif.append(salarie)

        # Assiettes (contribution bases summary)
        assiettes = ET.SubElement(root, 'assiettes')
        for key, value in totals.items():
            elem = ET.SubElement(assiettes, key)
            elem.text = str(int(round(value, 0)))  # Round to integer for summary

        # Create XML string with proper formatting
        xml_str = self._prettify_xml(root)

        # Add DOCTYPE declaration
        xml_with_doctype = self._add_doctype(xml_str)

        # Save to file if path provided
        if output_path:
            with open(output_path, 'w', encoding='UTF-8') as f:
                f.write(xml_with_doctype)

        # Return as BytesIO buffer
        buffer = io.BytesIO(xml_with_doctype.encode('UTF-8'))
        buffer.seek(0)
        return buffer

    def _create_employee_element(self, employee: Dict, totals: Dict) -> ET.Element:
        """Create XML element for a single employee"""
        salarie = ET.Element('salarie')

        # Matricule
        matricule = ET.SubElement(salarie, 'matricule')
        matricule.text = str(employee.get('matricule', ''))

        # Nom
        nom = ET.SubElement(salarie, 'nom')
        nom.text = str(employee.get('nom', '')).upper()

        # Prenom
        prenom = ET.SubElement(salarie, 'prenom')
        prenom.text = str(employee.get('prenom', '')).upper()

        # Date de naissance
        if employee.get('date_naissance'):
            date_naissance = ET.SubElement(salarie, 'dateNaissance')
            # Convert to YYYY-MM-DD if necessary
            date_val = employee.get('date_naissance')
            if isinstance(date_val, str):
                date_naissance.text = date_val
            else:
                date_naissance.text = date_val.strftime('%Y-%m-%d')

        # Affiliations (default to "Oui" if not specified)
        affiliation_ac = ET.SubElement(salarie, 'affiliationAC')
        affiliation_ac.text = employee.get('affiliation_ac', 'Oui')

        affiliation_rc = ET.SubElement(salarie, 'affiliationRC')
        affiliation_rc.text = employee.get('affiliation_rc', 'Oui')

        affiliation_car = ET.SubElement(salarie, 'affiliationCAR')
        affiliation_car.text = employee.get('affiliation_car', 'Oui')

        # Teletravail
        teletravail = ET.SubElement(salarie, 'teletravail')
        teletravail.text = employee.get('teletravail', 'Non')

        # Pays teletravail (only if teletravail = Oui)
        if employee.get('teletravail', 'Non') == 'Oui' and employee.get('pays_teletravail'):
            pays_teletravail = ET.SubElement(salarie, 'paysTeletravail')
            pays_teletravail.text = employee.get('pays_teletravail', '')

        # Administrateur salarié
        admin_salarie = ET.SubElement(salarie, 'administrateurSalarie')
        admin_salarie.text = employee.get('administrateur_salarie', 'Non')

        # Remuneration section
        remuneration = ET.SubElement(salarie, 'remuneration')

        salaire_brut = float(employee.get('salaire_brut', 0))

        # Salaire brut
        salaire_brut_elem = ET.SubElement(remuneration, 'salaireBrut')
        salaire_brut_elem.text = str(int(round(salaire_brut, 0)))

        # Heures totales
        heures_totales = ET.SubElement(remuneration, 'heuresTotales')
        heures_totales.text = str(int(employee.get('base_heures', 169)))

        # Calculate contribution bases
        bases = self.calculate_contribution_bases(salaire_brut)

        # baseCCSS
        base_ccss = ET.SubElement(remuneration, 'baseCCSS')
        base_ccss.text = str(int(round(bases['baseCCSS'], 0)))
        totals['CCSS'] += bases['baseCCSS']

        # baseCAR
        base_car = ET.SubElement(remuneration, 'baseCAR')
        base_car.text = str(int(round(bases['baseCAR'], 0)))
        totals['CAR'] += bases['baseCAR']

        # baseCMRCTA
        base_cmrc_ta = ET.SubElement(remuneration, 'baseCMRCTA')
        base_cmrc_ta.text = str(int(round(bases['baseCMRCTA'], 0)))
        totals['CMRCTA'] += bases['baseCMRCTA']

        # baseCMRCTB
        base_cmrc_tb = ET.SubElement(remuneration, 'baseCMRCTB')
        base_cmrc_tb.text = str(int(round(bases['baseCMRCTB'], 0)))
        totals['CMRCTB'] += bases['baseCMRCTB']

        # Update Assurance Chomage total
        totals['AssuranceChomage'] += bases['baseAssuranceChomage']

        # Events section (optional)
        self._add_events_section(salarie, employee)

        return salarie

    def _add_events_section(self, salarie: ET.Element, employee: Dict):
        """Add events section if applicable (conges, primes, maladie, etc.)"""
        has_events = False
        evenements = ET.Element('evenements')

        # Congés payés
        if employee.get('jours_cp_pris') and float(employee.get('jours_cp_pris', 0)) > 0:
            has_events = True
            conges_payes = ET.SubElement(evenements, 'congesPayes')

            # Convert days to hours (assuming 7h/day)
            jours = float(employee.get('jours_cp_pris', 0))
            heures = jours * 7

            heures_elem = ET.SubElement(conges_payes, 'heures')
            heures_elem.text = str(int(heures))

            # Add dates if available
            if employee.get('cp_date_debut'):
                date_debut = ET.SubElement(conges_payes, 'dateDebut')
                date_debut.text = employee.get('cp_date_debut')

            if employee.get('cp_date_fin'):
                date_fin = ET.SubElement(conges_payes, 'dateFin')
                date_fin.text = employee.get('cp_date_fin')

        # Prime
        if employee.get('prime') and float(employee.get('prime', 0)) > 0:
            has_events = True
            prime = ET.SubElement(evenements, 'prime')
            montant = ET.SubElement(prime, 'montant')
            montant.text = f"{float(employee.get('prime', 0)):.2f}"

        # Maladie
        if employee.get('maladie_date_debut'):
            has_events = True
            maladie = ET.SubElement(evenements, 'maladie')

            date_debut = ET.SubElement(maladie, 'dateDebut')
            date_debut.text = employee.get('maladie_date_debut')

            if employee.get('maladie_date_fin'):
                date_fin = ET.SubElement(maladie, 'dateFin')
                date_fin.text = employee.get('maladie_date_fin')

        # Only add evenements section if there are events
        if has_events:
            salarie.append(evenements)

    def _prettify_xml(self, elem: ET.Element) -> str:
        """Return a pretty-printed XML string"""
        rough_string = ET.tostring(elem, encoding='UTF-8', method='xml')
        reparsed = minidom.parseString(rough_string)

        # Remove the XML declaration added by minidom (we'll add our own)
        pretty = reparsed.toprettyxml(indent="\t", encoding='UTF-8').decode('UTF-8')

        # Remove empty lines
        lines = [line for line in pretty.split('\n') if line.strip()]
        return '\n'.join(lines[1:])  # Skip the first line (XML declaration)

    def _add_doctype(self, xml_str: str) -> str:
        """Add XML declaration and DOCTYPE to the XML string"""
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>'
        doctype = f'<!DOCTYPE declaration PUBLIC "{self.DTD_PUBLIC_ID}" "{self.DTD_SYSTEM_ID}">'

        return f"{xml_declaration}\n{doctype}\n{xml_str}"


# Utility function for integration
def generate_dsm_for_period(employees_df: pl.DataFrame,
                           employer_number: str,
                           period: str,
                           plafond_ss_t1: float = 3428.00) -> io.BytesIO:
    """
    Generate DSM XML declaration for a payroll period

    Args:
        employees_df: Employee payroll data
        employer_number: Employer registration number
        period: Period in YYYY-MM format
        plafond_ss_t1: SS ceiling T1

    Returns:
        BytesIO buffer with XML content
    """
    generator = DSMXMLGenerator(employer_number, plafond_ss_t1)
    return generator.generate_dsm_xml(employees_df, period)
