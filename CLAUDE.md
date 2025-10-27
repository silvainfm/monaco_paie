# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
- In all interactions adn commit messages, be extremely concise ans sacrifice grammar for the sake of concision.
- When suggesting code changes, only suggest code that is necessary to achieve the requested change and that will drastically improve the codebase and/or project.
- use uv when possible vs pip.
- use uv run not python.

## Plan
- at the end of each plan, give me a list of unresolved questions to answer if any. Make the questions extremely concise. Sacrifice grammar for the sake of concision.

## Project Overview

Monaco Payroll System - A comprehensive payroll management application for Monaco-based accounting firms. Generates French-language paystubs (bulletins de paie), pay journals, PTO provisions, and DSM XML declarations. Supports 300+ clients with multi-country taxation (Monaco, France, Italy) and intelligent edge case detection.

**Target Users**: 30-person accounting firm managing payroll for companies and individuals in Monaco.

## Architecture Overview

### Service Layer Structure

The application uses a **layered architecture** with 12 specialized services in `/services/`:

**Core Payroll Processing**:
- `payroll_system.py` - Main orchestrator (`IntegratedPayrollSystem`)
- `payroll_calculations.py` - Monaco-specific calculations, social charges, PTO management
  - Key classes: `CalculateurPaieMonaco`, `ChargesSocialesMonaco`, `ValidateurPaieMonaco`, `GestionnaireCongesPayes`
  - Handles 18 different social charges (CAR, CCSS, ASSEDIC, retirement, etc.) with tranche-based rates

**Data Management**:
- `data_mgt.py` - DuckDB connection pool, schema management, CRUD operations
  - Primary table: `payroll_data` (113 columns, composite PK: company_id, period_year, period_month, matricule)
  - Thread-safe with connection pooling (4 threads, 2GB limit)
  - DuckDB database, located at `data/payroll.duckdb`. No migrations needed - schema is auto-created by `DataManager` on first run.

**Document Generation**:
- `pdf_generation.py` - Generates paystubs, journals, PTO provisions using ReportLab
  - Supports 23 salary rubric codes and 9 charge codes
- `dsm_xml_generator.py` - Creates DSM 2.0 XML declarations for Monaco Caisses Sociales

**Intelligence & Automation**:
- `edge_case_agent.py` - Intelligent anomaly detection and auto-correction
  - `RemarkParser`: NLP pattern matching for 6 edge case categories (new hire, departure, salary change, bonus, unpaid leave, prorate)
  - `HistoricalTrend`: Statistical analysis (avg, std dev, volatility) to flag anomalies
  - Auto-corrects with >0.85 confidence, flags for manual review otherwise

**Communication**:
- `email_archive.py` - Email distribution with compliance audit trail
- `oauth2_integration.py` - Office 365 OAuth2 for secure email sending

**Cross-Border & I/O**:
- `import_export.py` - Excel I/O, cross-border taxation (France CSG/CRDS, Italy IRPEF)
- `auth.py` - User management with bcrypt (2 roles: admin, comptable)

**Supporting**:
- `payslip_helpers.py` - UI helper functions for rubric codes and validation
- `scheduler.py` - Job scheduling framework for automation

### Data Flow Pipeline

```
Excel Import → DataConsolidation → DuckDB
    ↓
IntegratedPayrollSystem.process_monthly_payroll()
    ├─ Load period data
    ├─ Calculate (CalculateurPaieMonaco)
    ├─ Validate (ValidateurPaieMonaco)
    └─ Edge case detection (EdgeCaseAgent)
    ↓
Accountant Review/Validation (Streamlit UI)
    ↓
Save to DuckDB → Generate PDFs → Send Emails → DSM XML
```

### Key Configuration Files

- `config/payroll_rates.csv` - Social charge rates and ceilings by year (2024, 2025, 2026)
  - Format: Category, Type, Code, taux_2024, taux_2025, taux_2026
  - Critical constants: T1 (3428€), T2 (13712€), SMIC (11.65€/h), base hours (169h/month)
- `config/company_info.json` - Company details for PDF headers
- `data/users.parquet` - User credentials (bcrypt hashed, 12 rounds)

### Database Schema

**`payroll_data` table** (Primary Key: company_id, period_year, period_month, matricule):
- Employee info: matricule, nom, prenom, email, date_naissance, emploi, qualification
- Hours: base_heures, heures_payees, heures_conges_payes, heures_absence, heures_sup_125/150, heures_jours_feries, heures_dimanche
- Salary: salaire_base, taux_horaire, prime, type_prime
- Benefits: tickets_restaurant, avantage_logement, avantage_transport
- Cross-border: pays_residence, ccss_number, teletravail, pays_teletravail
- Charges: total_charges_salariales, total_charges_patronales, details_charges (JSON)
- PTO: cp_acquis_n1, cp_pris_n1, cp_restants_n1, cp_acquis_n, cp_pris_n, cp_restants_n
- Totals: salaire_brut, salaire_net, cumul_brut, cumul_net_percu, cost_total_employeur
- Edge cases: edge_case_flag (BOOLEAN), edge_case_reason, statut_validation, remarques

**`companies` table**: id, name, siret, address, phone, email

## Monaco-Specific Context

