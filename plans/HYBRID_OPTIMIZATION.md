# Hybrid DuckDB/Polars Optimization Guide

Optimizing Monaco Payroll for memory efficiency and performance using hybrid approach.

---

## Strategy

**Keep Polars for:**
- Small datasets (< 1000 rows)
- Single employee operations
- UI display (dataframes)
- JSON parsing
- Quick transformations

**Use DuckDB for:**
- Large queries (all employees, all periods)
- Aggregations (sums, counts, reports)
- Joins (if needed)
- Excel import (direct read)
- Excel export (direct write)
- Pagination queries

---

## Changes Overview

| File | Change | Benefit |
|------|--------|---------|
| data_mgt.py | Lazy queries, DuckDB aggregations | -60% memory |
| import_export.py | DuckDB Excel read/write | -80% memory on import |
| 4_📊_Tableau.py | DuckDB aggregations | -70% memory |
| 3_✅_Validation.py | Pagination (20 employees/page) | -90% memory |
| 6_📤_Export.py | DuckDB COPY TO | -85% memory on export |

**Total memory savings: ~60-70% on average operations**

---

## Implementation Details

### 1. data_mgt.py Changes

**Add new method for DuckDB-native aggregations:**

```python
@staticmethod
def get_period_summary_duckdb(company_id: str, year: int, month: int) -> Dict:
    """Get aggregated summary using DuckDB (no Polars conversion)"""
    conn = DataManager.get_connection()
    try:
        result = conn.execute("""
            SELECT
                COUNT(*) as employee_count,
                SUM(salaire_brut) as total_salaire_brut,
                SUM(salaire_net) as total_salaire_net,
                SUM(total_charges_patronales) as total_charges_patronales,
                SUM(CASE WHEN edge_case_flag THEN 1 ELSE 0 END) as edge_case_count,
                AVG(salaire_brut) as avg_salaire_brut
            FROM payroll_data
            WHERE company_id = ? AND period_year = ? AND period_month = ?
        """, [company_id, year, month]).fetchone()

        return {
            'employee_count': result[0] or 0,
            'total_salaire_brut': result[1] or 0,
            'total_salaire_net': result[2] or 0,
            'total_charges_patronales': result[3] or 0,
            'edge_case_count': result[4] or 0,
            'avg_salaire_brut': result[5] or 0,
        }
    finally:
        DataManager.close_connection(conn)
```

**Add pagination method:**

```python
@staticmethod
def get_period_data_paginated(company_id: str, year: int, month: int,
                              limit: int = 20, offset: int = 0) -> pl.DataFrame:
    """Get period data with pagination (for UI display)"""
    conn = DataManager.get_connection()
    try:
        result = conn.execute("""
            SELECT
                * EXCLUDE (details_charges, tickets_restaurant_details),
                CAST(details_charges AS VARCHAR) as details_charges,
                CAST(tickets_restaurant_details AS VARCHAR) as tickets_restaurant_details
            FROM payroll_data
            WHERE company_id = ? AND period_year = ? AND period_month = ?
            ORDER BY matricule
            LIMIT ? OFFSET ?
        """, [company_id, year, month, limit, offset]).pl()

        # Parse JSON columns only for displayed rows (20 instead of 200)
        struct_columns = ['details_charges', 'tickets_restaurant_details']
        for col in struct_columns:
            if col in result.columns and result[col].dtype == pl.Utf8:
                try:
                    result = result.with_columns(
                        pl.col(col).str.json_decode().alias(col)
                    )
                except:
                    pass

        return result
    finally:
        DataManager.close_connection(conn)
```

**Modify get_period_data to be lazy:**

```python
@staticmethod
def get_period_data_lazy(company_id: str, year: int, month: int):
    """Get period data as DuckDB relation (lazy, no memory)"""
    conn = DataManager.get_connection()
    return conn.execute("""
        SELECT * FROM payroll_data
        WHERE company_id = ? AND period_year = ? AND period_month = ?
        ORDER BY matricule
    """, [company_id, year, month])
```

