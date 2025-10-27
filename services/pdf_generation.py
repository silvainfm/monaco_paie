"""
PDF Generation Module for Monaco Payroll System
===============================================
Generates paystubs, pay journals, and PTO provision documents
===============================================
Envoyer à l'employeur avant l'employé
tenir le bulletin sur une page
agrandir le tableau pour remplir la page

"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, 
    Spacer, PageBreak, Image, KeepTogether, Frame, PageTemplate
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.doctemplate import BaseDocTemplate
import polars as pl
from datetime import datetime, date, timedelta
from pathlib import Path
import io
from typing import Dict, List, Optional, Tuple
import locale
import calendar
import logging

logger = logging.getLogger(__name__)

# Set French locale for formatting
try:
    locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'fr_FR')
    except:
        pass  # Use default locale if French not available

class PDFStyles:
    """Styles et formatage pour les PDFs"""
    
    @staticmethod
    def get_styles():
        """Obtenir les styles de base"""
        styles = getSampleStyleSheet()
        
        # Style pour l'en-tête
        styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=styles['Title'],
            fontSize=16,
            textColor=colors.HexColor('#2C3E50'),
            spaceAfter=30,
            alignment=TA_CENTER
        ))
        
        # Style pour les sous-titres
        styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#34495E'),
            spaceAfter=12,
            spaceBefore=12,
            leftIndent=0
        ))
        
        # Style pour le texte normal
        styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=styles['Normal'],
            fontSize=9,
            leading=12
        ))
        
        # Style pour les montants (aligné à droite)
        styles.add(ParagraphStyle(
            name='RightAligned',
            parent=styles['Normal'],
            fontSize=9,
            alignment=TA_RIGHT
        ))
        
        # Style pour les totaux
        styles.add(ParagraphStyle(
            name='BoldTotal',
            parent=styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold'
        ))
        
        return styles
    
    @staticmethod
    def format_currency(amount: float) -> str:
        """Formater un montant en euros"""
        if amount is None:
            return "0,00 €"
        return f"{amount:,.2f} €".replace(",", " ").replace(".", ",")
    
    @staticmethod
    def format_date(date_value) -> str:
        """Formater une date en format français"""
        if isinstance(date_value, str):
            try:
                date_value = datetime.strptime(date_value, "%Y-%m-%d")
            except:
                return date_value
        if date_value:
            return date_value.strftime("%d/%m/%Y")
        return ""

class PaystubPDFGenerator:
    """Compact single-page paystub generator with blue color scheme"""
    
    # Color scheme - blue tones
    COLORS = {
        'primary_blue': colors.HexColor('#1e3a8a'),      # Dark blue for headers
        'secondary_blue': colors.HexColor('#3b82f6'),    # Medium blue for accents
        'light_blue': colors.HexColor('#dbeafe'),        # Light blue for backgrounds
        'very_light_blue': colors.HexColor('#f0f9ff'),   # Very light blue
        'text_dark': colors.HexColor('#1e293b'),         # Dark text
        'text_gray': colors.HexColor('#64748b'),         # Gray text
        'success_green': colors.HexColor('#10b981'),     # Green for net pay
        'border_gray': colors.HexColor('#e2e8f0')        # Light gray for borders
    }
    
    # Rubric codes for salary elements
    RUBRIC_CODES = {
        'salaire_base': '0003',
        'prime_anciennete': '1025',
        'heures_sup_125': '2001',
        'heures_sup_150': '2002',
        'prime_performance': '2029',
        'prime_autre': '2057',
        'jours_feries': '2065',
        'absence_maladie': '2985',
        'maintien_salaire': '2993',
        'absence_cp': '3211',
        'indemnite_cp': '4271',
        'tickets_resto': '7065'
    }
    
    # Charge codes
    CHARGE_CODES = {
        'CAR': '1901',
        'CCSS': '9301',
        'ASSEDIC_T1': '7001',
        'ASSEDIC_T2': '7121',
        'RETRAITE_COMP_T1': '74N0',
        'RETRAITE_COMP_T2': '74N6',
        'CONTRIB_EQUILIBRE_TECH': '7422',
        'CONTRIB_EQUILIBRE_GEN_T1': '74A0',
        'CONTRIB_EQUILIBRE_GEN_T2': '74A2',
        'CMRC': '9302',
        'PREVOYANCE': '8001'
    }
    
    def __init__(self, company_info: Dict, logo_path: Optional[str] = None):
        self.company_info = company_info  # Not used but kept for compatibility
        self.logo_path = logo_path
        self.styles = self._create_styles()
    
    def _create_styles(self):
        """Create custom styles for the paystub"""
        styles = getSampleStyleSheet()
        
        styles.add(ParagraphStyle(
            name='CompactTitle',
            fontSize=14,
            textColor=self.COLORS['primary_blue'],
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            spaceAfter=8
        ))
        
        styles.add(ParagraphStyle(
            name='CompactSection',
            fontSize=9,
            textColor=self.COLORS['primary_blue'],
            fontName='Helvetica-Bold',
            spaceAfter=4
        ))
        
        styles.add(ParagraphStyle(
            name='CompactNormal',
            fontSize=8,
            textColor=self.COLORS['text_dark'],
            leading=9
        ))
        
        styles.add(ParagraphStyle(
            name='CompactSmall',
            fontSize=7,
            textColor=self.COLORS['text_gray'],
            leading=8
        ))
        
        return styles
    
    def _get_numeric(self, data, key, default=0):
        """Safely get numeric value from data dictionary"""
        value = data.get(key, default)
        if isinstance(value, dict):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    
    def generate_paystub(self, employee_data: Dict, output_path: Optional[str] = None) -> io.BytesIO:
        """Generate a compact single-page paystub"""
        
        # Ensure required data fields
        self._prepare_employee_data(employee_data)
        
        # Create buffer or file
        if output_path:
            pdf_buffer = output_path
        else:
            pdf_buffer = io.BytesIO()
        
        # Create document with smaller margins for compact layout
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            rightMargin=0.8*cm,
            leftMargin=0.8*cm,
            topMargin=1*cm,
            bottomMargin=0.8*cm
        )
        
        # Build the content
        story = []
        
        # Header
        story.append(self._create_header())
        story.append(Spacer(1, 0.2*cm))
        
        # Employee information block
        story.append(self._create_employee_info(employee_data))
        story.append(Spacer(1, 0.2*cm))
        
        # Period information
        story.append(self._create_period_bar(employee_data))
        story.append(Spacer(1, 0.2*cm))
        
        # Combined salary and charges table
        story.append(self._create_combined_table(employee_data))
        story.append(Spacer(1, 0.2*cm))
        
        # Net pay summary
        story.append(self._create_net_summary(employee_data))
        story.append(Spacer(1, 0.2*cm))
        
        # Bottom section with cumuls and PTO
        story.append(self._create_cumuls_pto_section(employee_data))
        
        # Footer
        story.append(Spacer(1, 0.15*cm))
        story.append(self._create_compact_footer(employee_data))
        
        # Build PDF
        doc.build(story)
        
        if not output_path:
            pdf_buffer.seek(0)
        
        return pdf_buffer
    
    def _prepare_employee_data(self, data: Dict):
        """Ensure all required fields have default values"""
        defaults = {
            'ccss_number': '',
            'date_entree': '',
            'anciennete': '0 ans',
            'emploi': 'SALES ASSISTANT',
            'qualification': 'NON CADRE',
            'niveau': '3',
            'coefficient': '110.55',
            'heures_payees': 169,
            'base_heures': 169,
            'taux_horaire': 0,
            'cumul_brut': 0,
            'cumul_base_ss': 0,
            'cumul_net_percu': 0,
            'cumul_charges_sal': 0,
            'cumul_charges_pat': 0,
            'cp_acquis_n1': 30,
            'cp_pris_n1': 0,
            'cp_restants_n1': 30,
            'cp_acquis_n': 0,
            'cp_pris_n': 0,
            'cp_restants_n': 0,
        }
        
        for key, value in defaults.items():
            if key not in data:
                data[key] = value
    
    def _create_header(self) -> Table:
        """Create the paystub header"""
        data = [["BULLETIN DE PAIE"]]
        
        table = Table(data, colWidths=[19.4*cm])
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLORS['primary_blue']),
        ]))
        
        return table
    
    def _create_employee_info(self, employee_data: Dict) -> Table:
        """Create compact employee information block"""
        
        data = [
            [
                f"Matricule: {employee_data.get('matricule', '')}",
                f"N° CCSS: {employee_data.get('ccss_number', '')}",
                f"Entrée: {PDFStyles.format_date(employee_data.get('date_entree', ''))}",
                f"Ancienneté: {employee_data.get('anciennete', '0 ans')}"
            ],
            [
                f"{employee_data.get('nom', '')} {employee_data.get('prenom', '')}",
                f"Emploi: {employee_data.get('emploi', '')}",
                f"Qualif.: {employee_data.get('qualification', '')}",
                f"Niv: {employee_data.get('niveau', '')} - Coef: {employee_data.get('coefficient', '')}"
            ]
        ]
        
        table = Table(data, colWidths=[4.85*cm, 4.85*cm, 4.85*cm, 4.85*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COLORS['very_light_blue']),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLORS['text_dark']),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border_gray']),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('FONTNAME', (0, 1), (0, 1), 'Helvetica-Bold'),
        ]))
        
        return table
    
    def _create_period_bar(self, employee_data: Dict) -> Table:
        """Create period information bar"""
        
        data = [[
            f"PAIE DU {employee_data.get('period_start', '')}",
            f"AU {employee_data.get('period_end', '')}",
            f"PAYÉ LE: {employee_data.get('payment_date', '')}",
            f"HEURES: {employee_data.get('heures_payees', 169):.2f}"
        ]]
        
        table = Table(data, colWidths=[4.85*cm, 4.85*cm, 4.85*cm, 4.85*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COLORS['primary_blue']),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        return table
    
    def _create_combined_table(self, employee_data: Dict) -> Table:
        """Create combined salary elements and charges table with proper Monaco format"""
        
        charges_details = employee_data.get('details_charges', {})
        charges_sal = charges_details.get('charges_salariales', {})
        charges_pat = charges_details.get('charges_patronales', {})
        
        # Header
        data = [
            ["RUBRIQUES", "QUANTITÉ", "TAUX OU BASE", "À PAYER", "À DÉDUIRE", "TAUX CHARGES", "CHARGES PATRONALES"]
        ]
        
        # === SALARY ELEMENTS SECTION ===
        # Base salary (fix French formatting for base heures too)
        if employee_data.get('salaire_base', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['salaire_base']} Salaire Mensuel",
                f"{employee_data.get('base_heures', 169):.2f}".replace('.', ','),
                f"{employee_data.get('salaire_base', 0):,.2f}".replace(',', ' ').replace('.', ','),
                PDFStyles.format_currency(employee_data.get('salaire_base', 0)),
                "",
                ""
            ])
        
        # Overtime 125%
        if employee_data.get('heures_sup_125', 0) > 0:
            taux_125 = employee_data.get('taux_horaire', 0) * 1.25
            data.append([
                f"{self.RUBRIC_CODES['heures_sup_125']} Heures sup. 125%",
                f"{employee_data.get('heures_sup_125', 0):.2f}".replace('.', ','),
                f"{taux_125:.4f}".replace('.', ','),
                PDFStyles.format_currency(employee_data.get('montant_hs_125', 0)),
                "",
                ""
            ])
        
        # Overtime 150%
        if employee_data.get('heures_sup_150', 0) > 0:
            taux_150 = employee_data.get('taux_horaire', 0) * 1.50
            data.append([
                f"{self.RUBRIC_CODES['heures_sup_150']} Heures sup. 150%",
                f"{employee_data.get('heures_sup_150', 0):.2f}".replace('.', ','),
                f"{taux_150:.4f}".replace('.', ','),
                PDFStyles.format_currency(employee_data.get('montant_hs_150', 0)),
                "",
                ""
            ])
        
        # Bonuses
        if employee_data.get('prime', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['prime_performance']} Prime",
                "",
                "",
                PDFStyles.format_currency(employee_data.get('prime', 0)),
                "",
                ""
            ])
        
        # Holiday pay
        if employee_data.get('heures_jours_feries', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['jours_feries']} Jours fériés 100%",
                f"{employee_data.get('heures_jours_feries', 0):.2f}".replace('.', ','),
                f"{employee_data.get('taux_horaire', 0):.4f}".replace('.', ','),
                PDFStyles.format_currency(employee_data.get('montant_jours_feries', 0)),
                "",
                ""
            ])
        
        # Absences (deductions)
        if employee_data.get('retenue_absence', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['absence_maladie']} Absence {employee_data.get('type_absence', '')}",
                f"{employee_data.get('heures_absence', 0):.2f}".replace('.', ','),
                f"{employee_data.get('taux_horaire', 0):.4f}".replace('.', ','),
                "",
                PDFStyles.format_currency(employee_data.get('retenue_absence', 0)),
                ""
            ])
        
        # PTO indemnity
        if employee_data.get('indemnite_cp', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['indemnite_cp']} Indemnité congés payés",
                f"{employee_data.get('jours_cp_pris', 0):.2f}".replace('.', ','),
                "",
                PDFStyles.format_currency(employee_data.get('indemnite_cp', 0)),
                "",
                ""
            ])
        
        # TOTAL BRUT row
        total_brut_row = len(data)
        data.append([
            "TOTAL BRUT",
            "",
            "",
            PDFStyles.format_currency(employee_data.get('salaire_brut', 0)),
            "",
            "",
            ""
        ])
        
        # === SOCIAL CHARGES SECTION ===
        charges_start_row = len(data)
        
        # Calculate bases for tranches
        salaire_brut = employee_data.get('salaire_brut', 0)
        plafond_t1 = min(salaire_brut, 3428)
        base_t2 = max(0, min(salaire_brut - 3428, 13712 - 3428)) if salaire_brut > 3428 else 0
        
        # CAR
        if 'CAR' in charges_sal or 'CAR' in charges_pat:
            data.append([
                f"{self.CHARGE_CODES['CAR']} CAR",
                f"{salaire_brut:,.2f}".replace(',', ' ').replace('.', ','),
                "6,8500",
                "",
                PDFStyles.format_currency(charges_sal.get('CAR', 0)),
                "8,3500",
                PDFStyles.format_currency(charges_pat.get('CAR', 0))
            ])
        
        # CCSS
        if 'CCSS' in charges_sal:
            data.append([
                f"{self.CHARGE_CODES['CCSS']} C.C.S.S.",
                f"{salaire_brut:,.2f}".replace(',', ' ').replace('.', ','),
                "14,7500",
                "",
                PDFStyles.format_currency(charges_sal.get('CCSS', 0)),
                "",
                ""
            ])
        
        # Unemployment insurance T1
        if 'ASSEDIC_T1' in charges_sal or 'ASSEDIC_T1' in charges_pat:
            data.append([
                f"{self.CHARGE_CODES['ASSEDIC_T1']} Assurance Chômage tranche A",
                f"{plafond_t1:,.2f}".replace(',', ' ').replace('.', ','),
                "2,4000",
                "",
                PDFStyles.format_currency(charges_sal.get('ASSEDIC_T1', 0)),
                "4,0500",
                PDFStyles.format_currency(charges_pat.get('ASSEDIC_T1', 0))
            ])
        
        # Unemployment insurance T2
        if base_t2 > 0 and ('ASSEDIC_T2' in charges_sal or 'ASSEDIC_T2' in charges_pat):
            data.append([
                f"{self.CHARGE_CODES['ASSEDIC_T2']} Assurance Chômage tranche B",
                f"{base_t2:,.2f}".replace(',', ' ').replace('.', ','),
                "2,4000",
                "",
                PDFStyles.format_currency(charges_sal.get('ASSEDIC_T2', 0)),
                "4,0500",
                PDFStyles.format_currency(charges_pat.get('ASSEDIC_T2', 0))
            ])
        
        # Technical balance contributions
        if 'CONTRIB_EQUILIBRE_TECH' in charges_sal or 'CONTRIB_EQUILIBRE_TECH' in charges_pat:
            data.append([
                f"{self.CHARGE_CODES['CONTRIB_EQUILIBRE_TECH']} Contrib. équilibre technique T1+T2",
                f"{salaire_brut:,.2f}".replace(',', ' ').replace('.', ','),
                "0,1400",
                "",
                PDFStyles.format_currency(charges_sal.get('CONTRIB_EQUILIBRE_TECH', 0)),
                "0,2100",
                PDFStyles.format_currency(charges_pat.get('CONTRIB_EQUILIBRE_TECH', 0))
            ])
        
        # General balance contributions T1
        if 'CONTRIB_EQUILIBRE_GEN_T1' in charges_sal or 'CONTRIB_EQUILIBRE_GEN_T1' in charges_pat:
            data.append([
                f"{self.CHARGE_CODES['CONTRIB_EQUILIBRE_GEN_T1']} Contrib. équilibre général T1",
                f"{plafond_t1:,.2f}".replace(',', ' ').replace('.', ','),
                "0,8600",
                "",
                PDFStyles.format_currency(charges_sal.get('CONTRIB_EQUILIBRE_GEN_T1', 0)),
                "1,2900",
                PDFStyles.format_currency(charges_pat.get('CONTRIB_EQUILIBRE_GEN_T1', 0))
            ])
        
        # General balance contributions T2
        if base_t2 > 0 and ('CONTRIB_EQUILIBRE_GEN_T2' in charges_sal or 'CONTRIB_EQUILIBRE_GEN_T2' in charges_pat):
            data.append([
                f"{self.CHARGE_CODES['CONTRIB_EQUILIBRE_GEN_T2']} Contrib. équilibre général T2",
                f"{base_t2:,.2f}".replace(',', ' ').replace('.', ','),
                "1,0800",
                "",
                PDFStyles.format_currency(charges_sal.get('CONTRIB_EQUILIBRE_GEN_T2', 0)),
                "1,6200",
                PDFStyles.format_currency(charges_pat.get('CONTRIB_EQUILIBRE_GEN_T2', 0))
            ])
        
        # Complementary retirement T1
        if 'RETRAITE_COMP_T1' in charges_sal or 'RETRAITE_COMP_T1' in charges_pat:
            data.append([
                f"{self.CHARGE_CODES['RETRAITE_COMP_T1']} Retraite comp. unifiée T1",
                f"{plafond_t1:,.2f}".replace(',', ' ').replace('.', ','),
                "3,1500",
                "",
                PDFStyles.format_currency(charges_sal.get('RETRAITE_COMP_T1', 0)),
                "4,7200",
                PDFStyles.format_currency(charges_pat.get('RETRAITE_COMP_T1', 0))
            ])
        
        # Complementary retirement T2
        if base_t2 > 0 and ('RETRAITE_COMP_T2' in charges_sal or 'RETRAITE_COMP_T2' in charges_pat):
            data.append([
                f"{self.CHARGE_CODES['RETRAITE_COMP_T2']} Retraite comp. unifiée T2",
                f"{base_t2:,.2f}".replace(',', ' ').replace('.', ','),
                "8,6400",
                "",
                PDFStyles.format_currency(charges_sal.get('RETRAITE_COMP_T2', 0)),
                "12,9500",
                PDFStyles.format_currency(charges_pat.get('RETRAITE_COMP_T2', 0))
            ])
        
        # TOTAL RETENUES row
        total_retenues_row = len(data)
        data.append([
            "TOTAL RETENUES",
            "",
            "",
            "",
            PDFStyles.format_currency(employee_data.get('total_charges_salariales', 0)),
            "",
            PDFStyles.format_currency(employee_data.get('total_charges_patronales', 0))
        ])
        
        # NET row
        net_row = len(data)
        data.append([
            "NET",
            "",
            "",
            "",
            "",
            "",
            PDFStyles.format_currency(employee_data.get('salaire_net', 0))
        ])
        
        # Meal vouchers (after NET)
        if employee_data.get('tickets_restaurant', 0) > 0:
            tickets = employee_data.get('tickets_restaurant_details', {})
            nb_tickets = employee_data.get('tickets_restaurant', 0)
            valeur_unitaire = tickets.get('valeur_unitaire', 9.00)
            data.append([
                f"{self.RUBRIC_CODES['tickets_resto']} Tickets restaurant",
                f"{nb_tickets:.0f}",
                f"{valeur_unitaire:.4f}".replace('.', ','),
                "",
                PDFStyles.format_currency(tickets.get('part_salariale', 0)),
                "",
                ""
            ])
        
        # Create table with 7 columns now
        table = Table(data, colWidths=[4.8*cm, 1.8*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.8*cm])
        
        # Style commands
        style_commands = [
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['secondary_blue']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 6),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # General formatting
            ('FONTSIZE', (0, 1), (-1, -1), 6),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # QUANTITÉ column center
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),   # TAUX OU BASE column right
            ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),  # À PAYER, À DÉDUIRE, TAUX CHARGES, CHARGES PATRONALES right
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border_gray']),
            
            # TOTAL BRUT row
            ('BACKGROUND', (0, total_brut_row), (-1, total_brut_row), self.COLORS['light_blue']),
            ('FONTNAME', (0, total_brut_row), (-1, total_brut_row), 'Helvetica-Bold'),
            ('LINEABOVE', (0, total_brut_row), (-1, total_brut_row), 1, self.COLORS['primary_blue']),
            
            # Charges section separator
            ('LINEABOVE', (0, charges_start_row), (-1, charges_start_row), 0.5, self.COLORS['primary_blue']),
            
            # TOTAL RETENUES row
            ('BACKGROUND', (0, total_retenues_row), (-1, total_retenues_row), self.COLORS['light_blue']),
            ('FONTNAME', (0, total_retenues_row), (-1, total_retenues_row), 'Helvetica-Bold'),
            ('LINEABOVE', (0, total_retenues_row), (-1, total_retenues_row), 1, self.COLORS['primary_blue']),
            
            # NET row
            ('BACKGROUND', (0, net_row), (-1, net_row), self.COLORS['very_light_blue']),
            ('FONTNAME', (0, net_row), (-1, net_row), 'Helvetica-Bold'),
            ('FONTSIZE', (0, net_row), (-1, net_row), 7),
            ('LINEABOVE', (0, net_row), (-1, net_row), 1.5, self.COLORS['success_green']),
            
            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]
        
        table.setStyle(TableStyle(style_commands))
        
        return table
    
    def _add_salary_rows(self, data: List, employee_data: Dict):
        """Add salary element rows with rubric codes"""
        
        # Base salary
        if employee_data.get('salaire_base', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['salaire_base']} Salaire Mensuel",
                f"{employee_data.get('base_heures', 169):.2f}",
                PDFStyles.format_currency(employee_data.get('taux_horaire', 0)),
                PDFStyles.format_currency(employee_data.get('salaire_base', 0)),
                ""
            ])
        
        # Overtime and other elements
        if employee_data.get('heures_sup_125', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['heures_sup_125']} Heures sup. 125%",
                f"{employee_data.get('heures_sup_125', 0):.2f}",
                "125%",
                PDFStyles.format_currency(employee_data.get('montant_hs_125', 0)),
                ""
            ])
        
        if employee_data.get('heures_sup_150', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['heures_sup_150']} Heures sup. 150%",
                f"{employee_data.get('heures_sup_150', 0):.2f}",
                "150%",
                PDFStyles.format_currency(employee_data.get('montant_hs_150', 0)),
                ""
            ])
        
        if employee_data.get('prime', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['prime_performance']} Prime",
                "",
                "",
                PDFStyles.format_currency(employee_data.get('prime', 0)),
                ""
            ])
        
        if employee_data.get('heures_jours_feries', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['jours_feries']} Jours fériés",
                f"{employee_data.get('heures_jours_feries', 0):.2f}",
                "100%",
                PDFStyles.format_currency(employee_data.get('montant_jours_feries', 0)),
                ""
            ])
        
        if employee_data.get('retenue_absence', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['absence_maladie']} Absence",
                f"{employee_data.get('heures_absence', 0):.2f}",
                "",
                "",
                PDFStyles.format_currency(employee_data.get('retenue_absence', 0))
            ])
    
    def _create_charges_table(self, employee_data: Dict) -> Table:
        """Create social charges table"""
        
        charges_details = employee_data.get('details_charges', {})
        charges_sal = charges_details.get('charges_salariales', {})
        charges_pat = charges_details.get('charges_patronales', {})
        
        data = [
            ["COTISATIONS", "BASE", "TX SAL.", "MT SAL.", "TX PAT.", "MT PAT."]
        ]
        
        # Add charge rows
        self._add_charges_rows(data, employee_data, charges_sal, charges_pat)
        
        # Total row
        data.append([
            "TOTAL COTISATIONS",
            "",
            "",
            PDFStyles.format_currency(employee_data.get('total_charges_salariales', 0)),
            "",
            PDFStyles.format_currency(employee_data.get('total_charges_patronales', 0))
        ])
        
        table = Table(data, colWidths=[5.5*cm, 3*cm, 2*cm, 2.7*cm, 2*cm, 3.2*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['secondary_blue']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 6),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTSIZE', (0, 1), (-1, -1), 6),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border_gray']),
            ('LINEAFTER', (3, 0), (3, -1), 1, self.COLORS['primary_blue']),
            ('BACKGROUND', (0, -1), (-1, -1), self.COLORS['light_blue']),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 1, self.COLORS['primary_blue']),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        
        return table
    
    def _add_charges_rows(self, data: List, employee_data: Dict, charges_sal: Dict, charges_pat: Dict):
        """Add charge rows with codes"""
        
        # CAR
        if 'CAR' in charges_sal or 'CAR' in charges_pat:
            data.append([
                f"{self.CHARGE_CODES['CAR']} CAR",
                PDFStyles.format_currency(employee_data.get('salaire_brut', 0)),
                "6.85%",
                PDFStyles.format_currency(charges_sal.get('CAR', 0)),
                "8.35%",
                PDFStyles.format_currency(charges_pat.get('CAR', 0))
            ])
        
        # CCSS
        if 'CCSS' in charges_sal:
            data.append([
                f"{self.CHARGE_CODES['CCSS']} C.C.S.S.",
                PDFStyles.format_currency(employee_data.get('salaire_brut', 0)),
                "14.75%",
                PDFStyles.format_currency(charges_sal.get('CCSS', 0)),
                "",
                ""
            ])
        
        # Other charges...
        # Add remaining charges following same pattern
    
    def _create_net_summary(self, employee_data: Dict) -> Table:
        """Create net pay summary - right-aligned NET À PAYER box only"""

        net_pay = employee_data.get('salaire_net', 0)

        data = []

        # Add withholding tax rows for French residents
        if employee_data.get('pays_residence') == 'FRANCE' and employee_data.get('prelevement_source', 0) > 0:
            data.append([
                "", "",  # Spacer columns to push content right
                "Net avant impôt", PDFStyles.format_currency(net_pay + employee_data.get('prelevement_source', 0))
            ])
            data.append([
                "", "",
                "Prélèvement source", f"- {PDFStyles.format_currency(employee_data.get('prelevement_source', 0))}"
            ])

        # Main row with net pay only (right-aligned)
        data.append([
            "", "",  # Spacer columns to push content right
            "NET À PAYER", PDFStyles.format_currency(net_pay)
        ])

        # Column widths: spacer columns + 6cm total for NET À PAYER (3cm label + 3cm amount)
        table = Table(data, colWidths=[7*cm, 6.4*cm, 3*cm, 3*cm])

        # Build style commands
        style_commands = [
            # General alignment and font
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),

            # Style for the main row (last row)
            ('FONTNAME', (2, -1), (3, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (2, -1), (3, -1), 10),

            # Net pay styling (green)
            ('TEXTCOLOR', (3, -1), (3, -1), self.COLORS['success_green']),
            ('BACKGROUND', (2, -1), (3, -1), self.COLORS['very_light_blue']),
            ('BOX', (2, -1), (3, -1), 1, self.COLORS['success_green']),

            # Padding for main row
            ('TOPPADDING', (2, -1), (3, -1), 5),
            ('BOTTOMPADDING', (2, -1), (3, -1), 5),
        ]

        # Add styles for withholding tax rows if present
        if employee_data.get('pays_residence') == 'FRANCE' and employee_data.get('prelevement_source', 0) > 0:
            style_commands.extend([
                ('FONTSIZE', (2, 0), (3, -2), 8),
                ('TEXTCOLOR', (2, 0), (3, -2), self.COLORS['text_gray']),
            ])

        table.setStyle(TableStyle(style_commands))

        return table
    
    def _create_cumuls_pto_section(self, employee_data: Dict) -> Table:
        """Create bottom section with cumulative amounts and PTO"""
        
        # Helper to safely get numeric values
        def get_numeric(data, key, default=0):
            value = data.get(key, default)
            if isinstance(value, dict):
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default
        
        # Cumulative data
        cumul_data = [
            ["CUMULS", "BRUT", "BASE S.S.", "NET PERÇU", "CHARGES SAL.", "CHARGES PAT."],
            [
                f"{datetime.now().year}",
                PDFStyles.format_currency(get_numeric(employee_data, 'cumul_brut')),
                PDFStyles.format_currency(get_numeric(employee_data, 'cumul_base_ss')),
                PDFStyles.format_currency(get_numeric(employee_data, 'cumul_net_percu')),
                PDFStyles.format_currency(get_numeric(employee_data, 'cumul_charges_sal')),
                PDFStyles.format_currency(get_numeric(employee_data, 'cumul_charges_pat'))
            ],
            [
                "COÛT GLOBAL SALARIÉ",
                PDFStyles.format_currency(get_numeric(employee_data, 'cout_total_employeur')),
                "",
                "",
                "",
                ""
            ]
        ]
        
        # PTO data - safely get numeric values
        year = datetime.now().year
        cp_acquis_n1 = get_numeric(employee_data, 'cp_acquis_n1', 30)
        cp_pris_n1 = get_numeric(employee_data, 'cp_pris_n1', 0)
        cp_restants_n1 = get_numeric(employee_data, 'cp_restants_n1', 30)
        cp_acquis_n = get_numeric(employee_data, 'cp_acquis_n', 0)
        cp_pris_n = get_numeric(employee_data, 'cp_pris_n', 0)
        cp_restants_n = get_numeric(employee_data, 'cp_restants_n', 0)
        
        pto_data = [
            ["CONGÉS", f"{year-1}/{str(year)[2:]}", f"{year}/{str(year+1)[2:]}"],
            ["Acquis", f"{cp_acquis_n1:.1f}", f"{cp_acquis_n:.1f}"],
            ["Pris", f"{cp_pris_n1:.1f}", f"{cp_pris_n:.1f}"],
            ["Restants", f"{cp_restants_n1:.1f}", f"{cp_restants_n:.1f}"]
        ]
        
        # Combine tables
        combined_data = []
        for i in range(max(len(cumul_data), len(pto_data))):
            row = []
            if i < len(cumul_data):
                row.extend(cumul_data[i])
            else:
                row.extend([""] * 6)
            row.append("")  # Separator
            if i < len(pto_data):
                row.extend(pto_data[i])
            else:
                row.extend([""] * 3)
            combined_data.append(row)
        
        table = Table(
            combined_data,
            colWidths=[2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 0.4*cm, 2*cm, 1.5*cm, 1.5*cm]
        )
        
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (5, 0), self.COLORS['primary_blue']),
            ('TEXTCOLOR', (0, 0), (5, 0), colors.white),
            ('FONTNAME', (0, 0), (5, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (7, 0), (-1, 0), self.COLORS['secondary_blue']),
            ('TEXTCOLOR', (7, 0), (-1, 0), colors.white),
            ('FONTNAME', (7, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 6),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOX', (0, 0), (5, -1), 0.5, self.COLORS['border_gray']),
            ('BOX', (7, 0), (-1, -1), 0.5, self.COLORS['border_gray']),
            ('GRID', (0, 0), (5, -1), 0.5, self.COLORS['border_gray']),
            ('GRID', (7, 0), (-1, -1), 0.5, self.COLORS['border_gray']),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        
        return table
    
    def _create_compact_footer(self, employee_data: Dict) -> Table:
        """Create compact footer with legal notice only"""
        
        data = [
            ["DANS VOTRE INTÉRÊT ET POUR VOUS AIDER À FAIRE VALOIR VOS DROITS, CONSERVER CE BULLETIN SANS LIMITATION DE DURÉE"]
        ]
        
        table = Table(data, colWidths=[19.4*cm])
        table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (0, 0), 6),
            ('TEXTCOLOR', (0, 0), (0, 0), self.COLORS['text_gray']),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        return table
    
class PTOProvisionPDFGenerator:
    """Générateur du document de provision pour congés payés"""
    
    def __init__(self, company_info: Dict, logo_path: Optional[str] = None):
        self.company_info = company_info
        self.logo_path = logo_path
        self.styles = PDFStyles.get_styles()
    
    def generate_pto_provision(self, provisions_data: List[Dict], 
                              period: str, output_path: Optional[str] = None) -> io.BytesIO:
        """
        Générer le document de provision pour congés payés
        
        Args:
            provisions_data: Liste des provisions par employé
            period: Période (format: "MM-YYYY")
            output_path: Chemin de sortie (optionnel)
        """
        if output_path:
            pdf_buffer = output_path
        else:
            pdf_buffer = io.BytesIO()
        
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        story = []
        
        # En-tête
        story.extend(self._create_provision_header(period))
        
        # Tableau détaillé des provisions
        story.append(Paragraph("<b>PROVISION POUR CONGÉS PAYÉS</b>", self.styles['CustomHeading']))
        story.append(self._create_provisions_detail_table(provisions_data, period))
        story.append(Spacer(1, 1*cm))
        
        # Synthèse
        story.append(self._create_provisions_summary(provisions_data))
        
        # Pied de page
        story.append(Spacer(1, 2*cm))
        story.append(self._create_provision_footer(period))
        
        doc.build(story)
        
        if not output_path:
            pdf_buffer.seek(0)
        
        return pdf_buffer
    
    def _create_provision_header(self, period: str) -> List:
        """Créer l'en-tête du document de provision"""
        elements = []
        
        # Logo et titre
        header_data = []
        if self.logo_path and Path(self.logo_path).exists():
            try:
                logo = Image(self.logo_path, width=3*cm, height=2*cm)
                header_data.append([logo, "PROVISION POUR CONGÉS PAYÉS", ""])
            except:
                header_data.append(["", "PROVISION POUR CONGÉS PAYÉS", ""])
        else:
            header_data.append(["", "PROVISION POUR CONGÉS PAYÉS", ""])
        
        header_table = Table(header_data, colWidths=[5*cm, 8*cm, 5*cm])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (1, 0), (1, 0), 14),
        ]))
        
        elements.append(header_table)
        
        # Informations de période
        period_date = datetime.strptime(period, "%m-%Y")
        info_data = [
            [f"Établissement: {self.company_info.get('name', '')}"],
            [f"Date d'arrêté: {self._get_last_day_of_month(period_date).strftime('%d/%m/%Y')}"],
            ["Devise: Euro"]
        ]
        
        info_table = Table(info_data, colWidths=[18*cm])
        info_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        
        elements.append(Spacer(1, 0.5*cm))
        elements.append(info_table)
        elements.append(Spacer(1, 0.5*cm))
        
        return elements
    
    def _create_provisions_detail_table(self, provisions_data: List[Dict], period: str) -> Table:
        """Créer le tableau détaillé des provisions"""
        
        period_date = datetime.strptime(period, "%m-%Y")
        current_year = period_date.year
        previous_year = current_year - 1
        
        # En-têtes avec périodes
        data = [
            ["", f"Période du 01/05/{previous_year} au 30/04/{current_year}", "", "", "",
             f"Période du 01/05/{current_year} au {period_date.strftime('%d/%m/%Y')}", "", "", ""],
            ["Salarié", "Base", "Acquis", "Pris", "Restants",
             "Base", "Acquis", "Pris", "Restants", "Provision €"]
        ]
        
        total_provision = 0
        
        for prov in provisions_data:
            # Période précédente
            prev_base = prov.get('prev_period_base', 0)
            prev_acquis = prov.get('prev_period_acquis', 0)
            prev_pris = prov.get('prev_period_pris', 0)
            prev_restants = prev_acquis - prev_pris
            
            # Période courante
            curr_base = prov.get('current_period_base', 0)
            curr_acquis = prov.get('current_period_acquis', 0)
            curr_pris = prov.get('current_period_pris', 0)
            curr_restants = curr_acquis - curr_pris
            
            # Provision
            provision = prov.get('provision_amount', 0)
            total_provision += provision
            
            data.append([
                f"{prov.get('nom', '')} {prov.get('prenom', '')}",
                PDFStyles.format_currency(prev_base),
                f"{prev_acquis:.1f}",
                f"{prev_pris:.1f}",
                f"{prev_restants:.1f}",
                PDFStyles.format_currency(curr_base),
                f"{curr_acquis:.1f}",
                f"{curr_pris:.1f}",
                f"{curr_restants:.1f}",
                PDFStyles.format_currency(provision)
            ])
        
        # Total
        data.append([
            "TOTAL",
            "", "", "", "",
            "", "", "", "",
            PDFStyles.format_currency(total_provision)
        ])
        
        table = Table(data, colWidths=[3.5*cm, 2*cm, 1.5*cm, 1.5*cm, 1.5*cm,
                                       2*cm, 1.5*cm, 1.5*cm, 1.5*cm, 2.5*cm])
        table.setStyle(TableStyle([
            # Fusion des cellules d'en-tête pour les périodes
            ('SPAN', (1, 0), (4, 0)),
            ('SPAN', (5, 0), (8, 0)),
            ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor('#34495E')),
            ('TEXTCOLOR', (0, 0), (-1, 1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('ALIGN', (1, 2), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.grey),
            ('LINEBELOW', (0, -2), (-1, -2), 2, colors.black),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ECF0F1')),
        ]))
        
        return table
    
    def _create_provisions_summary(self, provisions_data: List[Dict]) -> Table:
        """Créer le tableau de synthèse des provisions"""
        
        total_restants_prev = sum(p.get('prev_period_acquis', 0) - p.get('prev_period_pris', 0) 
                                 for p in provisions_data)
        total_restants_curr = sum(p.get('current_period_acquis', 0) - p.get('current_period_pris', 0) 
                                 for p in provisions_data)
        total_provision = sum(p.get('provision_amount', 0) for p in provisions_data)
        
        data = [
            ["RÉSUMÉ", ""],
            ["", ""],
            ["Nombre de salariés", str(len(provisions_data))],
            ["Total jours restants (période précédente)", f"{total_restants_prev:.1f} jours"],
            ["Total jours restants (période courante)", f"{total_restants_curr:.1f} jours"],
            ["Total jours restants", f"{total_restants_prev + total_restants_curr:.1f} jours"],
            ["", ""],
            ["PROVISION TOTALE", PDFStyles.format_currency(total_provision)]
        ]
        
        table = Table(data, colWidths=[10*cm, 6*cm])
        table.setStyle(TableStyle([
            ('SPAN', (0, 0), (1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2980B9')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 2), (0, -1), 'LEFT'),
            ('ALIGN', (1, 2), (1, -1), 'RIGHT'),
            ('GRID', (0, 2), (-1, -2), 0.5, colors.grey),
            ('LINEBELOW', (0, -2), (-1, -2), 2, colors.black),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E74C3C')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
        ]))
        
        return table
    
    def _get_last_day_of_month(self, date: datetime) -> datetime:
        """Obtenir le dernier jour du mois"""
        last_day = calendar.monthrange(date.year, date.month)[1]
        return datetime(date.year, date.month, last_day)
    
    def _create_provision_footer(self, period: str) -> Paragraph:
        """Créer le pied de page du document de provision"""
        footer_text = f"""
        <para align="center" fontSize="8">
        Provision pour congés payés - Période {period}<br/>
        Document édité le {datetime.now().strftime("%d/%m/%Y à %H:%M")}<br/>
        Les montants incluent les charges sociales estimées<br/>
        Document comptable à conserver
        </para>
        """
        
        return Paragraph(footer_text, self.styles['CustomNormal'])

class PayJournalPDFGenerator:
    """Générateur du journal de paie (récapitulatif)"""
    
    def __init__(self, company_info: Dict, logo_path: Optional[str] = None):
        self.company_info = company_info
        self.logo_path = logo_path
        self.styles = PDFStyles.get_styles()
    
    def generate_pay_journal(self, employees_data: List[Dict], 
                            period: str, output_path: Optional[str] = None) -> io.BytesIO:
        """
        Générer le journal de paie consolidé
        
        Args:
            employees_data: Liste des données de tous les employés
            period: Période (format: "MM-YYYY")
            output_path: Chemin de sortie (optionnel)
        """
        if output_path:
            pdf_buffer = output_path
        else:
            pdf_buffer = io.BytesIO()
        
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            rightMargin=1*cm,
            leftMargin=1*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm
        )
        
        story = []
        
        # En-tête
        story.extend(self._create_journal_header(period))
        
        # Tableau des écritures comptables
        story.append(Paragraph("<b>JOURNAL DE PAIE</b>", self.styles['CustomHeading']))
        story.append(self._create_accounting_entries_table(employees_data, period))
        story.append(Spacer(1, 0.5*cm))
        
        # Récapitulatif par salarié
        story.append(PageBreak())
        story.append(Paragraph("<b>RÉCAPITULATIF PAR SALARIÉ</b>", self.styles['CustomHeading']))
        story.append(self._create_employee_summary_table(employees_data))
        story.append(Spacer(1, 0.5*cm))
        
        # Synthèse des charges
        story.append(Paragraph("<b>SYNTHÈSE DES COTISATIONS</b>", self.styles['CustomHeading']))
        story.append(self._create_charges_summary_table(employees_data))
        story.append(Spacer(1, 0.5*cm))
        
        # Totaux généraux
        story.append(self._create_totals_summary(employees_data))
        
        # Pied de page
        story.append(Spacer(1, 1*cm))
        story.append(self._create_journal_footer(period))
        
        doc.build(story)
        
        if not output_path:
            pdf_buffer.seek(0)
        
        return pdf_buffer
    
    def _create_journal_header(self, period: str) -> List:
        """Créer l'en-tête du journal"""
        elements = []
        
        # Logo et titre
        header_data = []
        if self.logo_path and Path(self.logo_path).exists():
            try:
                logo = Image(self.logo_path, width=3*cm, height=2*cm)
                header_data.append([logo, "JOURNAL DE PAIE", ""])
            except:
                header_data.append(["", "JOURNAL DE PAIE", ""])
        else:
            header_data.append(["", "JOURNAL DE PAIE", ""])
        
        header_table = Table(header_data, colWidths=[5*cm, 8*cm, 5*cm])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (1, 0), (1, 0), 16),
        ]))
        
        elements.append(header_table)
        
        # Informations de période et entreprise
        period_date = datetime.strptime(period, "%m-%Y")
        info_data = [
            [f"Entreprise: {self.company_info.get('name', '')}", 
             f"Période: {period_date.strftime('%B %Y')}"],
            [f"SIRET: {self.company_info.get('siret', '')}", 
             f"Date d'édition: {datetime.now().strftime('%d/%m/%Y')}"]
        ]
        
        info_table = Table(info_data, colWidths=[9*cm, 9*cm])
        info_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        
        elements.append(Spacer(1, 0.5*cm))
        elements.append(info_table)
        elements.append(Spacer(1, 0.5*cm))
        
        return elements
    
    def _create_accounting_entries_table(self, employees_data: List[Dict], period: str) -> Table:
        """Créer le tableau des écritures comptables"""
        
        # En-têtes
        data = [
            ["Compte", "Date", "Libellé", "Débit", "Crédit"]
        ]
        
        period_date = datetime.strptime(period, "%m-%Y")
        last_day = self._get_last_day_of_month(period_date)
        date_str = last_day.strftime("%d/%m/%Y")
        
        # Comptes de personnel (crédit)
        for emp in employees_data:
            data.append([
                "421000",
                date_str,
                f"{emp.get('nom', '')} {emp.get('prenom', '')}",
                "",
                PDFStyles.format_currency(emp.get('salaire_net', 0))
            ])
        
        # Acomptes (si applicable)
        total_acomptes = sum(emp.get('acomptes', 0) for emp in employees_data)
        if total_acomptes > 0:
            data.append([
                "425000",
                date_str,
                "Acomptes",
                "",
                PDFStyles.format_currency(total_acomptes)
            ])
        
        # Charges salariales
        total_car_sal = sum(self._get_charge_amount(emp, 'salariales', 'CAR') for emp in employees_data)
        total_ccss = sum(self._get_charge_amount(emp, 'salariales', 'CCSS') for emp in employees_data)
        total_assedic_sal = sum(self._get_charge_amount(emp, 'salariales', 'ASSEDIC_T1') + 
                                self._get_charge_amount(emp, 'salariales', 'ASSEDIC_T2') 
                                for emp in employees_data)
        
        if total_car_sal + total_ccss > 0:
            data.append([
                "431100",
                date_str,
                "Part salariale CAR/CCSS",
                "",
                PDFStyles.format_currency(total_car_sal + total_ccss)
            ])
        
        if total_assedic_sal > 0:
            data.append([
                "437300",
                date_str,
                "Part salariale ASSEDIC",
                "",
                PDFStyles.format_currency(total_assedic_sal)
            ])
        
        # Salaires bruts (débit)
        total_salaires = sum(emp.get('salaire_base', 0) for emp in employees_data)
        total_primes = sum(emp.get('prime', 0) for emp in employees_data)
        
        data.append([
            "641100",
            date_str,
            "Rémunérations brutes",
            PDFStyles.format_currency(total_salaires),
            ""
        ])
        
        if total_primes > 0:
            data.append([
                "641300",
                date_str,
                "Primes et gratifications",
                PDFStyles.format_currency(total_primes),
                ""
            ])
        
        # Charges patronales
        total_car_pat = sum(self._get_charge_amount(emp, 'patronales', 'CAR') for emp in employees_data)
        total_cmrc = sum(self._get_charge_amount(emp, 'patronales', 'CMRC') for emp in employees_data)
        total_assedic_pat = sum(self._get_charge_amount(emp, 'patronales', 'ASSEDIC_T1') + 
                                self._get_charge_amount(emp, 'patronales', 'ASSEDIC_T2') 
                                for emp in employees_data)
        
        if total_car_pat > 0:
            data.append([
                "645101",
                date_str,
                "Charges patronales CAR",
                PDFStyles.format_currency(total_car_pat),
                ""
            ])
        
        if total_cmrc > 0:
            data.append([
                "645312",
                date_str,
                "Charges patronales CMRC",
                PDFStyles.format_currency(total_cmrc),
                ""
            ])
        
        if total_assedic_pat > 0:
            data.append([
                "645400",
                date_str,
                "Charges patronales ASSEDIC",
                PDFStyles.format_currency(total_assedic_pat),
                ""
            ])
        
        # Totaux
        total_debit = (total_salaires + total_primes + total_car_pat + 
                      total_cmrc + total_assedic_pat)
        total_credit = (sum(emp.get('salaire_net', 0) for emp in employees_data) +
                       total_acomptes + total_car_sal + total_ccss + total_assedic_sal)
        
        data.append([
            "TOTAUX",
            "",
            "",
            PDFStyles.format_currency(total_debit),
            PDFStyles.format_currency(total_credit)
        ])
        
        table = Table(data, colWidths=[2.5*cm, 2.5*cm, 7*cm, 3*cm, 3*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (3, 1), (4, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.grey),
            ('LINEBELOW', (0, -2), (-1, -2), 2, colors.black),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ECF0F1')),
        ]))
        
        return table
    
    def _create_employee_summary_table(self, employees_data: List[Dict]) -> Table:
        """Créer le tableau récapitulatif par salarié"""
        
        data = [
            ["Matricule", "Nom Prénom", "Salaire Base", "Heures Sup", 
             "Primes", "Brut", "Charges Sal.", "Net à payer", "Charges Pat."]
        ]
        
        for emp in employees_data:
            total_hs = emp.get('montant_hs_125', 0) + emp.get('montant_hs_150', 0)
            
            data.append([
                emp.get('matricule', ''),
                f"{emp.get('nom', '')} {emp.get('prenom', '')}",
                PDFStyles.format_currency(emp.get('salaire_base', 0)),
                PDFStyles.format_currency(total_hs),
                PDFStyles.format_currency(emp.get('prime', 0)),
                PDFStyles.format_currency(emp.get('salaire_brut', 0)),
                PDFStyles.format_currency(emp.get('total_charges_salariales', 0)),
                PDFStyles.format_currency(emp.get('salaire_net', 0)),
                PDFStyles.format_currency(emp.get('total_charges_patronales', 0))
            ])
        
        # Totaux
        data.append([
            "TOTAUX",
            "",
            PDFStyles.format_currency(sum(emp.get('salaire_base', 0) for emp in employees_data)),
            PDFStyles.format_currency(sum(emp.get('montant_hs_125', 0) + emp.get('montant_hs_150', 0) 
                                         for emp in employees_data)),
            PDFStyles.format_currency(sum(emp.get('prime', 0) for emp in employees_data)),
            PDFStyles.format_currency(sum(emp.get('salaire_brut', 0) for emp in employees_data)),
            PDFStyles.format_currency(sum(emp.get('total_charges_salariales', 0) for emp in employees_data)),
            PDFStyles.format_currency(sum(emp.get('salaire_net', 0) for emp in employees_data)),
            PDFStyles.format_currency(sum(emp.get('total_charges_patronales', 0) for emp in employees_data))
        ])
        
        table = Table(data, colWidths=[2*cm, 3.5*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498DB')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.grey),
            ('LINEBELOW', (0, -2), (-1, -2), 2, colors.black),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E8F4F8')),
        ]))
        
        return table
    
    def _create_charges_summary_table(self, employees_data: List[Dict]) -> Table:
        """Créer le tableau de synthèse des cotisations"""
        
        # Calculer les totaux par type de cotisation
        charges_summary = {}
        
        for emp in employees_data:
            details = emp.get('details_charges', {})
            
            # Charges salariales
            for key, value in details.get('charges_salariales', {}).items():
                if key not in charges_summary:
                    charges_summary[key] = {'salariale': 0, 'patronale': 0}
                charges_summary[key]['salariale'] += value
            
            # Charges patronales
            for key, value in details.get('charges_patronales', {}).items():
                if key not in charges_summary:
                    charges_summary[key] = {'salariale': 0, 'patronale': 0}
                charges_summary[key]['patronale'] += value
        
        data = [
            ["Cotisation", "Part Salariale", "Part Patronale", "Total"]
        ]
        
        total_sal = 0
        total_pat = 0
        
        for cotisation, values in sorted(charges_summary.items()):
            sal = values['salariale']
            pat = values['patronale']
            total_sal += sal
            total_pat += pat
            
            data.append([
                cotisation,
                PDFStyles.format_currency(sal),
                PDFStyles.format_currency(pat),
                PDFStyles.format_currency(sal + pat)
            ])
        
        # Total général
        data.append([
            "TOTAL",
            PDFStyles.format_currency(total_sal),
            PDFStyles.format_currency(total_pat),
            PDFStyles.format_currency(total_sal + total_pat)
        ])
        
        table = Table(data, colWidths=[6*cm, 4*cm, 4*cm, 4*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#9B59B6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.grey),
            ('LINEBELOW', (0, -2), (-1, -2), 2, colors.black),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E8DAEF')),
        ]))
        
        return table
    
    def _create_totals_summary(self, employees_data: List[Dict]) -> Table:
        """Créer le tableau de synthèse des totaux"""
        
        total_brut = sum(emp.get('salaire_brut', 0) for emp in employees_data)
        total_charges_sal = sum(emp.get('total_charges_salariales', 0) for emp in employees_data)
        total_charges_pat = sum(emp.get('total_charges_patronales', 0) for emp in employees_data)
        total_net = sum(emp.get('salaire_net', 0) for emp in employees_data)
        cout_total = total_brut + total_charges_pat
        
        data = [
            ["SYNTHÈSE GÉNÉRALE", ""],
            ["Nombre de salariés", str(len(employees_data))],
            ["Masse salariale brute", PDFStyles.format_currency(total_brut)],
            ["Total charges salariales", PDFStyles.format_currency(total_charges_sal)],
            ["Total charges patronales", PDFStyles.format_currency(total_charges_pat)],
            ["Total net à payer", PDFStyles.format_currency(total_net)],
            ["COÛT TOTAL EMPLOYEUR", PDFStyles.format_currency(cout_total)]
        ]
        
        table = Table(data, colWidths=[10*cm, 6*cm])
        table.setStyle(TableStyle([
            ('SPAN', (0, 0), (1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('GRID', (0, 1), (-1, -2), 0.5, colors.grey),
            ('LINEBELOW', (0, -2), (-1, -2), 2, colors.black),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#27AE60')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
        ]))
        
        return table
    
    def _get_charge_amount(self, emp: Dict, type_charge: str, key: str) -> float:
        """Obtenir le montant d'une charge spécifique"""
        details = emp.get('details_charges', {})
        charges = details.get(f'charges_{type_charge}', {})
        return charges.get(key, 0)
    
    def _get_last_day_of_month(self, date: datetime) -> datetime:
        """Obtenir le dernier jour du mois"""
        last_day = calendar.monthrange(date.year, date.month)[1]
        return datetime(date.year, date.month, last_day)
    
    def _create_journal_footer(self, period: str) -> Paragraph:
        """Créer le pied de page du journal"""
        footer_text = f"""
        <para align="center" fontSize="8">
        Journal de paie - Période {period}<br/>
        Document édité le {datetime.now().strftime("%d/%m/%Y à %H:%M")}<br/>
        Document comptable à conserver
        </para>
        """
        
        return Paragraph(footer_text, self.styles['CustomNormal'])

class ChargesSocialesPDFGenerator:
    """Générateur de PDF pour l'état des charges sociales"""

    def __init__(self, company_info: Dict, logo_path: Optional[str] = None):
        self.company_info = company_info
        self.logo_path = logo_path
        self.styles = PDFStyles.get_styles()

    def generate_charges_sociales(self, employees_data: List[Dict],
                                  period: str, output_path: Optional[str] = None) -> io.BytesIO:
        """
        Générer l'état des charges sociales

        Args:
            employees_data: Liste des données de tous les employés avec details_charges
            period: Période (format: "MM-YYYY")
            output_path: Chemin de sortie (optionnel)
        """
        if output_path:
            pdf_buffer = output_path
        else:
            pdf_buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            rightMargin=1*cm,
            leftMargin=1*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm
        )

        story = []

        # En-tête
        story.extend(self._create_header(period))

        # Agrégation des charges par code
        charges_aggregated = self._aggregate_charges(employees_data)

        # Grouper par organisme (pour l'instant juste liste les charges)
        # TODO: ajouter le mapping organisme quand disponible
        story.append(self._create_charges_table(charges_aggregated, period))
        story.append(Spacer(1, 0.5*cm))

        # Total global
        story.append(self._create_total_summary(charges_aggregated))

        # Pied de page
        story.append(Spacer(1, 1*cm))
        story.append(self._create_footer(period))

        doc.build(story)

        if not output_path:
            pdf_buffer.seek(0)

        return pdf_buffer

    def _create_header(self, period: str) -> List:
        """Créer l'en-tête du document"""
        elements = []

        # Titre principal
        title = Paragraph("<b>État des Charges Sociales</b>",
                         ParagraphStyle('CustomTitle', fontSize=16, alignment=1))
        elements.append(title)
        elements.append(Spacer(1, 0.5*cm))

        # Informations de période
        period_date = datetime.strptime(period, "%m-%Y")
        start_date = period_date.replace(day=1)
        last_day = (period_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

        info_data = [
            [f"Période de", start_date.strftime('%d/%m/%Y'), "à", last_day.strftime('%d/%m/%Y')],
            [f"Organisme de", "001", "à", "105"],  # TODO: dynamique basé sur données
            [f"Établissement de", "<<Tous>>", "à", ""],
            [f"Devises", "", "", "Euro"]
        ]

        info_table = Table(info_data, colWidths=[4*cm, 3*cm, 1.5*cm, 3*cm])
        info_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ]))

        elements.append(info_table)
        elements.append(Spacer(1, 0.5*cm))

        return elements

    def _aggregate_charges(self, employees_data: List[Dict]) -> Dict:
        """
        Agréger les charges par code

        Returns:
            Dict avec structure: {
                'charge_code': {
                    'description': str,
                    'nbre_salarie': int,
                    'base_cotisee': float,
                    'taux_sal': float,
                    'taux_pat': float,
                    'montant_sal': float,
                    'montant_pat': float,
                    'homme': int,
                    'femme': int
                }
            }
        """
        charges_agg = {}
        rates_csv = self._load_rates()

        for emp in employees_data:
            details = emp.get('details_charges', {})
            if not isinstance(details, dict):
                continue

            sexe = emp.get('sexe', '').upper()

            charges_sal = details.get('charges_salariales', {})
            charges_pat = details.get('charges_patronales', {})

            # Traiter charges salariales
            for code, montant in (charges_sal.items() if isinstance(charges_sal, dict) else []):
                if montant == 0:
                    continue

                if code not in charges_agg:
                    rate_info = rates_csv.get(code, {})
                    charges_agg[code] = {
                        'description': rate_info.get('description', code),
                        'nbre_salarie': 0,
                        'base_cotisee': 0,
                        'taux_sal': rate_info.get('taux_sal', 0),
                        'taux_pat': rate_info.get('taux_pat', 0),
                        'montant_sal': 0,
                        'montant_pat': 0,
                        'homme': 0,
                        'femme': 0
                    }

                # Estimer la base à partir du montant et du taux
                taux_sal = charges_agg[code]['taux_sal']
                if taux_sal > 0:
                    base = montant / (taux_sal / 100)
                    charges_agg[code]['base_cotisee'] += base

                charges_agg[code]['montant_sal'] += montant
                charges_agg[code]['nbre_salarie'] += 1

                if sexe == 'H':
                    charges_agg[code]['homme'] += 1
                elif sexe == 'F':
                    charges_agg[code]['femme'] += 1

            # Traiter charges patronales
            for code, montant in (charges_pat.items() if isinstance(charges_pat, dict) else []):
                if montant == 0:
                    continue

                if code not in charges_agg:
                    rate_info = rates_csv.get(code, {})
                    charges_agg[code] = {
                        'description': rate_info.get('description', code),
                        'nbre_salarie': 0,
                        'base_cotisee': 0,
                        'taux_sal': rate_info.get('taux_sal', 0),
                        'taux_pat': rate_info.get('taux_pat', 0),
                        'montant_sal': 0,
                        'montant_pat': 0,
                        'homme': 0,
                        'femme': 0
                    }

                # Estimer la base à partir du montant et du taux
                taux_pat = charges_agg[code]['taux_pat']
                if taux_pat > 0 and charges_agg[code]['base_cotisee'] == 0:
                    base = montant / (taux_pat / 100)
                    charges_agg[code]['base_cotisee'] += base

                charges_agg[code]['montant_pat'] += montant

                # Ne compter le salarié qu'une fois (déjà compté dans salariales)
                if code not in charges_sal or charges_sal.get(code, 0) == 0:
                    charges_agg[code]['nbre_salarie'] += 1
                    if sexe == 'H':
                        charges_agg[code]['homme'] += 1
                    elif sexe == 'F':
                        charges_agg[code]['femme'] += 1

        return charges_agg

    def _load_rates(self) -> Dict:
        """Charger les taux depuis le CSV pour avoir les descriptions"""
        rates = {}
        csv_path = Path("config") / "payroll_rates.csv"

        if csv_path.exists():
            try:
                df = pl.read_csv(csv_path)
                for row in df.iter_rows(named=True):
                    if row.get('category') == 'CHARGE':
                        code = row.get('code')
                        type_charge = row.get('type', '').upper()

                        if code not in rates:
                            rates[code] = {
                                'description': row.get('description', code),
                                'taux_sal': 0,
                                'taux_pat': 0
                            }

                        taux = row.get('taux_2025', 0)  # TODO: année dynamique
                        if type_charge == 'SALARIAL':
                            rates[code]['taux_sal'] = taux
                        elif type_charge == 'PATRONAL':
                            rates[code]['taux_pat'] = taux
            except Exception as e:
                logger.warning(f"Erreur chargement rates CSV: {e}")

        return rates

    def _create_charges_table(self, charges_agg: Dict, period: str) -> Table:
        """Créer le tableau des charges"""

        # En-têtes
        data = [[
            Paragraph("<b>CODE</b>", self.styles['CustomSmall']),
            Paragraph("<b>BASE COTISEE</b>", self.styles['CustomSmall']),
            Paragraph("<b>NBRE<br/>SALARIE</b>", self.styles['CustomSmall']),
            Paragraph("<b>BASE</b>", self.styles['CustomSmall']),
            Paragraph("<b>TAUX<br/>SAL.</b>", self.styles['CustomSmall']),
            Paragraph("<b>TAUX<br/>PAT.</b>", self.styles['CustomSmall']),
            Paragraph("<b>TAUX<br/>GLO.</b>", self.styles['CustomSmall']),
            Paragraph("<b>MONTANT<br/>SALARIAL</b>", self.styles['CustomSmall']),
            Paragraph("<b>MONTANT<br/>PATRONAL</b>", self.styles['CustomSmall']),
            Paragraph("<b>MONTANT<br/>GLOBAL</b>", self.styles['CustomSmall'])
        ]]

        # Lignes de données
        total_sal = 0
        total_pat = 0
        total_homme = 0
        total_femme = 0

        for code, values in sorted(charges_agg.items()):
            taux_sal = values['taux_sal']
            taux_pat = values['taux_pat']
            taux_glo = taux_sal + taux_pat

            montant_sal = values['montant_sal']
            montant_pat = values['montant_pat']
            montant_glo = montant_sal + montant_pat

            total_sal += montant_sal
            total_pat += montant_pat
            total_homme += values['homme']
            total_femme += values['femme']

            data.append([
                f"{code}\n{values['description']}",
                str(values['nbre_salarie']),
                PDFStyles.format_currency(values['base_cotisee']),
                PDFStyles.format_currency(values['base_cotisee']),
                f"{taux_sal:.5f}" if taux_sal > 0 else "",
                f"{taux_pat:.5f}" if taux_pat > 0 else "",
                f"{taux_glo:.5f}" if taux_glo > 0 else "",
                PDFStyles.format_currency(montant_sal) if montant_sal > 0 else "",
                PDFStyles.format_currency(montant_pat) if montant_pat > 0 else "",
                PDFStyles.format_currency(montant_glo)
            ])

        # Ligne de total
        data.append([
            Paragraph(f"<b>TOTAL GLOBAL</b><br/>Homme : {total_homme}  Femme : {total_femme}",
                     self.styles['CustomSmall']),
            "", "", "", "", "", "",
            Paragraph(f"<b>{PDFStyles.format_currency(total_sal)}</b>", self.styles['CustomSmall']),
            Paragraph(f"<b>{PDFStyles.format_currency(total_pat)}</b>", self.styles['CustomSmall']),
            Paragraph(f"<b>{PDFStyles.format_currency(total_sal + total_pat)}</b>", self.styles['CustomSmall'])
        ])

        table = Table(data, colWidths=[
            3.5*cm, 1*cm, 2*cm, 2*cm, 1.2*cm, 1.2*cm, 1.2*cm, 2*cm, 2*cm, 2*cm
        ])

        table.setStyle(TableStyle([
            # En-tête
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#CCCCCC')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),

            # Corps
            ('FONTSIZE', (0, 1), (-1, -2), 7),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),

            # Ligne totale
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E6E6E6')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),

            # Grille
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]))

        return table

    def _create_total_summary(self, charges_agg: Dict) -> Table:
        """Créer le résumé des totaux"""
        total_sal = sum(v['montant_sal'] for v in charges_agg.values())
        total_pat = sum(v['montant_pat'] for v in charges_agg.values())
        total_glo = total_sal + total_pat

        data = [[
            "TOTAL GLOBAL",
            PDFStyles.format_currency(total_sal),
            PDFStyles.format_currency(total_pat),
            PDFStyles.format_currency(total_glo)
        ]]

        table = Table(data, colWidths=[10*cm, 3*cm, 3*cm, 3*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1a5f9e')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]))

        return table

    def _create_footer(self, period: str) -> Paragraph:
        """Créer le pied de page"""
        period_date = datetime.strptime(period, "%m-%Y")
        footer_text = f"""
        <para align=center>
        Imprimé le {datetime.now().strftime('%d/%m/%Y à %H:%M')}<br/>
        Par {self.company_info.get('name', '')}<br/>
        État des charges sociales - Période {period_date.strftime('%B %Y')}
        </para>
        """

        return Paragraph(footer_text, self.styles['CustomNormal'])

class PDFGeneratorService:
    """Service principal pour gérer la génération de tous les PDFs"""
    
    def __init__(self, company_info: Dict, logo_path: Optional[str] = None):
        """
        Initialiser le service de génération PDF
        
        Args:
            company_info: Dictionnaire avec les informations de l'entreprise
            logo_path: Chemin vers le logo de l'entreprise (optionnel)
        """
        self.company_info = company_info
        self.logo_path = logo_path
        
        # Initialiser les générateurs
        self.paystub_generator = PaystubPDFGenerator(company_info, logo_path)
        self.journal_generator = PayJournalPDFGenerator(company_info, logo_path)
        self.pto_generator = PTOProvisionPDFGenerator(company_info, logo_path)
        self.charges_sociales_generator = ChargesSocialesPDFGenerator(company_info, logo_path)
    
    def generate_monthly_documents(self, employees_df: pl.DataFrame, 
                                  period: str, output_dir: Optional[Path] = None) -> Dict[str, any]:
        """
        Générer tous les documents pour une période mensuelle
        
        Args:
            employees_df: DataFrame avec les données de tous les employés
            period: Période au format "MM-YYYY"
            output_dir: Répertoire de sortie (optionnel)
        
        Returns:
            Dictionnaire avec les buffers PDF générés
        """
        documents = {}
        
        # Convertir DataFrame en liste de dictionnaires
        employees_data = employees_df.to_dict('records')
        
        # Préparer les données de période
        period_date = datetime.strptime(period, "%m-%Y")
        period_start = period_date.replace(day=1).strftime("%d/%m/%Y")
        last_day = calendar.monthrange(period_date.month, period_date.year)[1]
        period_end = period_date.replace(day=last_day).strftime("%d/%m/%Y")
        payment_date = period_end  # Paiement le dernier jour du mois

        # 1. Générer les bulletins individuels
        paystubs = []
        for emp_data in employees_data:
            # Ajouter les informations de période
            emp_data['period_start'] = period_start
            emp_data['period_end'] = period_end
            emp_data['payment_date'] = payment_date
            
            # Calculer les cumuls annuels (simplifiés pour cet exemple)
            emp_data['cumul_brut_annuel'] = self._calculate_yearly_cumul(
                employees_df, emp_data['matricule'], 'salaire_brut', period_date
            )
            emp_data['cumul_net_annuel'] = self._calculate_yearly_cumul(
                employees_df, emp_data['matricule'], 'salaire_net', period_date
            )
            emp_data['cumul_charges_sal_annuel'] = self._calculate_yearly_cumul(
                employees_df, emp_data['matricule'], 'total_charges_salariales', period_date
            )
            
            # Générer le bulletin
            if output_dir:
                output_path = output_dir / f"bulletin_{emp_data['matricule']}_{period}.pdf"
                self.paystub_generator.generate_paystub(emp_data, str(output_path))
            else:
                paystub_buffer = self.paystub_generator.generate_paystub(emp_data)
                paystubs.append({
                    'matricule': emp_data['matricule'],
                    'nom': emp_data['nom'],
                    'prenom': emp_data['prenom'],
                    'buffer': paystub_buffer
                })
        
        documents['paystubs'] = paystubs
        
        # 2. Générer le journal de paie
        if output_dir:
            journal_path = output_dir / f"journal_paie_{period}.pdf"
            self.journal_generator.generate_pay_journal(employees_data, period, str(journal_path))
        else:
            journal_buffer = self.journal_generator.generate_pay_journal(employees_data, period)
            documents['journal'] = journal_buffer
        
        # 3. Générer la provision pour congés payés
        provisions_data = self._prepare_provisions_data(employees_df, period_date)
        
        if output_dir:
            pto_path = output_dir / f"provision_cp_{period}.pdf"
            self.pto_generator.generate_pto_provision(provisions_data, period, str(pto_path))
        else:
            pto_buffer = self.pto_generator.generate_pto_provision(provisions_data, period)
            documents['pto_provision'] = pto_buffer
        
        return documents
    
    def generate_paystub_batch(self, employees_df: pl.DataFrame, 
                              period: str, output_dir: Path) -> List[str]:
        """
        Générer un lot de bulletins de paie
        
        Args:
            employees_df: DataFrame avec les données des employés
            period: Période au format "MM-YYYY"
            output_dir: Répertoire de sortie
        
        Returns:
            Liste des chemins de fichiers générés
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files = []
        
        employees_data = employees_df.to_dict('records')
        
        for emp_data in employees_data:
            output_path = output_dir / f"bulletin_{emp_data['matricule']}_{period}.pdf"
            self.paystub_generator.generate_paystub(emp_data, str(output_path))
            generated_files.append(str(output_path))
        
        return generated_files
    
    def _calculate_yearly_cumul(self, df: pl.DataFrame, matricule: str, 
                            field: str, current_date: datetime) -> float:
        """
        Calculer le cumul annuel pour un employé
        
        Note: Dans une implémentation réelle, ceci devrait chercher dans l'historique
        """
        # Simplification: on multiplie par le nombre de mois écoulés
        months_elapsed = current_date.month
        emp_row = df.filter(pl.col('matricule') == matricule)
        if emp_row.height > 0:
            monthly_value = emp_row.select(pl.col(field)).item(0, 0) if field in emp_row.columns else 0
            return monthly_value * months_elapsed
        return 0
    
    def _prepare_provisions_data(self, employees_df: pl.DataFrame, 
                            period_date: datetime) -> List[Dict]:
        """
        Préparer les données de provision pour congés payés
        """
        provisions = []
        
        for emp in employees_df.iter_rows(named=True):
            # Calcul simplifié des droits CP
            months_worked = period_date.month  # Simplification
            
            provision = {
                'matricule': emp.get('matricule', ''),
                'nom': emp.get('nom', ''),
                'prenom': emp.get('prenom', ''),
                
                # Période précédente (mai N-1 à avril N)
                'prev_period_base': emp.get('salaire_base', 0) * 12,
                'prev_period_acquis': 30.0,  # 30 jours max par an
                'prev_period_pris': emp.get('cp_pris_annee_precedente', 10),  # Exemple
                
                # Période courante (mai N à date actuelle)
                'current_period_base': emp.get('salaire_base', 0) * months_worked,
                'current_period_acquis': months_worked * 2.5,  # 2.5 jours par mois
                'current_period_pris': emp.get('cp_pris_annee_courante', 0),
                
                # Provision (salaire journalier * jours restants * 1.45 pour charges)
                'provision_amount': 0
            }
            
            # Calculer la provision
            total_restants = (provision['prev_period_acquis'] - provision['prev_period_pris'] +
                            provision['current_period_acquis'] - provision['current_period_pris'])
            
            salaire_journalier = emp.get('salaire_base', 0) / 30
            provision['provision_amount'] = salaire_journalier * total_restants * 1.45
            
            provisions.append(provision)
        
        return provisions
    
    def generate_email_ready_paystub(self, employee_data: Dict, period: str) -> io.BytesIO:
        """
        Générer un bulletin de paie prêt pour l'envoi par email
        
        Args:
            employee_data: Données de l'employé
            period: Période au format "MM-YYYY"
        
        Returns:
            Buffer PDF prêt pour l'envoi
        """
        
        # Ajouter les informations de période
        period_date = datetime.strptime(period, "%m-%Y")
        period_start = period_date.replace(day=1).strftime("%d/%m/%Y")
        last_day = calendar.monthrange(period_date.year, period_date.month)[1]
        period_end = period_date.replace(day=last_day).strftime("%d/%m/%Y")
        
        employee_data['period_start'] = period_start
        employee_data['period_end'] = period_end
        employee_data['payment_date'] = period_end
        
        # Générer le PDF
        return self.paystub_generator.generate_paystub(employee_data)

    def generate_charges_sociales_pdf(self, employees_data: List[Dict], period: str) -> io.BytesIO:
        """
        Générer l'état des charges sociales

        Args:
            employees_data: Liste des données de tous les employés avec details_charges
            period: Période au format "MM-YYYY"

        Returns:
            Buffer PDF de l'état des charges sociales
        """
        return self.charges_sociales_generator.generate_charges_sociales(employees_data, period)

# Test function
def test_pdf_generation():
    """Function to test PDF generation"""
    
    # Company configuration
    company_info = {
        'name': 'CARAX MONACO',
        'siret': '763000000',
        'address': '98000 MONACO'
    }
    
    # Example data
    # add in the period_start, period_end, payment_date for testing
    test_employee = {
        'matricule': 'S000000001',
        'ccss_number': '555174',
        'nom': 'DUPONT',
        'prenom': 'Jean',
        'emploi': 'Sales Assistant',
        'classification': 'Non cadre',
        'period_start': '01/05/2024',
        'period_end': '31/05/2024',
        'payment_date': '31/05/2024',
        'salaire_base': 3500.00,
        'base_heures': 169,
        'taux_horaire': 20.71,
        'heures_sup_125': 10,
        'montant_hs_125': 258.88,
        'heures_sup_150': 5,
        'montant_hs_150': 155.33,
        'prime': 500,
        'type_prime': 'performance',
        'heures_jours_feries': 7,
        'montant_jours_feries': 289.94,
        'salaire_brut': 4704.15,
        'total_charges_salariales': 1035.00,
        'total_charges_patronales': 1646.45,
        'salaire_net': 3669.15,
        'cout_total_employeur': 6350.60,
        'cumul_brut': 30094.22,
        'cumul_base_ss': 25398.15, 
        'cumul_net_percu': 25398.15,
        'cumul_charges_sal': 4451.27,
        'cumul_charges_pat': 10749.62,
        'cp_acquis_n1': 41.00,  # Previous year acquired
        'cp_pris_n1': 7.00,  # Previous year taken
        'cp_restants_n1': 34.00,  # Previous year remaining
        'cp_acquis_n': 2.08,  # Current year acquired
        'cp_pris_n': 2.08,  # Current year taken
        'cp_restants_n': 0,  # Current year remaining
        'pays_residence': 'MONACO',
        'details_charges': {
            'charges_salariales': {
                'CAR': 322.33,
                'CCSS': 694.36,
                'ASSEDIC_T1': 82.27,
                'RETRAITE_COMP_T1': 107.98
            },
            'charges_patronales': {
                'CAR': 392.80,
                'CMRC': 245.56,
                'ASSEDIC_T1': 138.83,
                'PREVOYANCE': 70.56
            }
        }
    }
    
    # Create service
    pdf_service = PDFGeneratorService(company_info)
    
    # Generate a paystub
    paystub_pdf = pdf_service.paystub_generator.generate_paystub(test_employee)
    
    # Save test file
    with open("test_bulletin.pdf", "wb") as f:
        f.write(paystub_pdf.getvalue())
    
    print("Test PDF generated: test_bulletin.pdf")
    
    return paystub_pdf

if __name__ == "__main__":
    test_pdf_generation()
