---
name: batch-data-processing
description: Optimize batch data processing for ETL pipelines, financial data updates, and bulk database operations. Use when processing large datasets, implementing batch updates, or optimizing data warehouse operations.
---

# Batch Data Processing

Optimize batch processing for ETL pipelines and data warehouse operations.

## Batch Processing Pattern

### Basic Structure

```python
def batch_process(items: list, batch_size: int = 50, delay: float = 0.1):
    """Process items in batches with delay"""
    total = len(items)
    success_count = 0
    failed_count = 0
    
    for i in range(0, total, batch_size):
        batch = items[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        
        logger.info(f"[批次 {batch_num}/{total_batches}] 处理 {len(batch)} 项")
        
        # Process batch
        for item in batch:
            try:
                process_item(item)
                success_count += 1
            except Exception as e:
                logger.error(f"处理失败: {e}")
                failed_count += 1
        
        # Delay between batches
        if i + batch_size < total:
            time.sleep(delay)
    
    return success_count, failed_count
```

## Database Batch Operations

### Bulk Insert Pattern

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def bulk_insert_records(records: list, model_class, batch_size: int = 1000):
    """Bulk insert records efficiently"""
    session = get_session()
    try:
        # Use bulk_insert_mappings for better performance
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            session.bulk_insert_mappings(model_class, batch)
            session.commit()
            logger.debug(f"插入批次 {i//batch_size + 1}: {len(batch)} 条")
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
```

### Batch Update Pattern

```python
def batch_update_existing(session, records: list, model_class, 
                          update_fields: list, batch_size: int = 500):
    """Batch update existing records"""
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        
        # Query existing records
        ts_codes = [r['ts_code'] for r in batch]
        existing = session.query(model_class).filter(
            model_class.ts_code.in_(ts_codes)
        ).all()
        
        # Update in bulk
        update_mappings = []
        for record in batch:
            update_mappings.append({
                'ts_code': record['ts_code'],
                **{field: record[field] for field in update_fields}
            })
        
        session.bulk_update_mappings(model_class, update_mappings)
        session.commit()
```

## Concurrent Batch Processing

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def concurrent_batch_process(items: list, max_workers: int = 3, 
                            batch_size: int = 50):
    """Process batches concurrently"""
    result = {}
    result_lock = threading.Lock()
    
    def process_batch(batch_items: list) -> dict:
        batch_result = {}
        for item in batch_items:
            try:
                batch_result[item] = process_item(item)
            except Exception as e:
                logger.debug(f"处理失败 {item}: {e}")
        return batch_result
    
    # Split into batches
    batches = [items[i:i+batch_size] 
               for i in range(0, len(items), batch_size)]
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_batch, batch): batch 
                   for batch in batches}
        
        for future in as_completed(futures):
            batch_result = future.result()
            with result_lock:
                result.update(batch_result)
    
    return result
```

## Progress Tracking

```python
def batch_process_with_progress(items: list, batch_size: int = 50,
                                log_interval: int = 10):
    """Process with progress logging"""
    total = len(items)
    processed = 0
    
    for i in range(0, total, batch_size):
        batch = items[i:i+batch_size]
        
        for item in batch:
            process_item(item)
            processed += 1
            
            # Log progress periodically
            if processed % log_interval == 0:
                progress_pct = (processed / total * 100) if total > 0 else 0
                logger.info(f"📊 进度: {processed}/{total} ({progress_pct:.1f}%)")
```

## Best Practices

1. **Batch size**: 50-100 for API calls, 500-1000 for DB operations
2. **Add delays**: 0.1-0.5s between batches for API calls
3. **Error handling**: Continue processing on individual failures
4. **Progress logging**: Log every N items or every batch
5. **Transaction management**: Commit in batches, not per item
6. **Memory management**: Process in chunks for large datasets
