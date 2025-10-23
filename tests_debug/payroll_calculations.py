# In Streamlit or Python console
from services.payroll_calculations import CalculateurPaieMonaco, MonacoPayrollConstants

# Load constants for year
constants = MonacoPayrollConstants(year=2025)

# Create calculator
calc = CalculateurPaieMonaco(constants)

# Test employee data (dict)
employee = {
    'matricule': '001',
    'nom': 'TEST',
    'salaire_base': 3000.00,
    'base_heures': 169,
    # ... other required fields
}

# Process payslip
result = calc.process_employee_payslip(employee)
print(f"Net: {result['salaire_net']}, Charges: {result['total_charges_salariales']}")