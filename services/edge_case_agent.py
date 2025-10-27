"""
Edge Case Agent Module
======================
Intelligent agent for handling payroll edge cases automatically with confidence scoring
"""

import polars as pl
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import io
from xlsxwriter import Workbook

logger = logging.getLogger(__name__)


@dataclass
class EdgeCaseModification:
    """Represents a modification made by the agent"""
    matricule: str
    employee_name: str
    field: str
    old_value: float
    new_value: float
    reason: str
    confidence: float
    automatic: bool
    month: str

    def to_dict(self) -> Dict:
        return {
            'matricule': self.matricule,
            'employee_name': self.employee_name,
            'field': self.field,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'reason': self.reason,
            'confidence': self.confidence,
            'automatic': self.automatic,
            'month': self.month
        }


@dataclass
class HistoricalTrend:
    """Represents historical trend data for an employee"""
    matricule: str
    employee_name: str
    field: str
    months: List[str]
    values: List[float]
    avg_value: float
    std_dev: float
    trend_direction: str  # 'increasing', 'decreasing', 'stable'
    volatility: str  # 'low', 'medium', 'high'

    def to_dict(self) -> Dict:
        return {
            'matricule': self.matricule,
            'employee_name': self.employee_name,
            'field': self.field,
            'months': self.months,
            'values': self.values,
            'avg_value': self.avg_value,
            'std_dev': self.std_dev,
            'trend_direction': self.trend_direction,
            'volatility': self.volatility
        }


@dataclass
class EdgeCaseReport:
    """Report of all modifications and flagged cases"""
    modifications: List[EdgeCaseModification] = field(default_factory=list)
    flagged_cases: List[Dict] = field(default_factory=list)
    anomalies: List[Dict] = field(default_factory=list)
    trends: List[HistoricalTrend] = field(default_factory=list)
    processed_count: int = 0
    automatic_count: int = 0
    flagged_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            'modifications': [m.to_dict() for m in self.modifications],
            'flagged_cases': self.flagged_cases,
            'anomalies': self.anomalies,
            'trends': [t.to_dict() for t in self.trends],
            'processed_count': self.processed_count,
            'automatic_count': self.automatic_count,
            'flagged_count': self.flagged_count,
            'timestamp': self.timestamp.isoformat()
        }


class RemarkParser:
    """Parses free-text remarks to extract structured information"""

    # Patterns for common remarks
    PATTERNS = {
        'new_hire': [
            r'embauche',
            r'nouveau',
            r'nouvelle',
            r'entrée\s+le\s+(\d{1,2})[/-](\d{1,2})',
            r'début\s+le\s+(\d{1,2})[/-](\d{1,2})',
            r'arrivée',
        ],
        'departure': [
            r'départ',
            r'sortie\s+le\s+(\d{1,2})[/-](\d{1,2})',
            r'fin\s+le\s+(\d{1,2})[/-](\d{1,2})',
            r'démission',
            r'licenciement',
        ],
        'salary_change': [
            r'augmentation',
            r'nouveau\s+salaire',
            r'modification\s+salaire',
            r'revalorisation',
        ],
        'bonus': [
            r'prime',
            r'bonus',
            r'gratification',
            r'13.?\s*mois',
            r'treizième',
        ],
        'unpaid_leave': [
            r'congé\s+sans\s+solde',
            r'absence\s+non\s+rémunérée',
            r'arrêt\s+maladie',
        ],
        'prorate': [
            r'prorata',
            r'pro\s*rata',
            r'au\s+(\d{1,2})',
            r'du\s+(\d{1,2})\s+au\s+(\d{1,2})',
        ]
    }

    @classmethod
    def parse(cls, remark: str) -> Dict[str, any]:
        """Parse a remark and extract structured information"""
        if not remark or not isinstance(remark, str):
            return {'type': None, 'details': {}}

        remark_lower = remark.lower()
        result = {'type': None, 'details': {}, 'raw': remark}

        # Check for new hire
        for pattern in cls.PATTERNS['new_hire']:
            match = re.search(pattern, remark_lower)
            if match:
                result['type'] = 'new_hire'
                if match.groups():
                    result['details']['day'] = int(match.group(1))
                break

        # Check for departure
        if not result['type']:
            for pattern in cls.PATTERNS['departure']:
                match = re.search(pattern, remark_lower)
                if match:
                    result['type'] = 'departure'
                    if match.groups():
                        result['details']['day'] = int(match.group(1))
                    break

        # Check for salary change
        if not result['type']:
            for pattern in cls.PATTERNS['salary_change']:
                if re.search(pattern, remark_lower):
                    result['type'] = 'salary_change'
                    break

        # Check for bonus
        for pattern in cls.PATTERNS['bonus']:
            if re.search(pattern, remark_lower):
                if not result['type']:
                    result['type'] = 'bonus'
                result['details']['has_bonus'] = True
                break

        # Check for prorata
        for pattern in cls.PATTERNS['prorate']:
            match = re.search(pattern, remark_lower)
            if match:
                result['details']['prorate'] = True
                if match.groups():
                    result['details']['prorate_day'] = int(match.group(1))
                break

        return result


