---
name: financial-data-validator
description: Validate financial data completeness and quality for stock analysis. Use when processing financial indicators, income statements, cash flow statements, or when checking data integrity before calculations.
---

# Financial Data Validator

Validates financial data completeness and quality for stock quantitative analysis.

## Validation Checklist

### Required Fields

For fundamental analysis, verify these fields exist:

```python
REQUIRED_FIELDS = {
    'roe': 'Return on Equity',
    'net_margin': 'Net Profit Margin',
    'gross_margin': 'Gross Profit Margin',
    'debt_ratio': 'Debt Ratio',
    'revenue': 'Revenue',
    'revenue_growth': 'Revenue Growth Rate',
    'op_cf': 'Operating Cash Flow',
    'total_debt': 'Total Debt',
    'total_asset': 'Total Assets'
}
```

### Data Quality Checks

```python
def validate_financial_data(data: dict) -> tuple[bool, list[str]]:
    """Validate financial data quality"""
    errors = []
    
    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in data or data[field] is None:
            errors.append(f"Missing required field: {field}")
    
    # Check for invalid values
    if 'roe' in data:
        if data['roe'] is not None and (data['roe'] > 1.0 or data['roe'] < -1.0):
            errors.append(f"Invalid ROE: {data['roe']} (expected -1.0 to 1.0)")
    
    # Check for NaN/Inf
    for key, value in data.items():
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                errors.append(f"Invalid value in {key}: {value}")
    
    return len(errors) == 0, errors
```

### Safe Float Conversion

```python
import math

def safe_float(value, default=0.0):
    """Safely convert to float, handling NaN, inf, and None"""
    if value is None:
        return default
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return default
    try:
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    except (ValueError, TypeError):
        return default
```

## Report Date Validation

```python
def validate_report_date(report_date: str) -> bool:
    """Validate report date format and recency"""
    try:
        year = int(report_date[:4])
        month = int(report_date[4:6])
        day = int(report_date[6:8])
        
        # Check format: YYYYMMDD
        if len(report_date) != 8:
            return False
        
        # Check if date is reasonable (not too old, not future)
        from datetime import datetime
        report_dt = datetime(year, month, day)
        now = datetime.now()
        
        # Report should be within last 2 years
        if (now - report_dt).days > 730:
            return False
        
        # Report should not be in future
        if report_dt > now:
            return False
        
        return True
    except:
        return False
```

## Usage Pattern

```python
# Before using financial data
is_valid, errors = validate_financial_data(financial_data)
if not is_valid:
    logger.warning(f"Data validation failed: {errors}")
    return None

# Use safe conversion
roe = safe_float(financial_data.get('roe'), 0.0)
```