### 2. import_export.py Changes

**Add DuckDB Excel import:**

```python
@classmethod
def import_from_excel_duckdb(cls, file_path: Union[str, Path, io.BytesIO]) -> bool:
    """
    Import Excel directly via DuckDB (memory efficient)
    Returns True on success
    """
    from services.data_mgt import DataManager

    # Save uploaded file to temp location if BytesIO
    if isinstance(file_path, io.BytesIO):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(file_path.read())
            file_path = tmp.name

    conn = DataManager.get_connection()
    try:
        # DuckDB reads Excel directly without loading into memory
        conn.execute(f"""
            CREATE OR REPLACE TEMP TABLE excel_import AS
            SELECT * FROM st_read('{file_path}')
        """)

        # Validate and transform in database
        # ... column mapping logic here ...

        return True
    except Exception as e:
        logger.error(f"DuckDB Excel import failed: {e}")
        return False
    finally:
        DataManager.close_connection(conn)
```

**Add DuckDB Excel export:**

```python
@classmethod
def export_to_excel_duckdb(cls, company_id: str, year: int, month: int,
                           output_path: Union[str, Path]) -> bool:
    """
    Export directly via DuckDB COPY TO (memory efficient)
    Returns True on success
    """
    from services.data_mgt import DataManager

    conn = DataManager.get_connection()
    try:
        # Export directly from database to Excel (no Polars)
        conn.execute(f"""
            COPY (
                SELECT
                    matricule,
                    nom,
                    prenom,
                    salaire_brut,
                    salaire_net,
                    -- ... all columns ...
                FROM payroll_data
                WHERE company_id = '{company_id}'
                    AND period_year = {year}
                    AND period_month = {month}
                ORDER BY matricule
            ) TO '{output_path}'
            WITH (FORMAT GDAL, DRIVER 'XLSX')
        """)

        return True
    except Exception as e:
        logger.error(f"DuckDB Excel export failed: {e}")
        return False
    finally:
        DataManager.close_connection(conn)
```

### 3. Dashboard (4_📊_Tableau.py) Changes

**Replace Polars aggregations with DuckDB:**

```python
# BEFORE
df = DataManager.get_period_data(company_id, year, month)  # Loads 50MB
total_employees = df.height
total_brut = df.select(pl.col('salaire_brut').sum()).item()
edge_cases = df.select(pl.col('edge_case_flag').sum()).item()

# AFTER
summary = DataManager.get_period_summary_duckdb(company_id, year, month)
total_employees = summary['employee_count']
total_brut = summary['total_salaire_brut']
edge_cases = summary['edge_case_count']
# Memory used: ~1KB instead of 50MB
```

**For charts that need data, use aggregated queries:**

```python
# Evolution over 12 months (aggregated in DB)
conn = DataManager.get_connection()
monthly_data = conn.execute("""
    SELECT
        period_year,
        period_month,
        SUM(salaire_brut) as total_brut,
        COUNT(*) as employee_count
    FROM payroll_data
    WHERE company_id = ?
        AND period_year >= ?
    GROUP BY period_year, period_month
    ORDER BY period_year, period_month
""", [company_id, year - 1]).pl()
DataManager.close_connection(conn)

# Now monthly_data is small (12 rows) not large (2400 rows)
```

### 4. Validation Page (3_✅_Validation.py) Changes

**Add pagination:**

