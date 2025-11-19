# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
- In all interactions and commit messages, be extremely concise and sacrifice grammar for the sake of concision. Do not use emojis.
- You are an expert who double checks things, you are skeptical and you do research. I am not always right. Neither are you, we both strive for accuracy.
- When suggesting code changes, only suggest code that is necessary to achieve the requested change and that will drastically improve the codebase and/or project.
- use uv when possible vs pip.
- use uv run not python.

## Plan
- at the end of each plan, give me a list of unresolved questions to answer if any. Make the questions extremely concise. Sacrifice grammar for the sake of concision.

## Project Overview

Monaco Payroll System - A comprehensive payroll management application (in French) for Monaco-based accounting firms. Generates French-language paystubs (bulletins de paie), pay journals, PTO provisions, and DSM XML declarations. Supports 300+ clients with multi-country taxation (Monaco, France, Italy) and intelligent edge case detection.

**Target Users**: 30-person accounting firm managing payroll for companies and individuals in Monaco.

### Data Flow Overview

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
