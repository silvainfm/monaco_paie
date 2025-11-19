"""
Integrated Payroll System
========================
Main system orchestrator for Monaco payroll processing
"""

import json
import logging
import traceback
import streamlit as st
import polars as pl
from datetime import datetime
from pathlib import Path
from typing import Dict

from services.payroll_calculations import (
    CalculateurPaieMonaco,
    ValidateurPaieMonaco,
    GestionnaireCongesPayes
)
from services.import_export import ExcelImportExport, DataConsolidation
from services.data_mgt import DataManager

logger = logging.getLogger(__name__)


class IntegratedPayrollSystem:
    """Système intégré de gestion de paie"""

    def __init__(self, config_dir: Path = None):
        """Initialiser le système complet"""
        self.config_dir = config_dir or Path("data/config")
        self.calculator = CalculateurPaieMonaco()
        self.validator = ValidateurPaieMonaco()
        self.pto_manager = GestionnaireCongesPayes()
        self.excel_manager = ExcelImportExport()
        self.data_consolidator = DataConsolidation()
        self.company_info = self._load_company_info()

    def _load_company_info(self) -> Dict:
        """Charger les informations de l'entreprise"""
        config_file = self.config_dir / "company_info.json"

        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        default_info = {
            'name': 'Cabinet Comptable Monaco',
            'siret': '000000000',
            'address': '98000 MONACO',
            'phone': '+377 93 00 00 00',
            'email': 'contact@cabinet.mc'
        }

        # Create config directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_info, f, indent=2)

        return default_info

    def process_monthly_payroll(self, company_id: str, period: str) -> Dict:
        """Traiter la paie mensuelle complète"""
        report = {
            'period': period,
            'company_id': company_id,
            'start_time': datetime.now(),
            'steps': []
        }

        try:
            month, year = map(int, period.split('-'))
            df = DataManager.load_period_data(company_id, month, year)

            if df.is_empty():
                report['error'] = "Aucune donnée trouvée pour cette période"
                return report

            report['steps'].append({
                'step': 'Chargement des données',
                'status': 'success',
                'count': len(df)
            })

            processed_data = []
            edge_cases = []

            # Convert to list of dicts for processing
            for row in df.iter_rows(named=True):
                # Get cumulative annual gross salary for plafond calculations
                matricule = row.get('matricule', '')
                cumul_brut_annuel = DataManager.get_cumul_brut_annuel(
                    company_id, matricule, year, month
                ) if matricule else 0.0

                payslip = self.calculator.process_employee_payslip(row, cumul_brut_annuel=cumul_brut_annuel)
                is_valid, issues = self.validator.validate_payslip(payslip)

                if not is_valid or row.get('remarques') or row.get('date_sortie'):
                    edge_cases.append({
                        'matricule': row.get('matricule', ''),
                        'nom': row.get('nom', ''),
                        'prenom': row.get('prenom', ''),
                        'issues': issues,
                        'remarques': row.get('remarques'),
                        'date_sortie': row.get('date_sortie')
                    })
                    payslip['statut_validation'] = 'À vérifier'
                    payslip['edge_case_flag'] = True
                    payslip['edge_case_reason'] = '; '.join(issues) if issues else 'Remarques ou date de sortie'
                else:
                    payslip['statut_validation'] = True
                    payslip['edge_case_flag'] = False
                    payslip['edge_case_reason'] = ''

                # Keep original data
                for key in row.keys():
                    if key not in payslip:
                        payslip[key] = row[key]

                processed_data.append(payslip)

            processed_df = pl.DataFrame(processed_data)
            DataManager.save_period_data(processed_df, company_id, month, year)

            report['steps'].append({
                'step': 'Calcul des paies',
                'status': 'success',
                'processed': len(processed_data),
                'validated': len(processed_data) - len(edge_cases),
                'edge_cases': len(edge_cases)
            })

            st.session_state['processed_data'] = processed_df
            st.session_state['edge_cases'] = edge_cases

            report['success'] = True
            report['end_time'] = datetime.now()
            report['duration'] = (report['end_time'] - report['start_time']).total_seconds()

        except Exception as e:
            report['error'] = str(e)
            report['success'] = False
            logger.error(f"Erreur traitement paie: {e}")
            logger.error(traceback.format_exc())

        return report
