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
from reportlab.lib.pagesizes import A4, landscape
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
import json
from datetime import datetime, date, timedelta
from pathlib import Path
import io
from typing import Dict, List, Optional, Tuple
import locale
import calendar
import logging
import getpass

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

        # Style pour le texte petit (tableaux)
        styles.add(ParagraphStyle(
            name='CustomSmall',
            parent=styles['Normal'],
            fontSize=7,
            leading=9,
            alignment=TA_CENTER
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
        'prime_non_cotisable': '2070',
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
    
    def generate_paystub(self, employee_data: Dict, output_path: Optional[str] = None,
                        password: Optional[str] = None) -> io.BytesIO:
        """Generate a compact single-page paystub"""

        # Ensure required data fields
        self._prepare_employee_data(employee_data)

        # Create buffer or file
        if output_path:
            pdf_buffer = output_path
        else:
            pdf_buffer = io.BytesIO()

        # Create document with smaller margins for compact layout
        doc_kwargs = {
            'pagesize': A4,
            'rightMargin': 0.8*cm,
            'leftMargin': 0.8*cm,
            'topMargin': 1*cm,
            'bottomMargin': 0.8*cm
        }

        # Add password protection if specified
        if password:
            doc_kwargs['encrypt'] = password

        doc = SimpleDocTemplate(pdf_buffer, **doc_kwargs)
        
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

        # Prime non cotisable (added AFTER charges, exempt from social contributions)
        if employee_data.get('prime_non_cotisable', 0) > 0:
            data.append([
                f"{self.RUBRIC_CODES['prime_non_cotisable']} Prime non cotisable",
                "",
                "",
                PDFStyles.format_currency(employee_data.get('prime_non_cotisable', 0)),
                "",
                "",
                ""
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
    """Générateur du document de provision pour congés payés format"""

    # Color scheme matching paystub
    COLORS = {
        'primary_blue': colors.HexColor('#1e3a8a'),      # Dark blue for headers
        'secondary_blue': colors.HexColor('#3b82f6'),    # Medium blue for accents
        'light_blue': colors.HexColor('#dbeafe'),        # Light blue for backgrounds
        'very_light_blue': colors.HexColor('#f0f9ff'),   # Very light blue
        'text_dark': colors.HexColor('#1e293b'),         # Dark text
        'text_gray': colors.HexColor('#64748b'),         # Gray text
        'border_gray': colors.HexColor('#e2e8f0')        # Light gray for borders
    }

    def __init__(self, company_info: Dict, logo_path: Optional[str] = None):
        self.company_info = company_info
        self.logo_path = logo_path
        self.styles = PDFStyles.get_styles()
    
    def generate_pto_provision(self, provisions_data: List[Dict],
                              period: str, output_path: Optional[str] = None,
                              password: Optional[str] = None) -> io.BytesIO:
        """
        Générer le document de provision pour congés payés format

        Args:
            provisions_data: Liste des provisions par employé
            period: Période (format: "MM-YYYY")
            output_path: Chemin de sortie (optionnel)
            password: Mot de passe pour protéger le PDF (optionnel)
        """
        if output_path:
            pdf_buffer = output_path
        else:
            pdf_buffer = io.BytesIO()

        # Use landscape A4
        doc_kwargs = {
            'pagesize': landscape(A4),
            'rightMargin': 1*cm,
            'leftMargin': 1*cm,
            'topMargin': 1.5*cm,
            'bottomMargin': 2*cm
        }

        # Add password protection if specified
        if password:
            doc_kwargs['encrypt'] = password

        doc = SimpleDocTemplate(pdf_buffer, **doc_kwargs)

        story = []

        # Header
        story.append(self._create_provision_header(period))
        story.append(Spacer(1, 0.5*cm))

        # Main provisions table
        story.append(self._create_provisions_table(provisions_data, period))
        story.append(Spacer(1, 0.3*cm))

        # Footer note
        story.append(self._create_footer_note())

        doc.build(story, onFirstPage=self._add_footer, onLaterPages=self._add_footer)

        if not output_path:
            pdf_buffer.seek(0)

        return pdf_buffer

    def _create_provision_header(self, period: str) -> KeepTogether:
        """Créer l'en-tête du document format"""
        period_date = datetime.strptime(period, "%m-%Y")
        last_day = self._get_last_day_of_month(period_date)

        elements = []

        # Create title with underline using table
        title_data = [["Provision pour congés payés"]]
        title_table = Table(title_data, colWidths=[26*cm])
        title_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 16),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLORS['primary_blue']),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('LINEBELOW', (0, 0), (-1, -1), 1.5, self.COLORS['primary_blue']),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(title_table)
        elements.append(Spacer(1, 0.3*cm))

        # Header info row
        etablissement = self.company_info.get('etablissement', '169')
        company_name = self.company_info.get('name', '')

        info_data = [[
            f"Etablissement(s)  {etablissement}",
            "Devises  Euro",
            f"Date d'arrêté  {last_day.strftime('%d/%m/%Y')}"
        ]]

        info_table = Table(info_data, colWidths=[8*cm, 8*cm, 8*cm])
        info_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLORS['text_dark']),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.3*cm))

        # Etablissement section
        etab_style = ParagraphStyle(
            'EtabSection',
            parent=self.styles['CustomNormal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            alignment=TA_LEFT,
            textColor=self.COLORS['text_dark'],
            spaceAfter=8
        )
        etab_text = Paragraph(f"Etablissement : {etablissement}    {company_name}", etab_style)
        elements.append(etab_text)

        return KeepTogether(elements)
    
    def _create_provisions_table(self, provisions_data: List[Dict], period: str) -> Table:
        """Créer le tableau des provisions format"""

        period_date = datetime.strptime(period, "%m-%Y")
        last_day = self._get_last_day_of_month(period_date)

        # Calculate period dates
        current_year = period_date.year
        prev_year_start = f"01/05/{current_year - 2}"
        prev_year_end = f"30/04/{current_year - 1}"
        curr_year_start = f"01/05/{current_year - 1}"
        curr_year_end = f"30/04/{current_year}"
        final_start = f"01/05/{current_year}"
        final_end = last_day.strftime('%d/%m/%Y')

        # Header rows
        data = [
            # Row 1: Period headers (merged cells)
            ["Salarié",
             f"Reliquat au {prev_year_start}", "", "",
             f"Période du {curr_year_start} au {curr_year_end}", "", "", "", "",
             f"Période du {final_start} au {final_end}", "", "", "", "", ""],
            # Row 2: Column headers
            ["",
             "Base", "Mois", "Restants",
             "Base", "Mois", "Acquis", "Pris", "Restants",
             "Base", "Mois", "Acquis", "Pris", "Restants", "Provisions"]
        ]

        # Totals accumulators
        totals = {
            'rel_base': 0, 'rel_mois': 0, 'rel_restants': 0,
            'p1_base': 0, 'p1_mois': 0, 'p1_acquis': 0, 'p1_pris': 0, 'p1_restants': 0,
            'p2_base': 0, 'p2_mois': 0, 'p2_acquis': 0, 'p2_pris': 0, 'p2_restants': 0,
            'provisions': 0
        }

        # Employee rows
        for emp in provisions_data:
            matricule = emp.get('matricule', '')
            nom = emp.get('nom', '')
            prenom = emp.get('prenom', '')

            # Reliquat (previous period carryover)
            rel_base = emp.get('reliquat_base', 0)
            rel_mois = emp.get('reliquat_mois', 0)
            rel_restants = emp.get('reliquat_restants', 0)

            # Period 1 (N-1 year)
            p1_base = emp.get('p1_base', 0)
            p1_mois = emp.get('p1_mois', 0)
            p1_acquis = emp.get('cp_acquis_n1', 0)
            p1_pris = emp.get('cp_pris_n1', 0)
            p1_restants = emp.get('cp_restants_n1', 0)

            # Period 2 (current year)
            p2_base = emp.get('p2_base', 0)
            p2_mois = emp.get('p2_mois', 0)
            p2_acquis = emp.get('cp_acquis_n', 0)
            p2_pris = emp.get('cp_pris_n', 0)
            p2_restants = emp.get('cp_restants_n', 0)

            # Provision
            provision = emp.get('provision_amount', 0)

            # Update totals
            totals['rel_base'] += rel_base
            totals['rel_mois'] += rel_mois
            totals['rel_restants'] += rel_restants
            totals['p1_base'] += p1_base
            totals['p1_mois'] += p1_mois
            totals['p1_acquis'] += p1_acquis
            totals['p1_pris'] += p1_pris
            totals['p1_restants'] += p1_restants
            totals['p2_base'] += p2_base
            totals['p2_mois'] += p2_mois
            totals['p2_acquis'] += p2_acquis
            totals['p2_pris'] += p2_pris
            totals['p2_restants'] += p2_restants
            totals['provisions'] += provision

            data.append([
                f"{matricule} {nom} {prenom}",
                PDFStyles.format_currency(rel_base) if rel_base > 0 else "",
                f"{rel_mois:.2f}" if rel_mois > 0 else "",
                f"{rel_restants:.2f}" if rel_restants > 0 else "",
                PDFStyles.format_currency(p1_base) if p1_base > 0 else "",
                f"{p1_mois:.2f}" if p1_mois > 0 else "",
                f"{p1_acquis:.2f}" if p1_acquis > 0 else "",
                f"{p1_pris:.2f}" if p1_pris > 0 else "",
                f"{p1_restants:.2f}" if p1_restants > 0 else "",
                PDFStyles.format_currency(p2_base) if p2_base > 0 else "",
                f"{p2_mois:.2f}" if p2_mois > 0 else "",
                f"{p2_acquis:.2f}" if p2_acquis > 0 else "",
                f"{p2_pris:.2f}" if p2_pris > 0 else "",
                f"{p2_restants:.2f}" if p2_restants > 0 else "",
                PDFStyles.format_currency(provision) if provision > 0 else ""
            ])

        # Total row
        data.append([
            "Total Etablissement",
            PDFStyles.format_currency(totals['rel_base']),
            f"{totals['rel_mois']:.2f}",
            f"{totals['rel_restants']:.2f}",
            PDFStyles.format_currency(totals['p1_base']),
            f"{totals['p1_mois']:.2f}",
            f"{totals['p1_acquis']:.2f}",
            f"{totals['p1_pris']:.2f}",
            f"{totals['p1_restants']:.2f}",
            PDFStyles.format_currency(totals['p2_base']),
            f"{totals['p2_mois']:.2f}",
            f"{totals['p2_acquis']:.2f}",
            f"{totals['p2_pris']:.2f}",
            f"{totals['p2_restants']:.2f}",
            PDFStyles.format_currency(totals['provisions'])
        ])

        # Column widths (landscape A4)
        col_widths = [4*cm, 1.5*cm, 1*cm, 1.3*cm,
                      1.5*cm, 1*cm, 1.2*cm, 1.2*cm, 1.3*cm,
                      1.5*cm, 1*cm, 1.2*cm, 1.2*cm, 1.3*cm, 1.8*cm]

        table = Table(data, colWidths=col_widths, repeatRows=2)

        # Style the table
        style = TableStyle([
            # Merge period header cells
            ('SPAN', (1, 0), (3, 0)),  # Reliquat
            ('SPAN', (4, 0), (8, 0)),  # Period 1
            ('SPAN', (9, 0), (14, 0)), # Period 2

            # Header styling
            ('BACKGROUND', (0, 0), (-1, 1), self.COLORS['primary_blue']),
            ('TEXTCOLOR', (0, 0), (-1, 1), colors.white),
            ('ALIGN', (0, 0), (-1, 1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 1), 8),
            ('VALIGN', (0, 0), (-1, 1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, 1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, 1), 3),

            # Data rows
            ('FONTSIZE', (0, 2), (-1, -1), 7),
            ('TEXTCOLOR', (0, 2), (-1, -1), self.COLORS['text_dark']),
            ('ALIGN', (1, 2), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 2), (0, -1), 'LEFT'),

            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border_gray']),

            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 2), (-1, -2), [colors.white, self.COLORS['very_light_blue']]),

            # Total row
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), self.COLORS['light_blue']),
            ('TEXTCOLOR', (0, -1), (-1, -1), self.COLORS['primary_blue']),
        ])

        table.setStyle(style)
        return table
    
    def _create_footer_note(self) -> Paragraph:
        """Create footer note about negative amounts"""
        note_style = ParagraphStyle(
            'FooterNote',
            parent=self.styles['CustomNormal'],
            fontSize=7,
            textColor=self.COLORS['text_gray'],
            alignment=TA_LEFT,
            italic=True
        )
        return Paragraph("*Les montants négatifs ne sont pas totalisés", note_style)

    def _add_footer(self, canvas_obj, doc):
        """Add footer to each page"""
        canvas_obj.saveState()

        width, height = landscape(A4)

        # Footer text
        canvas_obj.setFont('Helvetica', 8)
        footer_text = f"Imprimé le {datetime.now().strftime('%d/%m/%y à %H:%M')}"
        canvas_obj.drawString(1*cm, 1*cm, footer_text)

        # Author
        username = getpass.getuser()
        author = self.company_info.get('author', f'Par {username}')
        canvas_obj.drawString(1*cm, 0.7*cm, author)

        # Page number (right aligned)
        page_text = f"Page n° {doc.page}"
        canvas_obj.setFont('Helvetica', 8)
        canvas_obj.drawRightString(width - 1*cm, 1*cm, page_text)

        # Company code (right bottom)
        company_code = self.company_info.get('code', '')
        company_name = self.company_info.get('name', '')
        if company_code or company_name:
            canvas_obj.setFont('Helvetica', 7)
            company_text = f"{company_code} {company_name}".strip()
            canvas_obj.drawRightString(width - 1*cm, 0.7*cm, company_text)

        canvas_obj.restoreState()

    def _get_last_day_of_month(self, date: datetime) -> datetime:
        """Get last day of month"""
        last_day = calendar.monthrange(date.year, date.month)[1]
        return datetime(date.year, date.month, last_day)