**Language**: All UI, PDFs, and user-facing text in French
- Paystub = Bulletin de paie
- Pay journal = Journal de paie
- PTO = Congés payés
- Social charges = Charges sociales

**Regulatory Compliance**:
- DSM (Déclaration Sociale Monaco): Monthly XML submission to Caisses Sociales
- Meal tickets: 60% employer / 40% employee participation
- SMIC Monaco: 11.65€/hour (as of 2025)
- Work week: 169 hours/month standard

**Edge Case Categories** (parsed from "remarques" field):
1. `new_hire`: "embauche", "nouveau", "entrée le DD/MM"
2. `departure`: "départ", "sortie le DD/MM", "démission"
3. `salary_change`: "augmentation", "modification salaire"
4. `bonus`: "prime", "bonus", "13ème mois"
5. `unpaid_leave`: "congé sans solde", "arrêt maladie"
6. `prorate`: "prorata", "du DD au DD"

## Common Development Tasks

### Adding a New Salary Rubric
1. Add rubric code to `PDFGeneratorService.get_salary_rubrics()` in `services/pdf_generation.py`
2. Update calculation logic in `CalculateurPaieMonaco.process_employee_payslip()` in `services/payroll_calculations.py`
3. Add UI field in relevant Streamlit page in `app.py`
4. Update database schema if new column needed in `data_mgt.py`

### Adding a New Social Charge
1. Add charge to `ChargesSocialesMonaco` class in `services/payroll_calculations.py`
2. Add rate to `config/payroll_rates.csv` (CSV: Category=CHARGE, Type=SALARIAL/PATRONAL, Code=NEW_CODE, taux_YYYY=rate)
3. Update charge total calculations
4. Add to PDF generation in `pdf_generation.py` charge codes

### Modifying Edge Case Detection
1. Edit `RemarkParser` patterns in `services/edge_case_agent.py`
2. Add new category to `EdgeCaseCategory` enum if needed
3. Update `EdgeCaseAgent.process()` logic for auto-correction rules
4. Adjust confidence thresholds (default: >0.85 for auto-correction)

## Role-Based Access Control

**Admin Role**:
- Full system access
- User management
- Configuration changes
- All periods accessible

**Comptable (Accountant) Role**:
- Can modify last 2 months of paystubs only
- Cannot modify older data (unless new company)
- Can validate and generate PDFs
- Cannot manage users

Check role in code:
```python
if st.session_state.get('role') == 'admin':
    # Admin-only features
```

## File Structure

```
.
├── app.py                    # Main Streamlit application (127KB - comprehensive UI)
├── services/                 # Business logic layer
│   ├── payroll_system.py     # Main orchestrator
│   ├── payroll_calculations.py   # Core calculations (60KB)
│   ├── data_mgt.py           # DuckDB operations
│   ├── pdf_generation.py     # PDF documents (77KB)
│   ├── edge_case_agent.py    # Intelligent automation (44KB)
│   ├── email_archive.py      # Email distribution (60KB)
│   ├── import_export.py      # I/O operations
│   ├── dsm_xml_generator.py  # XML declarations
│   ├── auth.py               # Authentication
│   ├── oauth2_integration.py # Office 365 integration
│   ├── scheduler.py          # Job automation
│   └── payslip_helpers.py    # UI helpers
├── config/
│   ├── payroll_rates.csv     # Rates and ceilings by year
│   └── company_info.json     # Company details
├── data/
│   ├── payroll.duckdb        # Main database (800KB)
│   ├── users.parquet         # User credentials
│   ├── companies/            # Company-specific data
│   ├── consolidated/         # Consolidated reports
│   └── audit_logs/           # Modification logs
├── pyproject.toml            # Project dependencies (uv/pip)
├── requirements.txt          # Flat dependencies
└── README.md                 # Project overview and instructions
```

## Important Constraints

**Data Editing Restrictions**:
- Accountants can only modify last 2 months of paystubs
- Exception: New companies (no historical data) - all periods editable
- Enforced at UI level in `app.py` validation pages

**Calculation Immutability**:
- Social charge rates loaded from `config/payroll_rates.csv` - **do not hardcode**
- Use `MonacoPayrollConstants(year=YYYY)` to get year-specific rates
- Charges recalculated on every save to ensure consistency

**PDF Requirements**:
- Must fit on single A4 page
- Blue color scheme (#1a5f9e)
- French formatting: comma decimals (1 234,56 €), DD/MM/YYYY dates
- Company info from `config/company_info.json`

**Concurrency**:
- DuckDB supports 10-15 concurrent users (configured in `data_mgt.py`)
- File locking used for `users.parquet` (5s timeout)
- Session state in Streamlit - not shared between users

## Technology Stack

- **Backend**: Python 3.11+
- **Database**: DuckDB (in-process analytical DB, thread-safe)
- **DataFrames**: Polars (preferred over Pandas for performance) https://docs.pola.rs/api/python/stable/search.html
- **UI**: Streamlit
- **PDF**: ReportLab
- **Authentication**: Bcrypt (12 rounds)
- **Email**: SMTP/OAuth2 (Office 365)
- **Package Manager**: uv (fast pip replacement)

## Future Features (README.md)

Not yet implemented:
- Automatic yearly rate/ceiling updates
- Automated email send of DSM XML to Monaco government
- Automated email validation workflow with clients before employee distribution
- Regularization lines for correcting prior period errors
