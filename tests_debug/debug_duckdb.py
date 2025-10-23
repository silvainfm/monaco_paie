from services.data_mgt import DataManager

dm = DataManager()
conn = dm.get_connection()

# Query period data
result = conn.execute("""
    SELECT matricule, nom, salaire_brut, salaire_net
    FROM payroll_data
    WHERE company_id = 'COMP001'
      AND period_year = 2025
      AND period_month = 10
""").fetchdf()

print(result)
