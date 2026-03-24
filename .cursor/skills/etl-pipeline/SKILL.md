---
name: etl-pipeline
description: Design and implement ETL (Extract, Transform, Load) pipelines for financial data. Use when building data warehouse operations, daily updates, or data migration tasks.
---

# ETL Pipeline

Design robust ETL pipelines for financial data processing.

## ETL Structure

### Three-Layer Architecture

```
Raw Layer (raw_fundamental) 
  ↓ Extract & Transform
Clean Layer (fact_fundamental)
  ↓ Transform & Aggregate
Data Warehouse (dim_*, fact_*)
```

## ETL Pattern

### Extract Phase

```python
def extract_fundamental_data(ts_codes: list, report_date: str):
    """Extract data from external API"""
    raw_data = []
    
    for ts_code in ts_codes:
        try:
            data = api.get_fundamental(ts_code, report_date)
            raw_data.append({
                'ts_code': ts_code,
                'end_date': report_date,
                'raw_payload': data,  # Store raw for audit
                'source': 'tushare'
            })
        except Exception as e:
            logger.error(f"Extract failed {ts_code}: {e}")
    
    return raw_data
```

### Transform Phase

```python
def transform_fundamental_data(raw_data: dict) -> dict:
    """Transform raw API data to clean format"""
    return {
        'ts_code': raw_data['ts_code'],
        'end_date': parse_date(raw_data['end_date']),
        'roe': safe_float(raw_data.get('roe'), 0.0),
        'net_margin': safe_float(raw_data.get('netprofit_margin'), 0.0),
        'gross_margin': safe_float(raw_data.get('grossprofit_margin'), 0.0),
        'debt_ratio': safe_float(raw_data.get('debt_to_assets'), 0.0),
        'revenue': safe_float(raw_data.get('revenue'), 0.0),
        'revenue_growth': safe_float(raw_data.get('yoy_sales'), 0.0),
        # ... more fields
    }
```

### Load Phase

```python
def load_fundamental_data(clean_data: list):
    """Load transformed data into data warehouse"""
    session = get_session()
    try:
        # Save to raw layer
        session.bulk_insert_mappings(RawFundamental, raw_data)
        
        # Save to clean layer
        session.bulk_insert_mappings(FactFundamental, clean_data)
        
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
```

## Daily Update Pattern

```python
def daily_update_fundamental(force: bool = False):
    """Daily incremental update with duplicate check"""
    
    # Check if already updated today
    if not force:
        if is_updated_today():
            logger.info("今日已更新，跳过")
            return True
    
    # Get list of stocks to update
    stocks = get_stock_list()
    
    # Extract: Get latest data from API
    raw_data = extract_latest_data(stocks)
    
    # Transform: Clean and validate
    clean_data = [transform(d) for d in raw_data if validate(d)]
    
    # Load: Save to database
    load_data(clean_data)
    
    # Update metadata
    update_update_timestamp()
```

## Error Handling

```python
def robust_etl_process(items: list):
    """ETL with comprehensive error handling"""
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    for item in items:
        try:
            # Extract
            raw = extract(item)
            if not raw:
                skipped_count += 1
                continue
            
            # Transform
            clean = transform(raw)
            if not clean:
                skipped_count += 1
                continue
            
            # Load
            load(clean)
            success_count += 1
            
        except ExtractError as e:
            logger.error(f"Extract failed: {e}")
            failed_count += 1
        except TransformError as e:
            logger.error(f"Transform failed: {e}")
            failed_count += 1
        except LoadError as e:
            logger.error(f"Load failed: {e}")
            failed_count += 1
    
    return success_count, failed_count, skipped_count
```

## Best Practices

1. **Idempotency**: Can be run multiple times safely
2. **Incremental updates**: Only process changed data
3. **Data validation**: Validate before transform
4. **Error recovery**: Continue on individual failures
5. **Audit trail**: Store raw data for debugging
6. **Transaction management**: Commit in batches
7. **Progress tracking**: Log progress for long operations