class PayJournalPDFGenerator:
    """Générateur du OD de paie"""

    # Color scheme matching paystub
    COLORS = {
        'primary_blue': colors.HexColor('#1e3a8a'),      # Dark blue for headers
        'secondary_blue': colors.HexColor('#3b82f6'),    # Medium blue for accents
        'light_blue': colors.HexColor('#dbeafe'),        # Light blue for backgrounds
        'very_light_blue': colors.HexColor('#f0f9ff'),   # Very light blue
        'text_dark': colors.HexColor('#1e293b'),         # Dark text
        'text_gray': colors.HexColor('#64748b'),         # Gray text
        'border_gray': colors.HexColor('#e2e8f0')        # Light gray for borders
    }

    def __init__(self, company_info: Dict, logo_path: Optional[str] = None):
        self.company_info = company_info
        self.logo_path = logo_path
        self.styles = PDFStyles.get_styles()

    def generate_pay_journal(self, employees_data: List[Dict],
                            period: str, output_path: Optional[str] = None,
                            password: Optional[str] = None) -> io.BytesIO:
        """
        Générer le journal de paie consolidé

        Args:
            employees_data: Liste des données de tous les employés
            period: Période (format: "MM-YYYY")
            output_path: Chemin de sortie (optionnel)
            password: Mot de passe pour protéger le PDF (optionnel)
        """
        if output_path:
            pdf_buffer = output_path
        else:
            pdf_buffer = io.BytesIO()

        # Use landscape A4
        doc_kwargs = {
            'pagesize': landscape(A4),
            'rightMargin': 1*cm,
            'leftMargin': 1*cm,
            'topMargin': 2*cm,
            'bottomMargin': 2*cm
        }

        # Add password protection if specified
        if password:
            doc_kwargs['encrypt'] = password

        doc = SimpleDocTemplate(pdf_buffer, **doc_kwargs)

        story = []

        # Generate accounting entries
        entries = self._generate_accounting_entries(employees_data, period)

        # Header
        story.append(self._create_journal_header(period))
        story.append(Spacer(1, 0.5*cm))

        # Main table with all entries
        story.append(self._create_accounting_table(entries, period))

        doc.build(story, onFirstPage=self._add_footer, onLaterPages=self._add_footer)

        if not output_path:
            pdf_buffer.seek(0)

        return pdf_buffer
    
    def _create_journal_header(self, period: str) -> Paragraph:
        """Créer l'en-tête du journal"""
        period_date = datetime.strptime(period, "%m-%Y")
        last_day = self._get_last_day_of_month(period_date)

        # Title centered with blue color
        title_style = ParagraphStyle(
            'JournalTitle',
            parent=self.styles['CustomNormal'],
            fontSize=14,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            spaceAfter=6,
            textColor=self.COLORS['primary_blue']
        )

        title = Paragraph("OD de Paie", title_style)

        # Subtitle with journal info
        subtitle_style = ParagraphStyle(
            'JournalSubtitle',
            parent=self.styles['CustomNormal'],
            fontSize=10,
            alignment=TA_LEFT,
            spaceAfter=12,
            textColor=self.COLORS['text_dark']
        )

        company_name = self.company_info.get('name', '')
        journal_num = self.company_info.get('journal_number', '763')  # Default from example
        date_str = f"{last_day.day} {self._get_french_month(last_day.month)} {last_day.year}"

        subtitle = Paragraph(
            f"OD de Paie : {journal_num}     {company_name}     en date du : {date_str}",
            subtitle_style
        )

        return KeepTogether([title, subtitle])
    
    def _generate_accounting_entries(self, employees_data: List[Dict], period: str) -> List[Dict]:
        """Generate all accounting entries"""
        entries = []
        line_num = 2  # Start at line 2 (after header)
        folio = 1

        period_date = datetime.strptime(period, "%m-%Y")
        last_day = self._get_last_day_of_month(period_date)
        date_str = last_day.strftime("%d/%m/%Y")

        # Employee net salaries (4210000000 - credit)
        for emp in employees_data:
            auxiliaire = emp.get('matricule', '').replace('M', 'S').zfill(10) if emp.get('matricule') else ''
            entries.append({
                'compte': '4210000000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': auxiliaire,
                'libelle': f"{emp.get('nom', '')} {emp.get('prenom', '')}",
                'debit': 0,
                'credit': emp.get('salaire_net', 0)
            })
            line_num += 1

        # Acomptes (4250000000 - credit)
        total_acomptes = sum(emp.get('acomptes', 0) for emp in employees_data)
        if total_acomptes > 0:
            entries.append({
                'compte': '4250000000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Acomptes',
                'debit': 0,
                'credit': total_acomptes
            })
            line_num += 1

        # Part salariale CAR/CCSS (4311000000 - credit)
        total_car_ccss_sal = sum(
            self._get_charge_amount(emp, 'salariales', 'CAR') +
            self._get_charge_amount(emp, 'salariales', 'CCSS')
            for emp in employees_data
        )
        if total_car_ccss_sal > 0:
            entries.append({
                'compte': '4311000000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Part salariale CAR/CCSS',
                'debit': 0,
                'credit': total_car_ccss_sal
            })
            line_num += 1

        # Part salariale ASSEDIC (4373000000 - credit)
        total_assedic_sal = sum(
            self._get_charge_amount(emp, 'salariales', 'ASSEDIC_T1') +
            self._get_charge_amount(emp, 'salariales', 'ASSEDIC_T2')
            for emp in employees_data
        )
        if total_assedic_sal > 0:
            entries.append({
                'compte': '4373000000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Part salariale ASSEDIC',
                'debit': 0,
                'credit': total_assedic_sal
            })
            line_num += 1

        # Part salariale prevoyance (4374100000 - credit)
        total_prevoyance_sal = sum(
            self._get_charge_amount(emp, 'salariales', 'PREVOYANCE')
            for emp in employees_data
        )
        if total_prevoyance_sal > 0:
            entries.append({
                'compte': '4374100000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Part salariale MMA / QUATREM',
                'debit': 0,
                'credit': total_prevoyance_sal
            })
            line_num += 1

        # Rémunérations brutes (6411000000 - debit)
        total_salaires_brut = sum(emp.get('salaire_brut', 0) for emp in employees_data)
        total_primes = sum(emp.get('prime', 0) for emp in employees_data)

        # Calculate base salary (brut minus primes)
        total_salaires_base = total_salaires_brut - total_primes

        if total_salaires_base > 0:
            entries.append({
                'compte': '6411000000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Rémunérations brutes',
                'debit': total_salaires_base,
                'credit': 0
            })
            line_num += 1

        # Primes et gratifications (6413000000 - debit)
        if total_primes > 0:
            entries.append({
                'compte': '6413000000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Primes et gratifications',
                'debit': total_primes,
                'credit': 0
            })
            line_num += 1

        # Indemnité de licenciement (6414000000 - debit) if any
        total_indem = sum(emp.get('indemnite_licenciement', 0) for emp in employees_data)
        if total_indem > 0:
            entries.append({
                'compte': '6414000000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Indemnité de licenciement',
                'debit': total_indem,
                'credit': 0
            })
            line_num += 1

        # Mark folio 1 total
        entries.append({
            'compte': '',
            'date': '',
            'folio': '',
            'ligne': '',
            'auxiliaire': '',
            'libelle': 'Total folio',
            'debit': sum(e['debit'] for e in entries if e.get('folio') == folio),
            'credit': sum(e['credit'] for e in entries if e.get('folio') == folio),
            'is_total': True
        })

        # Folio 2 - Employer charges
        folio = 2
        line_num = 20  # Continue line numbering

        # Charges patronales CAR/CCSS (4311000000 - credit)
        total_car_ccss_pat = sum(
            self._get_charge_amount(emp, 'patronales', 'CAR') +
            self._get_charge_amount(emp, 'patronales', 'CCSS')
            for emp in employees_data
        )
        if total_car_ccss_pat > 0:
            entries.append({
                'compte': '4311000000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Charges patronales CAR/CCSS',
                'debit': 0,
                'credit': total_car_ccss_pat
            })
            line_num += 1

        # Charges patronales ASSEDIC (4373000000 - credit)
        total_assedic_pat = sum(
            self._get_charge_amount(emp, 'patronales', 'ASSEDIC_T1') +
            self._get_charge_amount(emp, 'patronales', 'ASSEDIC_T2')
            for emp in employees_data
        )
        if total_assedic_pat > 0:
            entries.append({
                'compte': '4373000000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Charges patronales ASSEDIC',
                'debit': 0,
                'credit': total_assedic_pat
            })
            line_num += 1

        # Charges patronales PREVOYANCE (4374100000 - credit)
        total_prevoyance_pat = sum(
            self._get_charge_amount(emp, 'patronales', 'PREVOYANCE')
            for emp in employees_data
        )
        if total_prevoyance_pat > 0:
            entries.append({
                'compte': '4374100000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Charges patronales PREVOYANCE',
                'debit': 0,
                'credit': total_prevoyance_pat
            })
            line_num += 1

        # Charges patronales CAR/CCSS (6451010000 - debit)
        if total_car_ccss_pat > 0:
            entries.append({
                'compte': '6451010000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Charges patronales CAR/CCSS',
                'debit': total_car_ccss_pat,
                'credit': 0
            })
            line_num += 1

        # Charges patronales PREVOYANCE (6452100000 - debit)
        if total_prevoyance_pat > 0:
            entries.append({
                'compte': '6452100000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Charges patronales PREVOYANCE',
                'debit': total_prevoyance_pat,
                'credit': 0
            })
            line_num += 1

        # Charges patronales CMRC (6453120000 - debit)
        total_cmrc = sum(self._get_charge_amount(emp, 'patronales', 'CMRC') for emp in employees_data)
        if total_cmrc > 0:
            entries.append({
                'compte': '6453120000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Charges patronales CMRC',
                'debit': total_cmrc,
                'credit': 0
            })
            line_num += 1

        # Charges patronales ASSEDIC (6454000000 - debit)
        if total_assedic_pat > 0:
            entries.append({
                'compte': '6454000000',
                'date': date_str,
                'folio': folio,
                'ligne': line_num,
                'auxiliaire': '',
                'libelle': 'Charges patronales ASSEDIC',
                'debit': total_assedic_pat,
                'credit': 0
            })
            line_num += 1

        # Folio 2 total
        folio2_debit = sum(e['debit'] for e in entries if e.get('folio') == folio)
        folio2_credit = sum(e['credit'] for e in entries if e.get('folio') == folio)
        entries.append({
            'compte': '',
            'date': '',
            'folio': '',
            'ligne': '',
            'auxiliaire': '',
            'libelle': 'Total folio',
            'debit': folio2_debit,
            'credit': folio2_credit,
            'is_total': True
        })

        # Total établissement
        total_debit = sum(e['debit'] for e in entries if not e.get('is_total'))
        total_credit = sum(e['credit'] for e in entries if not e.get('is_total'))
        entries.append({
            'compte': '',
            'date': '',
            'folio': '',
            'ligne': '',
            'auxiliaire': '',
            'libelle': 'Total établissement',
            'debit': total_debit,
            'credit': total_credit,
            'is_total': True
        })

        # Total général
        entries.append({
            'compte': '',
            'date': '',
            'folio': '',
            'ligne': '',
            'auxiliaire': '',
            'libelle': 'Total général',
            'debit': total_debit,
            'credit': total_credit,
            'is_total': True
        })

        return entries

    def _create_accounting_table(self, entries: List[Dict], period: str) -> Table:
        """Create the main accounting entries table"""
        # Header row
        data = [[
            'Compte', 'Date', 'Folio', 'Ligne', 'Auxiliaire', 'Libelle', 'Débit', 'Crédit'
        ]]

        # Add all entries
        for entry in entries:
            is_total = entry.get('is_total', False)
            data.append([
                str(entry.get('compte', '')),
                str(entry.get('date', '')),
                str(entry.get('folio', '')),
                str(entry.get('ligne', '')),
                str(entry.get('auxiliaire', '')),
                entry.get('libelle', ''),
                PDFStyles.format_currency(entry['debit']) if entry['debit'] > 0 else '0,00',
                PDFStyles.format_currency(entry['credit']) if entry['credit'] > 0 else '0,00'
            ])

        # Create table with proper column widths
        col_widths = [2.5*cm, 2.2*cm, 1.3*cm, 1.3*cm, 2.5*cm, 7*cm, 2.5*cm, 2.5*cm]
        table = Table(data, colWidths=col_widths, repeatRows=1)

        # Style the table
        style = TableStyle([
            # Header row styling
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['primary_blue']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),

            # All cells
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('TEXTCOLOR', (0, 1), (-1, -1), self.COLORS['text_dark']),

            # Align numbers to right
            ('ALIGN', (6, 1), (7, -1), 'RIGHT'),

            # Grid with blue borders
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border_gray']),

            # Center folio and ligne columns
            ('ALIGN', (2, 1), (3, -1), 'CENTER'),

            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLORS['very_light_blue']]),
        ])

        # Find total rows and apply bold styling with background
        for idx, entry in enumerate(entries, start=1):
            if entry.get('is_total'):
                style.add('FONTNAME', (0, idx), (-1, idx), 'Helvetica-Bold')
                style.add('ALIGN', (5, idx), (5, idx), 'RIGHT')
                style.add('BACKGROUND', (0, idx), (-1, idx), self.COLORS['light_blue'])
                style.add('TEXTCOLOR', (0, idx), (-1, idx), self.COLORS['primary_blue'])

        table.setStyle(style)
        return table

    def _add_footer(self, canvas_obj, doc):
        """Add footer to each page"""
        canvas_obj.saveState()

        width, height = landscape(A4)

        # Footer text
        canvas_obj.setFont('Helvetica', 8)
        footer_text = f"Imprimé le {datetime.now().strftime('%d/%m/%y à %H:%M')}"
        canvas_obj.drawString(1*cm, 1*cm, footer_text)

        # Author
        username = getpass.getuser()
        author = self.company_info.get('author', f'Par {username}')
        canvas_obj.drawString(1*cm, 0.7*cm, author)

        # Page number (right aligned)
        page_text = f"Page n° {doc.page}"
        canvas_obj.drawRightString(width - 1*cm, 1*cm, page_text)

        # Software info
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.drawRightString(width - 1*cm, 0.7*cm, "BEC")

        canvas_obj.restoreState()

    def _get_french_month(self, month_num: int) -> str:
        """Get French month name"""
        months = {
            1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
            5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
            9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
        }
        return months.get(month_num, '')

    def _get_charge_amount(self, emp: Dict, type_charge: str, key: str) -> float:
        """Get charge amount from employee data"""
        details = emp.get('details_charges', {})
        charges = details.get(f'charges_{type_charge}', {})
        return charges.get(key, 0)

    def _get_last_day_of_month(self, date: datetime) -> datetime:
        """Get last day of month"""
        last_day = calendar.monthrange(date.year, date.month)[1]
        return datetime(date.year, date.month, last_day)

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

        # Agrégation des charges par organisme
        organismes = self._aggregate_charges(employees_data)

        # Tableau des charges groupées par organisme
        story.append(self._create_charges_table(organismes))
        story.append(Spacer(1, 0.5*cm))

        # Pied de page
        story.append(Spacer(1, 0.5*cm))
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

    def _get_organisme_mapping(self) -> Dict[str, Tuple[str, str]]:
        """Map charge codes to organismes (code, name)"""
        return {
            'UNEDIC': ('002', 'FRANCE TRAVAIL'),
            'CCSS': ('101', 'CCSS'),
            'RETRAITE_CAR': ('103', 'CAR'),
            'CONTRIB_EQUILIBRE_TECH': ('103', 'CAR'),
            'CONTRIB_EQUILIBRE_GEN_T1': ('103', 'CAR'),
            'CONTRIB_EQUILIBRE_GEN_T2': ('103', 'CAR'),
            'CMRC TA': ('105', 'CMRC'),
            'CMRC TB': ('105', 'CMRC'),
        }

    def _aggregate_charges(self, employees_data: List[Dict]) -> Dict:
        """
        Agréger les charges par organisme puis par code

        Returns:
            Dict avec structure: {
                'organisme_code': {
                    'organisme_name': str,
                    'charges': {
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
                    },
                    'homme': int,
                    'femme': int
                }
            }
        """
        organismes = {}
        rates_csv = self._load_rates()
        organisme_mapping = self._get_organisme_mapping()

        # Track which employees have been counted per organisme
        organisme_employees = {}

        for emp in employees_data:
            details = emp.get('details_charges', {})
            if not isinstance(details, dict):
                continue

            sexe = emp.get('sexe', '').upper()
            matricule = emp.get('matricule', '')

            charges_sal = details.get('charges_salariales', {})
            charges_pat = details.get('charges_patronales', {})

            # Process all charges (both salarial and patronal)
            all_charges = {}

            # Combine charges_sal and charges_pat
            for code, montant in (charges_sal.items() if isinstance(charges_sal, dict) else []):
                if code not in all_charges:
                    all_charges[code] = {'sal': 0, 'pat': 0}
                all_charges[code]['sal'] += montant

            for code, montant in (charges_pat.items() if isinstance(charges_pat, dict) else []):
                if code not in all_charges:
                    all_charges[code] = {'sal': 0, 'pat': 0}
                all_charges[code]['pat'] += montant

            # Process combined charges
            for code, montants in all_charges.items():
                if montants['sal'] == 0 and montants['pat'] == 0:
                    continue

                # Get organisme info
                org_code, org_name = organisme_mapping.get(code, ('999', 'AUTRES'))

                # Initialize organisme if needed
                if org_code not in organismes:
                    organismes[org_code] = {
                        'organisme_name': org_name,
                        'charges': {},
                        'homme': 0,
                        'femme': 0
                    }
                    organisme_employees[org_code] = set()

                # Track employee for this organisme
                if matricule not in organisme_employees[org_code]:
                    organisme_employees[org_code].add(matricule)
                    if sexe == 'H':
                        organismes[org_code]['homme'] += 1
                    elif sexe == 'F':
                        organismes[org_code]['femme'] += 1

                # Initialize charge if needed
                if code not in organismes[org_code]['charges']:
                    rate_info = rates_csv.get(code, {})
                    organismes[org_code]['charges'][code] = {
                        'description': rate_info.get('description', code),
                        'code_dsm': rate_info.get('code_dsm', ''),
                        'nbre_salarie': 0,
                        'base_cotisee': 0,
                        'taux_sal': rate_info.get('taux_sal', 0),
                        'taux_pat': rate_info.get('taux_pat', 0),
                        'montant_sal': 0,
                        'montant_pat': 0,
                        'employes': set()
                    }

                charge_data = organismes[org_code]['charges'][code]

                # Track employee for this charge
                if matricule not in charge_data['employes']:
                    charge_data['employes'].add(matricule)
                    charge_data['nbre_salarie'] += 1

                # Calculate base from taux and montant
                if montants['sal'] > 0 and charge_data['taux_sal'] > 0:
                    base = montants['sal'] / (charge_data['taux_sal'] / 100)
                    charge_data['base_cotisee'] += base
                elif montants['pat'] > 0 and charge_data['taux_pat'] > 0 and charge_data['base_cotisee'] == 0:
                    base = montants['pat'] / (charge_data['taux_pat'] / 100)
                    charge_data['base_cotisee'] += base

                charge_data['montant_sal'] += montants['sal']
                charge_data['montant_pat'] += montants['pat']

        # Clean up employes sets (not JSON serializable)
        for org_data in organismes.values():
            for charge_data in org_data['charges'].values():
                del charge_data['employes']

        return organismes

    def _load_rates(self) -> Dict:
        """Charger les taux depuis le CSV pour avoir les descriptions et codes DSM"""
        rates = {}
        csv_path = Path("data/config") / "payroll_rates.csv"

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
                                'code_dsm': row.get('code_dsm', ''),
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

    def _create_charges_table(self, organismes: Dict) -> Table:
        """Créer le tableau des charges regroupées par organisme"""
        
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

        # Totaux globaux
        total_sal_global = 0
        total_pat_global = 0
        total_homme_global = 0
        total_femme_global = 0

        # Parcourir chaque organisme dans l'ordre
        for org_code in sorted(organismes.keys()):
            org_data = organismes[org_code]
            org_name = org_data['organisme_name']
            charges = org_data['charges']

            # Header de l'organisme - merge cells across
            org_header_text = f"<b>Organisme : {org_code}  {org_name}</b>"
            data.append([
                Paragraph(org_header_text, self.styles['CustomSmall']),
                "", "", "", "", "", "", "", "", ""
            ])

            # Totaux pour cet organisme
            total_sal_org = 0
            total_pat_org = 0

            # Lignes de charges pour cet organisme
            for code, values in sorted(charges.items()):
                taux_sal = values['taux_sal']
                taux_pat = values['taux_pat']
                taux_glo = taux_sal + taux_pat

                montant_sal = values['montant_sal']
                montant_pat = values['montant_pat']
                montant_glo = montant_sal + montant_pat

                total_sal_org += montant_sal
                total_pat_org += montant_pat

                # Use code_dsm if available, otherwise use charge code
                display_code = values.get('code_dsm', code) or code

                # Abbreviate base cotisée to CCSS or CMRC for common social charges
                description = values['description']
                if 'CCSS' in description.upper() or 'caisse de compensation' in description.lower():
                    base_cotisee_text = 'CCSS'
                elif 'CMRC' in description.upper() or 'caisse monégasque' in description.lower():
                    base_cotisee_text = 'CMRC'
                else:
                    base_cotisee_text = description

                data.append([
                    f"{display_code}",
                    base_cotisee_text,
                    str(values['nbre_salarie']),
                    PDFStyles.format_currency(values['base_cotisee']),
                    f"{taux_sal:.2f}" if taux_sal > 0 else "",
                    f"{taux_pat:.2f}" if taux_pat > 0 else "",
                    f"{taux_glo:.2f}" if taux_glo > 0 else "",
                    PDFStyles.format_currency(montant_sal) if montant_sal > 0 else "",
                    PDFStyles.format_currency(montant_pat) if montant_pat > 0 else "",
                    PDFStyles.format_currency(montant_glo)
                ])

            # Sous-total organisme
            homme_org = org_data['homme']
            femme_org = org_data['femme']
            data.append([
                Paragraph(f"<b>TOTAL {org_name}</b>", self.styles['CustomSmall']),
                Paragraph(f"Homme : {homme_org}  Femme : {femme_org}", self.styles['CustomSmall']),
                "", "", "", "", "",
                Paragraph(f"<b>{PDFStyles.format_currency(total_sal_org)}</b>", self.styles['CustomSmall']),
                Paragraph(f"<b>{PDFStyles.format_currency(total_pat_org)}</b>", self.styles['CustomSmall']),
                Paragraph(f"<b>{PDFStyles.format_currency(total_sal_org + total_pat_org)}</b>", self.styles['CustomSmall'])
            ])

            total_sal_global += total_sal_org
            total_pat_global += total_pat_org
            total_homme_global += homme_org
            total_femme_global += femme_org

        # Ligne de total global
        data.append([
            Paragraph(f"<b>TOTAL GLOBAL</b>", self.styles['CustomSmall']),
            "", "", "", "", "", "",
            Paragraph(f"<b>{PDFStyles.format_currency(total_sal_global)}</b>", self.styles['CustomSmall']),
            Paragraph(f"<b>{PDFStyles.format_currency(total_pat_global)}</b>", self.styles['CustomSmall']),
            Paragraph(f"<b>{PDFStyles.format_currency(total_sal_global + total_pat_global)}</b>", self.styles['CustomSmall'])
        ])

        table = Table(data, colWidths=[
            1.15*cm, 4.4*cm, 1.3*cm, 1.85*cm, 1.2*cm, 1.2*cm, 1.2*cm, 1.95*cm, 1.95*cm, 1.95*cm
        ])

        # Style de base
        table_style = [
            # En-tête
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#CCCCCC')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),

            # Corps - alignement
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 1), (1, -1), 'LEFT'),
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),

            # Grille
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]

        # Style pour les headers d'organisme et sous-totaux
        row_idx = 1
        for org_code in sorted(organismes.keys()):
            org_data = organismes[org_code]
            charges_count = len(org_data['charges'])

            # Header organisme - span across all columns
            table_style.extend([
                ('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'),
                ('SPAN', (0, row_idx), (-1, row_idx)),
            ])
            row_idx += 1

            # Lignes de charges
            row_idx += charges_count

            # Sous-total - pas de fond, juste bold avec ligne
            table_style.extend([
                ('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'),
                ('SPAN', (0, row_idx), (1, row_idx)),
                ('SPAN', (2, row_idx), (6, row_idx)),
                ('LINEABOVE', (0, row_idx), (-1, row_idx), 1, colors.black),
            ])
            row_idx += 1

        # Total global - fond bleu
        table_style.extend([
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#1a5f9e')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('SPAN', (0, -1), (6, -1)),
            ('LINEABOVE', (0, -1), (-1, -1), 2, colors.black),
        ])

        table.setStyle(TableStyle(table_style))
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

