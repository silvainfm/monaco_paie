#!/bin/bash
# Common DB inspection queries

DB="data/payroll.duckdb"

echo "=== TABLES ==="
duckdb $DB "SHOW TABLES"

echo -e "\n=== TOTAL RECORDS ==="
duckdb $DB "SELECT COUNT(*) FROM payroll_data"

echo -e "\n=== COMPANIES ==="
duckdb $DB "SELECT * FROM companies"

echo -e "\n=== PERIODS ==="
duckdb $DB "SELECT DISTINCT period_year, period_month, COUNT(*) as employees FROM payroll_data GROUP BY 1,2 ORDER BY 1 DESC, 2 DESC"

echo -e "\n=== SAMPLE DATA ==="
duckdb $DB "SELECT matricule, nom, prenom, salaire_base, company_id, period_year, period_month FROM payroll_data LIMIT 3"

echo -e "\n=== COLUMN COUNT ==="
duckdb $DB "SELECT COUNT(*) as column_count FROM (DESCRIBE payroll_data)"

echo -e "\n=== COLUMNS WITH 'prime' ==="
duckdb $DB "DESCRIBE payroll_data" | grep prime
