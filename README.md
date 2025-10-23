# Logiciel de Paie Monégasque

## Project Overview

Monaco Payroll System - A comprehensive payroll management application for Monaco-based accounting firms. Generates French-language paystubs (bulletins de paie), pay journals, PTO provisions, and DSM XML declarations. Supports 300+ clients with multi-country taxation (Monaco, France, Italy) and intelligent edge case detection.

**Target Users**: 30-person accounting firm managing payroll for companies and individuals in Monaco.


## Prompt used
System Instruction: Absolute Mode • Eliminate: emojis, filler, hype, soft asks, conversational transitions, call-to-action appendixes. • Assume: user retains high-perception despite blunt tone. • Prioritize: blunt, directive phrasing; aim at cognitive rebuilding, not tone-matching. • Disable: engagement/sentiment-boosting behaviors. • Suppress: metrics like satisfaction scores, emotional softening, continuation bias. • Never mirror: user's diction, mood, or affect. • Speak only: to underlying cognitive tier. • No: questions, offers, suggestions, transitions, motivational content. • Terminate reply: immediately after delivering info - no closures. • Goal: restore independent, high-fidelity thinking. • Outcome: model obsolescence via user self-sufficiency.

You are a great engineer with a background in Python and SQL, and you want to build a software to generate paystubs specific to Monaco - in French. Including an agent that can do 70% + of the paystubs each months, highlighting edge cases for the accountants (which will then use the web app).
<context> The software will have the UI for accountants to go in and modify certain data points for each company or employee, before generating PDF Paystubs from that data. There will be 2 roles within the web app , an accountant role and an admin role. Attached are 3 pdf outputs that the web app must give - the paystub for employees, the pay journal and the PTO provision.
The data will either be prepared based on previous paystubs or made new by the accountant.
The data contains the following columns: 
the employees' ID (or matricule), Nom, Prenom, Base heures (169), nombres d'Heures congés payés, nombres d'Heures absence, Type d'absence, Prime, Type de prime, Heures Sup 125, Heures Sup 150, nombres d'Heures jours feries, nombres d'Heures dimanche, Tickets restaurant, Avantage en nature (logement), Avantage en nature (transports), Date de Sortie, Remarques.
The web app will be rendered using streamlit, and duckdb will be used as the database <context>
<audience> This web app is for an accounting firm of 30 employees (accountants/jurists) who all use Windows and the firm has around 300 clients (companies and individuals) <audience>
<task> create the paystub software with multiple pages. For the pdf generation, ask questions before starting those scripts as there are more specification <task>
<task> create an agent that can make the modifications necessary on the edge cases, including understanding the "remarques" in the data to validate those edge cases.
the agent should give a summary of the changes made to the accountant<task>
<thinking> Ask for clarification on the data, the software's use and parameters as necessary.
With the software there will be a need to add paystub data monthly to the database <thinking>

## Features implemented
* Users can modify the 2 last months of paystubs
* drop down menu for rubriques int he valdiation page
* duckdb as the backend

## Features to implement/double check
* csv/excel file with the taux and plafonds (ceilings) for each year
* automatic creation and email send of xml file to declare the salary to the Monaco government
* automatic email send of the paystubs, paystub journal, and PTO provision to the client (the company) for validation before sending them to the employees
* add a ligne for "regularisation" of previous paystubs that had errors or for which new data has been received. In these the base and taux for all "charges" will have to be updated

## Development Commands

### Environment Setup
```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies (uv is used for package management)
uv pip install -e .

# Or use requirements.txt
pip install -r requirements.txt
```

### Running the Application
```bash
# Start Streamlit app
streamlit run app.py

# App runs on http://localhost:8501
```

### Code Quality
```bash
# Format code with Black (line length: 100)
black services/ app.py

# Lint with Ruff
ruff check services/ app.py

# Run tests (when implemented)
pytest
```