class RecapPaiePDFGenerator:
    """Générateur de PDF pour le récapitulatif annuel de paie"""

    # Color scheme matching paystubs - blue tones
    COLORS = {
        'primary_blue': colors.HexColor('#1e3a8a'),      # Dark blue for headers
        'secondary_blue': colors.HexColor('#3b82f6'),    # Medium blue for accents
        'light_blue': colors.HexColor('#dbeafe'),        # Light blue for backgrounds
        'very_light_blue': colors.HexColor('#f0f9ff'),   # Very light blue
        'text_dark': colors.HexColor('#1e293b'),         # Dark text
        'text_gray': colors.HexColor('#64748b'),         # Gray text
        'border_gray': colors.HexColor('#e2e8f0')        # Light gray for borders
    }

    def __init__(self, company_info: Dict, logo_path: Optional[str] = None):
        self.company_info = company_info
        self.logo_path = logo_path
        self.styles = PDFStyles.get_styles()

    def generate_recap_paie(self, company_id: str, year: int,
                           output_path: Optional[str] = None) -> io.BytesIO:
        """
        Générer récapitulatif annuel de paie (1 page par employé)

        Args:
            company_id: ID de l'entreprise
            year: Année
            output_path: Chemin de sortie (optionnel)

        Returns:
            io.BytesIO: PDF buffer
        """
        if output_path:
            pdf_buffer = output_path
        else:
            pdf_buffer = io.BytesIO()

        # Load client company name
        self.client_company_name = self._load_company_name(company_id)

        # Load yearly data
        employees_data = self._load_yearly_data(company_id, year)

        if not employees_data:
            raise ValueError(f"No data for company {company_id} in year {year}")

        # Sort by last name
        employees_data = sorted(employees_data, key=lambda x: x.get('nom', '').upper())

        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=1.5*cm,
            bottomMargin=2*cm
        )

        story = []

        # Calculate matricule range for first page header
        matricules = [emp.get('matricule', '') for emp in employees_data if emp.get('matricule')]
        matricule_range = (matricules[0], matricules[-1]) if matricules else ('', '')

        # Generate 1 page per employee
        for idx, emp_data in enumerate(employees_data):
            if idx > 0:
                story.append(PageBreak())

            # Only show matricule range on first page
            is_first_page = (idx == 0)
            story.extend(self._create_employee_page(emp_data, year, is_first_page, matricule_range))

        # Build with footer
        doc.build(story, onFirstPage=self._add_footer, onLaterPages=self._add_footer)

        if not output_path:
            pdf_buffer.seek(0)

        return pdf_buffer

    def _load_company_name(self, company_id: str) -> str:
        """Load company name from companies.parquet"""
        import polars as pl

        companies_file = Path("data/companies/companies.parquet")

        if not companies_file.exists():
            return company_id.replace('_', ' ').upper()

        try:
            df = pl.read_parquet(companies_file)
            company_row = df.filter(pl.col('id') == company_id)

            if company_row.height > 0:
                return company_row.select('name').item()
            else:
                return company_id.replace('_', ' ').upper()
        except:
            return company_id.replace('_', ' ').upper()

    def _load_yearly_data(self, company_id: str, year: int) -> List[Dict]:
        """Load and aggregate yearly data per employee from parquet files"""

        consolidated_dir = Path("data/consolidated")

        if not consolidated_dir.exists():
            return []

        # Collect all parquet files for this company across all year directories
        all_dfs = []

        for year_dir in consolidated_dir.iterdir():
            if not year_dir.is_dir():
                continue

            # Look for parquet files for this company
            pattern = f"{company_id}_*.parquet"
            for parquet_file in year_dir.glob(pattern):
                try:
                    df = pl.read_parquet(parquet_file)

                    # Filter by calculation_year and validated status
                    if 'calculation_year' in df.columns and 'statut_validation' in df.columns:
                        df_filtered = df.filter(
                            (pl.col('calculation_year') == year) &
                            (pl.col('statut_validation') == 'true')
                        )
                        if df_filtered.height > 0:
                            all_dfs.append(df_filtered)
                except:
                    continue

        if not all_dfs:
            return []

        # Concatenate all dataframes
        df_all = pl.concat(all_dfs)

        # Aggregate by employee
        employees = {}

        for row in df_all.iter_rows(named=True):
            matricule = row.get('matricule')
            if not matricule:
                continue

            if matricule not in employees:
                employees[matricule] = {
                    'matricule': matricule,
                    'nom': row.get('nom') or '',
                    'prenom': row.get('prenom') or '',
                    'months': [],
                    'total_brut': 0,
                    'total_net': 0,
                    'total_charges_sal': 0,
                    'total_charges_pat': 0,
                    'total_net_imposable': 0,
                    'total_pas': 0,
                    'rubriques': {},
                    'charges': {}
                }

            # Accumulate totals
            employees[matricule]['total_brut'] += row.get('salaire_brut') or 0
            employees[matricule]['total_net'] += row.get('salaire_net') or 0
            employees[matricule]['total_charges_sal'] += row.get('total_charges_salariales') or 0
            employees[matricule]['total_charges_pat'] += row.get('total_charges_patronales') or 0
            # Use salaire_net as fallback for net_imposable if not available
            employees[matricule]['total_net_imposable'] += row.get('net_imposable', row.get('salaire_net', 0)) or 0
            employees[matricule]['total_pas'] += row.get('pas_retenu', 0) or 0

            # Track month
            period_month = row.get('period_month')
            if period_month:
                employees[matricule]['months'].append(period_month)

            # Parse details_charges if available
            details_charges = row.get('details_charges')
            if details_charges:
                try:
                    if isinstance(details_charges, str):
                        details = json.loads(details_charges)
                    elif isinstance(details_charges, dict):
                        details = details_charges
                    else:
                        continue
                    self._aggregate_charges(employees[matricule], details)
                except:
                    pass

        return list(employees.values())

    def _aggregate_charges(self, emp_data: Dict, details: Dict):
        """Aggregate charges from monthly details into yearly totals"""
        charges_sal = details.get('charges_salariales', {})
        charges_pat = details.get('charges_patronales', {})

        for code, montant in (charges_sal.items() if isinstance(charges_sal, dict) else []):
            if code not in emp_data['charges']:
                emp_data['charges'][code] = {
                    'salarial': 0,
                    'patronal': 0,
                    'count': 0
                }
            emp_data['charges'][code]['salarial'] += montant or 0
            emp_data['charges'][code]['count'] += 1

        for code, montant in (charges_pat.items() if isinstance(charges_pat, dict) else []):
            if code not in emp_data['charges']:
                emp_data['charges'][code] = {
                    'salarial': 0,
                    'patronal': 0,
                    'count': 0
                }
            emp_data['charges'][code]['patronal'] += montant or 0

    def _create_employee_page(self, emp_data: Dict, year: int, is_first_page: bool = False,
                             matricule_range: tuple = ('', '')) -> List:
        """Create page content for one employee"""
        elements = []

        # Header
        elements.extend(self._create_header(emp_data, year, is_first_page, matricule_range))
        elements.append(Spacer(1, 0.3*cm))

        # Main table
        elements.append(self._create_recap_table(emp_data))
        elements.append(Spacer(1, 0.5*cm))

        # Footer with totals
        elements.append(self._create_totals_footer(emp_data, year))

        return elements

    def _create_header(self, emp_data: Dict, year: int, is_first_page: bool = False,
                      matricule_range: tuple = ('', '')) -> List:
        """Create page header"""
        elements = []

        # Title with blue background using Table for full encapsulation
        title_table = Table([["Récapitulatif de paie"]], colWidths=[16.3*cm], rowHeights=[0.8*cm])
        title_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COLORS['primary_blue']),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        elements.append(title_table)
        elements.append(Spacer(1, 0.2*cm))

        # Employee and establishment info (only on first page)
        if is_first_page:
            info_style = ParagraphStyle(
                'RecapInfo',
                fontSize=8,
                alignment=TA_LEFT,
                textColor=self.COLORS['text_gray']
            )

            matricule_start, matricule_end = matricule_range
            info_text = f"Salarié(e) de {matricule_start} à {matricule_end}<br/>Etablissement(e) &lt;&lt;Tous&gt;&gt;"
            elements.append(Paragraph(info_text, info_style))
            elements.append(Spacer(1, 0.3*cm))

        # Employee name box
        matricule = emp_data.get('matricule', '')
        nom = emp_data.get('nom', '').upper()
        prenom = emp_data.get('prenom', '').title()
        name_text = f"Salarié {matricule} {nom} {prenom}"

        name_table = Table([[name_text]], colWidths=[16.3*cm])
        name_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, self.COLORS['primary_blue']),
            ('BACKGROUND', (0, 0), (-1, -1), self.COLORS['very_light_blue']),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLORS['text_dark']),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(name_table)
        elements.append(Spacer(1, 0.2*cm))

        # Period
        period_style = ParagraphStyle(
            'RecapPeriod',
            fontSize=9,
            fontName='Helvetica-Bold',
            alignment=TA_LEFT,
            textColor=self.COLORS['text_dark']
        )
        period_text = f"Période de 01/01/{year} à 31/12/{year}"
        elements.append(Paragraph(period_text, period_style))

        return elements

    def _create_recap_table(self, emp_data: Dict) -> Table:
        """Create main recap table with rubriques and charges"""

        # Header row
        headers = ['RUBRIQUES', 'NB SALARIE', 'REMUNERATION', 'BASE',
                   'TX SAL.', 'SALARIAL', 'TX PAT.', 'PATRONAL']

        data = [headers]

        # Salary lines (simplified - using aggregated totals)
        # In real implementation, would parse monthly rubriques
        nb_months = len(emp_data.get('months', []))

        data.append([
            '0011 Salaire Mensuel',
            str(nb_months),
            f"{emp_data['total_brut']:,.2f}",
            '',
            '',
            '',
            '',
            ''
        ])

        # Total hours/brut
        data.append([
            'Total Heure payées',
            str(nb_months),
            f"{emp_data['total_brut']:,.2f}",
            '',
            '',
            '',
            '',
            ''
        ])

        data.append([
            'Total Heure trav./ Brut',
            str(nb_months),
            f"{emp_data['total_brut']:,.2f}",
            '',
            '',
            '',
            '',
            ''
        ])

        # Charges sociales
        for code, amounts in sorted(emp_data.get('charges', {}).items()):
            base = amounts.get('salarial', 0) + amounts.get('patronal', 0)
            if base == 0:
                continue

            data.append([
                code,
                str(amounts.get('count', nb_months)),
                '',
                f"{base:,.2f}" if base > 0 else '',
                '',
                f"{amounts.get('salarial', 0):,.2f}" if amounts.get('salarial', 0) > 0 else '',
                '',
                f"{amounts.get('patronal', 0):,.2f}" if amounts.get('patronal', 0) > 0 else ''
            ])

        # Total retenues
        data.append([
            'Total Retenues',
            '',
            '',
            '',
            '',
            f"{emp_data['total_charges_sal']:,.2f}",
            '',
            f"{emp_data['total_charges_pat']:,.2f}"
        ])

        # Column widths - reduced RUBRIQUES and BASE, increased numeric columns
        col_widths = [4.2*cm, 1.8*cm, 2.4*cm, 1.4*cm, 1.2*cm, 2.0*cm, 1.2*cm, 2.1*cm]

        table = Table(data, colWidths=col_widths, repeatRows=1)

        # Table style
        table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['primary_blue']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

            # Data rows
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TEXTCOLOR', (0, 1), (-1, -1), self.COLORS['text_dark']),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # RUBRIQUES left
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),  # Numbers right

            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border_gray']),
            ('BOX', (0, 0), (-1, -1), 1.5, self.COLORS['primary_blue']),

            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),

            # Bold totals
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), self.COLORS['light_blue']),
        ]))

        return table

    def _create_totals_footer(self, emp_data: Dict, year: int) -> Table:
        """Create footer with totals"""

        nom = emp_data.get('nom', '').upper()
        prenom = emp_data.get('prenom', '').title()
        total_label = f"Total {nom} {prenom} Période de 01/01/{year} à 31/12/{year}"

        # Calculate values
        pas = emp_data.get('total_pas', 0)
        brut_av_abatt = emp_data.get('total_brut', 0)
        net_imposable = emp_data.get('total_net_imposable', 0)
        net_a_payer = emp_data.get('total_net', 0)

        # Inner table with values (match main table width of 16.3cm)
        inner_table = Table([
            ['PAS', 'Brut av abatt.', 'Net imposable', 'Net à payer'],
            [f"{pas:,.2f}", f"{brut_av_abatt:,.2f}", f"{net_imposable:,.2f}", f"{net_a_payer:,.2f}"]
        ], colWidths=[4.075*cm, 4.075*cm, 4.075*cm, 4.075*cm])

        inner_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['primary_blue']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TEXTCOLOR', (0, 1), (-1, 1), self.COLORS['text_dark']),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border_gray']),
        ]))

        data = [
            [total_label],
            [inner_table]
        ]

        footer_table = Table(data, colWidths=[16.3*cm])
        footer_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.COLORS['text_dark']),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOX', (0, 0), (-1, -1), 1.5, self.COLORS['primary_blue']),
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['very_light_blue']),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))

        return footer_table

    def _add_footer(self, canvas_obj, doc):
        """Add footer to each page"""
        canvas_obj.saveState()

        # Get current user
        current_user = getpass.getuser()

        # Footer text
        footer_left = f"Imprimé le {datetime.now().strftime('%d/%m/%y à %H:%M')}"
        footer_right = f"Page n° {doc.page}"
        footer_user = f"Par {current_user}"
        footer_company = getattr(self, 'client_company_name', 'COMPANY NAME').upper()

        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.setFillColor(self.COLORS['text_gray'])

        # Left
        canvas_obj.drawString(1.5*cm, 1*cm, footer_left)
        canvas_obj.drawString(1.5*cm, 0.7*cm, footer_user)

        # Center
        canvas_obj.drawString(8*cm, 0.7*cm, f"Version {datetime.now().strftime('%Y%m%d%H%M%S')} du {datetime.now().strftime('%d/%m/%Y')}")

        # Right
        canvas_obj.drawRightString(19.5*cm, 1*cm, footer_right)
        canvas_obj.drawRightString(19.5*cm, 0.7*cm, footer_company)

        canvas_obj.restoreState()

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
        self.recap_generator = RecapPaiePDFGenerator(company_info, logo_path)
    
    def generate_monthly_documents(self, employees_df: pl.DataFrame,
                                  period: str, output_dir: Optional[Path] = None,
                                  password: Optional[str] = None) -> Dict[str, any]:
        """
        Générer tous les documents pour une période mensuelle

        Args:
            employees_df: DataFrame avec les données de tous les employés
            period: Période au format "MM-YYYY"
            output_dir: Répertoire de sortie (optionnel)
            password: Mot de passe pour protéger les PDFs (optionnel)

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
                self.paystub_generator.generate_paystub(emp_data, str(output_path), password=password)
            else:
                paystub_buffer = self.paystub_generator.generate_paystub(emp_data, password=password)
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
            self.journal_generator.generate_pay_journal(employees_data, period, str(journal_path), password=password)
        else:
            journal_buffer = self.journal_generator.generate_pay_journal(employees_data, period, password=password)
            documents['journal'] = journal_buffer

        # 3. Générer la provision pour congés payés
        provisions_data = self._prepare_provisions_data(employees_df, period_date)

        if output_dir:
            pto_path = output_dir / f"provision_cp_{period}.pdf"
            self.pto_generator.generate_pto_provision(provisions_data, period, str(pto_path), password=password)
        else:
            pto_buffer = self.pto_generator.generate_pto_provision(provisions_data, period, password=password)
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

    def generate_recap_paie_pdf(self, company_id: str, year: int,
                               output_path: Optional[str] = None) -> io.BytesIO:
        """
        Générer récapitulatif annuel de paie

        Args:
            company_id: ID de l'entreprise
            year: Année
            output_path: Chemin de sortie (optionnel)

        Returns:
            Buffer PDF du récapitulatif de paie
        """
        return self.recap_generator.generate_recap_paie(company_id, year, output_path)

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