class EdgeCaseAgent:
    """
    Intelligent agent for handling payroll edge cases

    Features:
    - Analyzes remarks to understand context
    - Compares month-to-month data
    - Detects anomalies (>15% change)
    - Makes automatic adjustments with 95% confidence
    - Flags uncertain cases for review
    """

    CONFIDENCE_THRESHOLD = 0.95
    ANOMALY_THRESHOLD = 0.15  # 15% change

    # Fields to monitor for changes
    MONITORED_FIELDS = [
        'salaire_brut',
        'salaire_net',
        'total_charges_salariales',
        'total_charges_patronales',
        'heures_travaillees',
        'base_heures',
    ]

    def __init__(self, data_consolidator):
        """
        Initialize the agent

        Args:
            data_consolidator: DataConsolidation instance for loading historical data
        """
        self.data_consolidator = data_consolidator
        self.report = EdgeCaseReport()

    def process_payroll(self, current_df: pl.DataFrame, company: str, month: int, year: int) -> Tuple[pl.DataFrame, EdgeCaseReport]:
        """
        Process payroll data and handle edge cases

        Args:
            current_df: Current month's payroll data
            company: Company name
            month: Current month
            year: Current year

        Returns:
            Tuple of (modified_df, report)
        """
        logger.info(f"Starting edge case processing for {company} {month}/{year}")

        # Load previous month data
        prev_month, prev_year = self._get_previous_month(month, year)
        from services.data_mgt import DataManager
        prev_df = DataManager.load_period_data(company, prev_month, prev_year)

        if prev_df is None or (isinstance(prev_df, pl.DataFrame) and prev_df.is_empty()):
            logger.warning("No previous month data available for comparison")
            prev_df = None
        elif not isinstance(prev_df, pl.DataFrame):
            prev_df = pl.DataFrame(prev_df)

        # Reset report
        self.report = EdgeCaseReport()

        # Process each employee
        modified_rows = []
        for idx, row in enumerate(current_df.iter_rows(named=True)):
            try:
                modified_row = self._process_employee(
                    row,
                    prev_df,
                    f"{month:02d}-{year}"
                )
                modified_rows.append(modified_row)
            except Exception as e:
                logger.error(f"Error processing employee {row.get('matricule')}: {e}")
                modified_rows.append(row)

        # Create modified DataFrame
        modified_df = pl.DataFrame(modified_rows)

        # Update report counts
        self.report.processed_count = len(modified_rows)
        self.report.automatic_count = sum(1 for m in self.report.modifications if m.automatic)
        self.report.flagged_count = len(self.report.flagged_cases)

        # Analyze historical trends
        self._analyze_historical_trends(company, month, year, modified_df)

        logger.info(f"Edge case processing complete: {self.report.automatic_count} automatic, {self.report.flagged_count} flagged")

        return modified_df, self.report

    def _process_employee(self, row: Dict, prev_df: Optional[pl.DataFrame], month_str: str) -> Dict:
        """Process a single employee's payroll data"""
        matricule = row.get('matricule', '')
        employee_name = f"{row.get('nom', '')} {row.get('prenom', '')}"

        # Parse remarks
        remark_info = RemarkParser.parse(row.get('remarques', ''))

        # Get previous month data for this employee
        prev_row = None
        if prev_df is not None and not prev_df.is_empty():
            prev_data = prev_df.filter(pl.col('matricule') == matricule)
            if not prev_data.is_empty():
                prev_row = prev_data.to_dicts()[0]

        # Start with current row
        modified_row = dict(row)

        # Handle different cases
        if remark_info['type'] == 'new_hire':
            modified_row = self._handle_new_hire(modified_row, remark_info, month_str)
        elif remark_info['type'] == 'departure':
            modified_row = self._handle_departure(modified_row, remark_info, month_str)
        elif remark_info['type'] == 'bonus':
            modified_row = self._handle_bonus(modified_row, remark_info, month_str)

        # Check for data entry errors (like extra zeros)
        modified_row = self._check_data_entry_errors(modified_row, prev_row, month_str)

        # Compare with previous month and detect anomalies
        if prev_row:
            modified_row = self._compare_and_adjust(modified_row, prev_row, remark_info, month_str)

        return modified_row

    def _handle_new_hire(self, row: Dict, remark_info: Dict, month_str: str) -> Dict:
        """Handle new hire with potential proration"""
        matricule = row.get('matricule', '')
        employee_name = f"{row.get('nom', '')} {row.get('prenom', '')}"

        # Check if proration is mentioned
        if remark_info['details'].get('prorate') or remark_info['details'].get('day'):
            day = remark_info['details'].get('day') or remark_info['details'].get('prorate_day', 1)

            # Calculate working days in month (approximate)
            month_num = int(month_str.split('-')[0])
            year = int(month_str.split('-')[1])

            # Simple approximation: assume 22 working days per month
            total_working_days = 22
            worked_days = max(1, total_working_days - day + 1)
            prorate_factor = worked_days / total_working_days

            confidence = 0.90  # Good confidence for new hire proration

            # Prorate salary fields
            for field in ['salaire_brut', 'salaire_net']:
                if field in row and row[field]:
                    old_value = float(row[field])
                    new_value = old_value * prorate_factor

                    # Only adjust if it looks like full month salary
                    if abs(old_value - new_value) / old_value > 0.1:  # More than 10% difference
                        row[field] = new_value

                        self.report.modifications.append(EdgeCaseModification(
                            matricule=matricule,
                            employee_name=employee_name,
                            field=field,
                            old_value=old_value,
                            new_value=new_value,
                            reason=f"Proratisation embauche le {day} ({worked_days}/{total_working_days} jours)",
                            confidence=confidence,
                            automatic=confidence >= self.CONFIDENCE_THRESHOLD,
                            month=month_str
                        ))

        # Flag for review if confidence is low
        if remark_info['details'].get('prorate') and not remark_info['details'].get('day'):
            self.report.flagged_cases.append({
                'matricule': matricule,
                'employee_name': employee_name,
                'reason': 'Nouvelle embauche - jour de début non spécifié dans remarques',
                'remark': remark_info['raw'],
                'month': month_str
            })

        return row

    def _handle_departure(self, row: Dict, remark_info: Dict, month_str: str) -> Dict:
        """Handle employee departure with potential proration"""
        matricule = row.get('matricule', '')
        employee_name = f"{row.get('nom', '')} {row.get('prenom', '')}"

        # Check if proration is mentioned
        if remark_info['details'].get('prorate') or remark_info['details'].get('day'):
            day = remark_info['details'].get('day', 30)

            # Calculate working days
            total_working_days = 22
            worked_days = min(day, total_working_days)
            prorate_factor = worked_days / total_working_days

            confidence = 0.90

            # Prorate salary fields
            for field in ['salaire_brut', 'salaire_net']:
                if field in row and row[field]:
                    old_value = float(row[field])
                    new_value = old_value * prorate_factor

                    if abs(old_value - new_value) / old_value > 0.1:
                        row[field] = new_value

                        self.report.modifications.append(EdgeCaseModification(
                            matricule=matricule,
                            employee_name=employee_name,
                            field=field,
                            old_value=old_value,
                            new_value=new_value,
                            reason=f"Proratisation départ le {day} ({worked_days}/{total_working_days} jours)",
                            confidence=confidence,
                            automatic=confidence >= self.CONFIDENCE_THRESHOLD,
                            month=month_str
                        ))
        else:
            # Flag departure without clear proration info
            self.report.flagged_cases.append({
                'matricule': matricule,
                'employee_name': employee_name,
                'reason': 'Départ - jour de sortie non spécifié dans remarques',
                'remark': remark_info['raw'],
                'month': month_str
            })

        return row

    def _handle_bonus(self, row: Dict, remark_info: Dict, month_str: str) -> Dict:
        """Handle bonus payments"""
        # Bonuses are usually already in the data, just flag for verification
        matricule = row.get('matricule', '')
        employee_name = f"{row.get('nom', '')} {row.get('prenom', '')}"

        self.report.flagged_cases.append({
            'matricule': matricule,
            'employee_name': employee_name,
            'reason': 'Prime mentionnée - vérifier le montant',
            'remark': remark_info['raw'],
            'month': month_str
        })

        return row

    def _check_data_entry_errors(self, row: Dict, prev_row: Optional[Dict], month_str: str) -> Dict:
        """Check for common data entry errors like extra zeros"""
        if not prev_row:
            return row

        matricule = row.get('matricule', '')
        employee_name = f"{row.get('nom', '')} {row.get('prenom', '')}"

        for field in self.MONITORED_FIELDS:
            if field not in row or field not in prev_row:
                continue

            try:
                current_val = float(row[field]) if row[field] else 0
                prev_val = float(prev_row[field]) if prev_row[field] else 0

                if prev_val == 0:
                    continue

                # Check for 10x or 0.1x errors (extra zero or missing zero)
                ratio = current_val / prev_val

                if 9.5 <= ratio <= 10.5:  # Likely 10x error (extra zero)
                    new_value = current_val / 10
                    confidence = 0.98

                    row[field] = new_value
                    self.report.modifications.append(EdgeCaseModification(
                        matricule=matricule,
                        employee_name=employee_name,
                        field=field,
                        old_value=current_val,
                        new_value=new_value,
                        reason=f"Correction erreur de saisie (zéro en trop) - valeur 10x supérieure au mois précédent",
                        confidence=confidence,
                        automatic=True,
                        month=month_str
                    ))

                elif 0.095 <= ratio <= 0.105:  # Likely 0.1x error (missing zero)
                    new_value = current_val * 10
                    confidence = 0.98

                    row[field] = new_value
                    self.report.modifications.append(EdgeCaseModification(
                        matricule=matricule,
                        employee_name=employee_name,
                        field=field,
                        old_value=current_val,
                        new_value=new_value,
                        reason=f"Correction erreur de saisie (zéro manquant) - valeur 10x inférieure au mois précédent",
                        confidence=confidence,
                        automatic=True,
                        month=month_str
                    ))

            except (ValueError, TypeError, ZeroDivisionError):
                continue

        return row

    def _compare_and_adjust(self, row: Dict, prev_row: Dict, remark_info: Dict, month_str: str) -> Dict:
        """Compare with previous month and detect anomalies"""
        matricule = row.get('matricule', '')
        employee_name = f"{row.get('nom', '')} {row.get('prenom', '')}"

        for field in self.MONITORED_FIELDS:
            if field not in row or field not in prev_row:
                continue

            try:
                current_val = float(row[field]) if row[field] else 0
                prev_val = float(prev_row[field]) if prev_row[field] else 0

                if prev_val == 0:
                    continue

                # Calculate percentage change
                pct_change = abs((current_val - prev_val) / prev_val)

                # Flag if change > 15%
                if pct_change > self.ANOMALY_THRESHOLD:
                    # Check if this is explained by remarks
                    explained = remark_info['type'] in ['new_hire', 'departure', 'salary_change', 'bonus']

                    if not explained:
                        self.report.anomalies.append({
                            'matricule': matricule,
                            'employee_name': employee_name,
                            'field': field,
                            'previous_value': prev_val,
                            'current_value': current_val,
                            'change_percent': pct_change * 100,
                            'remark': remark_info.get('raw', ''),
                            'month': month_str
                        })

                        # Flag for review
                        self.report.flagged_cases.append({
                            'matricule': matricule,
                            'employee_name': employee_name,
                            'reason': f"Variation importante de {field}: {pct_change*100:.1f}% sans explication",
                            'previous_value': prev_val,
                            'current_value': current_val,
                            'month': month_str
                        })

            except (ValueError, TypeError, ZeroDivisionError):
                continue

        return row

    def _get_previous_month(self, month: int, year: int) -> Tuple[int, int]:
        """Get previous month and year"""
        if month == 1:
            return 12, year - 1
        return month - 1, year

    def _analyze_historical_trends(self, company: str, month: int, year: int, current_df: pl.DataFrame):
        """
        Analyze historical trends across the last 6 months

        Args:
            company: Company name
            month: Current month
            year: Current year
            current_df: Current month's data
        """
        logger.info("Analyzing historical trends...")

        # Load last 6 months of data
        historical_data = []
        for i in range(6, 0, -1):
            hist_month = month - i
            hist_year = year
            while hist_month <= 0:
                hist_month += 12
                hist_year -= 1

            from services.data_mgt import DataManager
            hist_df = DataManager.load_period_data(company, hist_month, hist_year)
            if hist_df is not None and not (isinstance(hist_df, pl.DataFrame) and hist_df.is_empty()):
                if not isinstance(hist_df, pl.DataFrame):
                    hist_df = pl.DataFrame(hist_df)
                historical_data.append({
                    'month': f"{hist_month:02d}-{hist_year}",
                    'data': hist_df
                })

        if not historical_data:
            logger.warning("No historical data available for trend analysis")
            return

        # Analyze trends for each employee in current month
        for row in current_df.iter_rows(named=True):
            matricule = row.get('matricule', '')
            employee_name = f"{row.get('nom', '')} {row.get('prenom', '')}"

            # Analyze key fields
            for field in ['salaire_brut', 'salaire_net', 'heures_travaillees']:
                if field not in row:
                    continue

                months = []
                values = []

                # Collect historical values
                for hist_entry in historical_data:
                    hist_df = hist_entry['data']
                    emp_data = hist_df.filter(pl.col('matricule') == matricule)

                    if not emp_data.is_empty():
                        emp_row = emp_data.to_dicts()[0]
                        if field in emp_row and emp_row[field] is not None:
                            months.append(hist_entry['month'])
                            try:
                                values.append(float(emp_row[field]))
                            except (ValueError, TypeError):
                                continue

                # Add current month
                if row[field] is not None:
                    months.append(f"{month:02d}-{year}")
                    try:
                        values.append(float(row[field]))
                    except (ValueError, TypeError):
                        pass

                # Only analyze if we have at least 3 data points
                if len(values) >= 3:
                    import statistics

                    avg_value = statistics.mean(values)
                    std_dev = statistics.stdev(values) if len(values) > 1 else 0

                    # Determine trend direction
                    if len(values) >= 2:
                        recent_trend = values[-1] - values[-2]
                        if abs(recent_trend) < avg_value * 0.05:  # Less than 5% change
                            trend_direction = 'stable'
                        elif recent_trend > 0:
                            trend_direction = 'increasing'
                        else:
                            trend_direction = 'decreasing'
                    else:
                        trend_direction = 'stable'

                    # Determine volatility
                    cv = (std_dev / avg_value) if avg_value > 0 else 0  # Coefficient of variation
                    if cv < 0.10:
                        volatility = 'low'
                    elif cv < 0.25:
                        volatility = 'medium'
                    else:
                        volatility = 'high'

                    # Create trend object
                    trend = HistoricalTrend(
                        matricule=matricule,
                        employee_name=employee_name,
                        field=field,
                        months=months,
                        values=values,
                        avg_value=avg_value,
                        std_dev=std_dev,
                        trend_direction=trend_direction,
                        volatility=volatility
                    )

                    self.report.trends.append(trend)

                    # Flag high volatility cases
                    if volatility == 'high':
                        self.report.flagged_cases.append({
                            'matricule': matricule,
                            'employee_name': employee_name,
                            'reason': f"Volatilité élevée détectée sur {field} (écart-type: {std_dev:.2f})",
                            'field': field,
                            'volatility': volatility,
                            'month': f"{month:02d}-{year}"
                        })

        logger.info(f"Historical trend analysis complete: {len(self.report.trends)} trends identified")

    def generate_email_summary(self, accountant_email: str) -> Dict:
        """
        Generate email summary for the accountant

        Args:
            accountant_email: Email address of the accountant

        Returns:
            Dictionary with email subject, body, and data
        """
        modifications_auto = [m for m in self.report.modifications if m.automatic]
        modifications_manual = [m for m in self.report.modifications if not m.automatic]

        # Create HTML body
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h2 {{ color: #2c3e50; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th {{ background-color: #34495e; color: white; padding: 10px; text-align: left; }}
                td {{ border: 1px solid #ddd; padding: 8px; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .automatic {{ background-color: #d4edda; }}
                .manual {{ background-color: #fff3cd; }}
                .anomaly {{ background-color: #f8d7da; }}
                .summary {{ background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <h2>Rapport de Traitement Automatique des Paies</h2>

            <div class="summary">
                <h3>Résumé</h3>
                <ul>
                    <li><strong>Employés traités:</strong> {self.report.processed_count}</li>
                    <li><strong>Modifications automatiques:</strong> {len(modifications_auto)}</li>
                    <li><strong>Cas signalés pour révision:</strong> {self.report.flagged_count}</li>
                    <li><strong>Anomalies détectées:</strong> {len(self.report.anomalies)}</li>
                </ul>
            </div>
        """

        # Automatic modifications
        if modifications_auto:
            html_body += """
            <h3>✅ Modifications Automatiques (Confiance ≥ 95%)</h3>
            <table>
                <tr>
                    <th>Matricule</th>
                    <th>Employé</th>
                    <th>Champ</th>
                    <th>Ancienne Valeur</th>
                    <th>Nouvelle Valeur</th>
                    <th>Raison</th>
                    <th>Confiance</th>
                </tr>
            """
            for mod in modifications_auto:
                html_body += f"""
                <tr class="automatic">
                    <td>{mod.matricule}</td>
                    <td>{mod.employee_name}</td>
                    <td>{mod.field}</td>
                    <td>{mod.old_value:.2f}</td>
                    <td>{mod.new_value:.2f}</td>
                    <td>{mod.reason}</td>
                    <td>{mod.confidence*100:.0f}%</td>
                </tr>
                """
            html_body += "</table>"

        # Flagged cases
        if self.report.flagged_cases:
            html_body += """
            <h3>⚠️ Cas Signalés pour Révision</h3>
            <table>
                <tr>
                    <th>Matricule</th>
                    <th>Employé</th>
                    <th>Raison</th>
                    <th>Remarque</th>
                </tr>
            """
            for case in self.report.flagged_cases:
                html_body += f"""
                <tr class="manual">
                    <td>{case['matricule']}</td>
                    <td>{case['employee_name']}</td>
                    <td>{case['reason']}</td>
                    <td>{case.get('remark', '')}</td>
                </tr>
                """
            html_body += "</table>"

        # Anomalies
        if self.report.anomalies:
            html_body += """
            <h3>🔍 Anomalies Détectées (>15% de variation)</h3>
            <table>
                <tr>
                    <th>Matricule</th>
                    <th>Employé</th>
                    <th>Champ</th>
                    <th>Mois Précédent</th>
                    <th>Mois Actuel</th>
                    <th>Variation</th>
                </tr>
            """
            for anomaly in self.report.anomalies:
                html_body += f"""
                <tr class="anomaly">
                    <td>{anomaly['matricule']}</td>
                    <td>{anomaly['employee_name']}</td>
                    <td>{anomaly['field']}</td>
                    <td>{anomaly['previous_value']:.2f}</td>
                    <td>{anomaly['current_value']:.2f}</td>
                    <td>{anomaly['change_percent']:.1f}%</td>
                </tr>
                """
            html_body += "</table>"

        html_body += """
            <hr>
            <p><em>Ce rapport a été généré automatiquement par l'Agent de Traitement des Paies.</em></p>
            <p>Veuillez réviser les cas signalés dans la page de validation de l'application.</p>
        </body>
        </html>
        """

        # Create plain text version
        text_body = f"""
RAPPORT DE TRAITEMENT AUTOMATIQUE DES PAIES
{'='*50}

RÉSUMÉ
------
Employés traités: {self.report.processed_count}
Modifications automatiques: {len(modifications_auto)}
Cas signalés pour révision: {self.report.flagged_count}
Anomalies détectées: {len(self.report.anomalies)}

"""

        if modifications_auto:
            text_body += "\nMODIFICATIONS AUTOMATIQUES\n" + "-"*50 + "\n"
            for mod in modifications_auto:
                text_body += f"""
{mod.employee_name} ({mod.matricule})
  Champ: {mod.field}
  {mod.old_value:.2f} → {mod.new_value:.2f}
  Raison: {mod.reason}
  Confiance: {mod.confidence*100:.0f}%
"""

        if self.report.flagged_cases:
            text_body += "\nCAS SIGNALÉS POUR RÉVISION\n" + "-"*50 + "\n"
            for case in self.report.flagged_cases:
                text_body += f"""
{case['employee_name']} ({case['matricule']})
  Raison: {case['reason']}
  Remarque: {case.get('remark', '')}
"""

        return {
            'to': accountant_email,
            'subject': f'Rapport Traitement Paies - {self.report.timestamp.strftime("%d/%m/%Y %H:%M")}',
            'html_body': html_body,
            'text_body': text_body,
            'report_data': self.report.to_dict()
        }

    def send_email_report(self, accountant_email: str, smtp_config: Dict) -> bool:
        """
        Send email report to accountant

        Args:
            accountant_email: Email address of the accountant
            smtp_config: SMTP configuration dictionary with keys:
                - smtp_server
                - smtp_port
                - sender_email
                - sender_password
                - sender_name (optional)

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Generate email content
            email_data = self.generate_email_summary(accountant_email)

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = email_data['subject']
            msg['From'] = f"{smtp_config.get('sender_name', 'Service Paie')} <{smtp_config['sender_email']}>"
            msg['To'] = accountant_email

            # Attach text and HTML parts
            part1 = MIMEText(email_data['text_body'], 'plain', 'utf-8')
            part2 = MIMEText(email_data['html_body'], 'html', 'utf-8')
            msg.attach(part1)
            msg.attach(part2)

            # Attach JSON report as file
            report_json = json.dumps(email_data['report_data'], indent=2, ensure_ascii=False)
            attachment = MIMEBase('application', 'json')
            attachment.set_payload(report_json.encode('utf-8'))
            encoders.encode_base64(attachment)
            attachment.add_header(
                'Content-Disposition',
                f'attachment; filename=rapport_paies_{self.report.timestamp.strftime("%Y%m%d_%H%M%S")}.json'
            )
            msg.attach(attachment)

            # Send email
            with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port']) as server:
                server.starttls()
                server.login(smtp_config['sender_email'], smtp_config['sender_password'])
                server.send_message(msg)

            logger.info(f"Email report sent successfully to {accountant_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email report: {e}")
            return False

    def export_to_excel(self, company: str, month: str) -> io.BytesIO:
        """
        Export comprehensive agent report to Excel

        Args:
            company: Company name
            month: Month string (MM-YYYY)

        Returns:
            BytesIO buffer containing Excel file
        """
        output = io.BytesIO()
        workbook = Workbook(output, {'in_memory': True})

        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#34495e',
            'font_color': 'white',
            'border': 1
        })
        auto_format = workbook.add_format({
            'bg_color': '#d4edda',
            'border': 1
        })
        manual_format = workbook.add_format({
            'bg_color': '#fff3cd',
            'border': 1
        })
        anomaly_format = workbook.add_format({
            'bg_color': '#f8d7da',
            'border': 1
        })
        number_format = workbook.add_format({
            'num_format': '#,##0.00',
            'border': 1
        })

        # SHEET 1: Summary
        summary_sheet = workbook.add_worksheet('Résumé')
        summary_sheet.write('A1', 'RAPPORT DE TRAITEMENT AUTOMATIQUE DES PAIES', header_format)
        summary_sheet.write('A2', f'Entreprise: {company}')
        summary_sheet.write('A3', f'Période: {month}')
        summary_sheet.write('A4', f'Date du rapport: {self.report.timestamp.strftime("%d/%m/%Y %H:%M")}')

        summary_sheet.write('A6', 'Statistiques', header_format)
        summary_sheet.write('A7', 'Employés traités:')
        summary_sheet.write('B7', self.report.processed_count)
        summary_sheet.write('A8', 'Modifications automatiques:')
        summary_sheet.write('B8', self.report.automatic_count)
        summary_sheet.write('A9', 'Cas signalés:')
        summary_sheet.write('B9', self.report.flagged_count)
        summary_sheet.write('A10', 'Anomalies détectées:')
        summary_sheet.write('B10', len(self.report.anomalies))
        summary_sheet.write('A11', 'Tendances analysées:')
        summary_sheet.write('B11', len(self.report.trends))

        # SHEET 2: Automatic Modifications
        if self.report.modifications:
            mods_sheet = workbook.add_worksheet('Modifications Auto')
            headers = ['Matricule', 'Employé', 'Champ', 'Ancienne Valeur', 'Nouvelle Valeur', 'Raison', 'Confiance %']
            for col, header in enumerate(headers):
                mods_sheet.write(0, col, header, header_format)

            row = 1
            for mod in self.report.modifications:
                if mod.automatic:
                    mods_sheet.write(row, 0, mod.matricule, auto_format)
                    mods_sheet.write(row, 1, mod.employee_name, auto_format)
                    mods_sheet.write(row, 2, mod.field, auto_format)
                    mods_sheet.write(row, 3, mod.old_value, number_format)
                    mods_sheet.write(row, 4, mod.new_value, number_format)
                    mods_sheet.write(row, 5, mod.reason, auto_format)
                    mods_sheet.write(row, 6, mod.confidence * 100, auto_format)
                    row += 1

            mods_sheet.autofilter(0, 0, row - 1, len(headers) - 1)
            mods_sheet.set_column('A:A', 12)
            mods_sheet.set_column('B:B', 25)
            mods_sheet.set_column('C:C', 20)
            mods_sheet.set_column('D:E', 15)
            mods_sheet.set_column('F:F', 50)
            mods_sheet.set_column('G:G', 12)

        # SHEET 3: Flagged Cases
        if self.report.flagged_cases:
            flagged_sheet = workbook.add_worksheet('Cas Signalés')
            headers = ['Matricule', 'Employé', 'Raison', 'Remarque', 'Mois']
            for col, header in enumerate(headers):
                flagged_sheet.write(0, col, header, header_format)

            row = 1
            for case in self.report.flagged_cases:
                flagged_sheet.write(row, 0, case.get('matricule', ''), manual_format)
                flagged_sheet.write(row, 1, case.get('employee_name', ''), manual_format)
                flagged_sheet.write(row, 2, case.get('reason', ''), manual_format)
                flagged_sheet.write(row, 3, case.get('remark', ''), manual_format)
                flagged_sheet.write(row, 4, case.get('month', ''), manual_format)
                row += 1

            flagged_sheet.autofilter(0, 0, row - 1, len(headers) - 1)
            flagged_sheet.set_column('A:A', 12)
            flagged_sheet.set_column('B:B', 25)
            flagged_sheet.set_column('C:C', 40)
            flagged_sheet.set_column('D:D', 40)
            flagged_sheet.set_column('E:E', 12)

        # SHEET 4: Anomalies
        if self.report.anomalies:
            anomaly_sheet = workbook.add_worksheet('Anomalies')
            headers = ['Matricule', 'Employé', 'Champ', 'Valeur Précédente', 'Valeur Actuelle', 'Variation %']
            for col, header in enumerate(headers):
                anomaly_sheet.write(0, col, header, header_format)

            row = 1
            for anomaly in self.report.anomalies:
                anomaly_sheet.write(row, 0, anomaly['matricule'], anomaly_format)
                anomaly_sheet.write(row, 1, anomaly['employee_name'], anomaly_format)
                anomaly_sheet.write(row, 2, anomaly['field'], anomaly_format)
                anomaly_sheet.write(row, 3, anomaly['previous_value'], number_format)
                anomaly_sheet.write(row, 4, anomaly['current_value'], number_format)
                anomaly_sheet.write(row, 5, anomaly['change_percent'], number_format)
                row += 1

            anomaly_sheet.autofilter(0, 0, row - 1, len(headers) - 1)
            anomaly_sheet.set_column('A:A', 12)
            anomaly_sheet.set_column('B:B', 25)
            anomaly_sheet.set_column('C:C', 25)
            anomaly_sheet.set_column('D:E', 15)
            anomaly_sheet.set_column('F:F', 15)

        # SHEET 5: Historical Trends
        if self.report.trends:
            trends_sheet = workbook.add_worksheet('Tendances Historiques')
            headers = ['Matricule', 'Employé', 'Champ', 'Moyenne', 'Écart-type', 'Direction', 'Volatilité', 'Mois', 'Valeurs']
            for col, header in enumerate(headers):
                trends_sheet.write(0, col, header, header_format)

            row = 1
            for trend in self.report.trends:
                trends_sheet.write(row, 0, trend.matricule)
                trends_sheet.write(row, 1, trend.employee_name)
                trends_sheet.write(row, 2, trend.field)
                trends_sheet.write(row, 3, trend.avg_value, number_format)
                trends_sheet.write(row, 4, trend.std_dev, number_format)
                trends_sheet.write(row, 5, trend.trend_direction)
                trends_sheet.write(row, 6, trend.volatility)
                trends_sheet.write(row, 7, ', '.join(trend.months))
                trends_sheet.write(row, 8, ', '.join([f"{v:.2f}" for v in trend.values]))
                row += 1

            trends_sheet.autofilter(0, 0, row - 1, len(headers) - 1)
            trends_sheet.set_column('A:A', 12)
            trends_sheet.set_column('B:B', 25)
            trends_sheet.set_column('C:C', 20)
            trends_sheet.set_column('D:E', 15)
            trends_sheet.set_column('F:F', 15)
            trends_sheet.set_column('G:G', 12)
            trends_sheet.set_column('H:H', 30)
            trends_sheet.set_column('I:I', 40)

        # SHEET 6: Detailed Trends by Employee (with sparklines if possible)
        if self.report.trends:
            detail_sheet = workbook.add_worksheet('Détails Tendances')

            # Group trends by employee
            employee_trends = {}
            for trend in self.report.trends:
                key = f"{trend.matricule}_{trend.employee_name}"
                if key not in employee_trends:
                    employee_trends[key] = []
                employee_trends[key].append(trend)

            row = 0
            for emp_key, trends in employee_trends.items():
                # Employee header
                detail_sheet.write(row, 0, trends[0].employee_name, header_format)
                detail_sheet.write(row, 1, f"({trends[0].matricule})", header_format)
                row += 1

                # Trend details for this employee
                for trend in trends:
                    detail_sheet.write(row, 0, trend.field)
                    detail_sheet.write(row, 1, f"Direction: {trend.trend_direction}")
                    detail_sheet.write(row, 2, f"Volatilité: {trend.volatility}")
                    detail_sheet.write(row, 3, f"Moyenne: {trend.avg_value:.2f}")

                    # Write historical values
                    for i, (month, value) in enumerate(zip(trend.months, trend.values)):
                        detail_sheet.write(row, 4 + i, value, number_format)

                    row += 1

                row += 1  # Space between employees

            detail_sheet.set_column('A:A', 20)
            detail_sheet.set_column('B:C', 20)
            detail_sheet.set_column('D:D', 15)

        workbook.close()
        output.seek(0)

        logger.info("Excel report generated successfully")
        return output