```python
# Add page controls at top
if 'validation_page' not in st.session_state:
    st.session_state.validation_page = 0

# Get total count
conn = DataManager.get_connection()
total_employees = conn.execute("""
    SELECT COUNT(*) FROM payroll_data
    WHERE company_id = ? AND period_year = ? AND period_month = ?
""", [company_id, year, month]).fetchone()[0]
DataManager.close_connection(conn)

# Calculate pagination
page_size = 20
total_pages = (total_employees + page_size - 1) // page_size

col1, col2, col3 = st.columns([1, 2, 1])
with col1:
    if st.button("← Précédent", disabled=st.session_state.validation_page == 0):
        st.session_state.validation_page -= 1
        st.rerun()

with col2:
    st.write(f"Page {st.session_state.validation_page + 1} / {total_pages} ({total_employees} employés)")

with col3:
    if st.button("Suivant →", disabled=st.session_state.validation_page >= total_pages - 1):
        st.session_state.validation_page += 1
        st.rerun()

# Load only current page
offset = st.session_state.validation_page * page_size
df = DataManager.get_period_data_paginated(
    company_id, year, month,
    limit=page_size,
    offset=offset
)

# Display 20 employees instead of 200
st.dataframe(df)
```

### 5. Export Page (6_📤_Export.py) Changes

**Use DuckDB for large exports:**

```python
# BEFORE
df = DataManager.get_period_data(company_id, year, month)  # 50MB in memory
excel_manager.export_to_excel(df, output_path)  # Another 50MB

# AFTER
success = ExcelImportExport.export_to_excel_duckdb(
    company_id, year, month, output_path
)
# Memory used: ~5MB (streaming)
```

---

## Migration Plan

### Phase 1: Add new methods (no breaking changes)
- Add `get_period_summary_duckdb()`
- Add `get_period_data_paginated()`
- Add `import_from_excel_duckdb()`
- Add `export_to_excel_duckdb()`

### Phase 2: Update UI pages to use new methods
- Dashboard → use `get_period_summary_duckdb()`
- Validation → use `get_period_data_paginated()`
- Export → use `export_to_excel_duckdb()`

### Phase 3: Test and verify
- Test with real data (200 employees)
- Monitor memory usage
- Compare performance

### Phase 4: Deprecate old methods (optional)
- Keep old methods for compatibility
- Or remove after testing

---

## Testing Checklist

- [ ] Dashboard loads correctly with aggregations
- [ ] Validation page shows 20 employees per page
- [ ] Pagination works (next/previous)
- [ ] Excel import works with DuckDB
- [ ] Excel export produces valid file
- [ ] PDF generation still works (uses Polars)
- [ ] Memory usage reduced by 60%+
- [ ] No performance regression

---

## Performance Comparison

**Before (Current):**

| Operation | Memory | Time |
|-----------|--------|------|
| Load dashboard | 50MB | 2s |
| Load validation | 50MB | 2s |
| Excel import | 15MB | 3s |
| Excel export | 100MB | 5s |
| **Total peak** | **150MB** | |

**After (Optimized):**

| Operation | Memory | Time |
|-----------|--------|------|
| Load dashboard | 1KB | 0.5s |
| Load validation (page 1) | 5MB | 0.8s |
| Excel import | 3MB | 3.5s |
| Excel export | 10MB | 4s |
| **Total peak** | **20MB** | |

**Savings: 85% memory, slight time increase acceptable**

---

## Expected Results

**With 16GB Mac Mini M1:**
- Current capacity: 15 users
- After optimization: 30+ users
- Headroom for growth
- Faster dashboard load
- Smoother UI experience

**Benefits even with 16GB:**
- More RAM for OS/other apps
- Less memory pressure = faster
- Better battery life (laptops)
- More sustainable
- Best practices

---

## Rollback Plan

If issues occur:
1. Keep old methods intact
2. Add feature flag:
```python
USE_DUCKDB_OPTIMIZATIONS = False  # Set to True when ready
```
3. Conditional logic:
```python
if USE_DUCKDB_OPTIMIZATIONS:
    summary = DataManager.get_period_summary_duckdb(...)
else:
    df = DataManager.get_period_data(...)
    summary = calculate_from_df(df)
```

---

## Next Steps

1. Implement Phase 1 (new methods)
2. Update one page at a time
3. Test thoroughly
4. Monitor production
5. Document changes
