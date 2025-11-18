# DuckDB Inspection Cheat Sheet

## Interactive Mode
```bash
duckdb data/payroll.duckdb
```

### Useful CLI commands inside DuckDB:
```sql
SHOW TABLES;                    -- List all tables
DESCRIBE payroll_data;          -- Show columns with types
.schema payroll_data            -- Show CREATE TABLE statement
.mode markdown                  -- Pretty output
.exit                           -- Quit
```

## One-Liner Queries (from terminal)

### Schema inspection
```bash
# List all columns
duckdb data/payroll.duckdb "DESCRIBE payroll_data"

# Count columns
duckdb data/payroll.duckdb "SELECT COUNT(*) FROM (DESCRIBE payroll_data)"

# Find columns by name pattern
duckdb data/payroll.duckdb "SELECT column_name FROM (DESCRIBE payroll_data) WHERE column_name LIKE '%prime%'"
```

### Data queries
```bash
# Count records
duckdb data/payroll.duckdb "SELECT COUNT(*) FROM payroll_data"

# Show companies
duckdb data/payroll.duckdb "SELECT * FROM companies"

# Available periods
duckdb data/payroll.duckdb "SELECT DISTINCT period_year, period_month FROM payroll_data ORDER BY 1 DESC, 2 DESC"

# Specific employee
duckdb data/payroll.duckdb "SELECT * FROM payroll_data WHERE matricule = '0000000001'"

# Latest data
duckdb data/payroll.duckdb "SELECT nom, prenom, salaire_base FROM payroll_data ORDER BY period_year DESC, period_month DESC LIMIT 5"
```

### Export data
```bash
# Export to CSV
duckdb data/payroll.duckdb "COPY (SELECT * FROM payroll_data) TO 'payroll_export.csv' (HEADER)"

# Export schema
duckdb data/payroll.duckdb ".schema" > full_schema.sql
```

## Check Migration Status
```bash
# Check if new rubric columns exist
duckdb data/payroll.duckdb "SELECT column_name FROM (DESCRIBE payroll_data) WHERE column_name IN ('prime_anciennete', '13eme_mois', 'commissions', 'heures_sup_200')"

# Expected: 76 cols before migration, 115+ after
duckdb data/payroll.duckdb "SELECT COUNT(*) FROM (DESCRIBE payroll_data)"
```

## Inspect WAL file
```bash
file data/payroll.duckdb.wal
# Shows: "DuckDB Write-Ahead Log" if active writes
```
