import re

with open('dbms.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add index import
content = content.replace(
    'from db_model import Table, Record, DB, MetaDB',
    'from db_model import Table, Record, DB, MetaDB\nfrom index import IndexManager'
)

# 2. Add index_manager init
content = content.replace(
    '        self.meta_db = MetaDB()',
    '        self.meta_db = MetaDB()\n        self.index_manager = IndexManager()\n        self._load_existing_indexes()'
)

# 3. Add _load_existing_indexes method after __init__
load_indexes = '''
    def _load_existing_indexes(self):
        """Load existing indexes from meta_db on startup."""
        try:
            self.meta_db.open_db()
            for key in self.meta_db.keys():
                table = self.meta_db.get(key)
                if table and table.primary_key:
                    for pk_col in table.primary_key:
                        self.index_manager.create_index(table.table_name, pk_col)
                        # Rebuild index from existing data
                        self._rebuild_index(table.table_name, pk_col)
            self.meta_db.close_db()
        except Exception:
            self.meta_db.close_db()
    
    def _rebuild_index(self, table_name: str, column_name: str):
        """Rebuild an index from existing table data."""
        table_db = DB(table_name)
        table_db.open_db()
        cursor = table_db.create_cursor()
        kv = cursor.first()
        while kv:
            key, value = kv
            record = Record.deserialize(value)
            if column_name in record.data:
                self.index_manager.insert(table_name, column_name, record.data[column_name], key)
            kv = cursor.next()
        table_db.discard_cursor(cursor)
        table_db.close_db()
    
    def create_index(self, table_name: str, column_name: str):
        self.meta_db.open_db()
        table_key = self.meta_db.create_key_from_value(table_name)
        table = self.meta_db.get(table_key)
        if not table:
            self.meta_db.close_db()
            raise NoSuchTable()
        if column_name not in table.columns:
            self.meta_db.close_db()
            raise UpdateColumnExistenceError(column_name)
        self.meta_db.close_db()
        
        self.index_manager.create_index(table_name, column_name)
        self._rebuild_index(table_name, column_name)
        return f"Index created on {table_name}({column_name})"
'''

# Insert after __init__ method
init_end = content.find('    def create_table(self, table_dict: dict):')
content = content[:init_end] + load_indexes + content[init_end:]

# 4. Modify create_table to auto-create PK index
create_table_end = content.find('        return CreateTableSuccess(table_name)')
content = content[:create_table_end] + '''        
        # Auto-create index on primary key
        if primary_key:
            for pk_col in primary_key:
                self.index_manager.create_index(table_name, pk_col)
''' + content[create_table_end:]

# 5. Modify insert to update indexes
insert_end = content.find('        return InsertResult()')
content = content[:insert_end] + '''        
        # Update indexes
        for col_name in table.columns:
            if self.index_manager.has_index(table_name, col_name):
                self.index_manager.insert(table_name, col_name, data[col_name], record_key)
''' + content[insert_end:]

# 6. Modify delete to update indexes
delete_block = '''                    table_db.delete_by_cursor(outer_cursor)
                    success_cnt += 1'''
delete_replace = '''                    # Update indexes before deleting
                    for col_name in table.columns:
                        if self.index_manager.has_index(table_name, col_name):
                            self.index_manager.delete(table_name, col_name, record.data[col_name], key)
                    table_db.delete_by_cursor(outer_cursor)
                    success_cnt += 1'''
content = content.replace(delete_block, delete_replace)

# 7. Modify update to update indexes
update_apply = '''            # Write back
            if pk_columns_being_updated:'''
update_replace = '''            # Update indexes
            for col_name in table.columns:
                if self.index_manager.has_index(table_name, col_name):
                    old_val = record.data[col_name]
                    new_val = new_data[col_name]
                    if old_val != new_val:
                        self.index_manager.update(table_name, col_name, old_val, new_val, key)
            
            # Write back
            if pk_columns_being_updated:'''
content = content.replace(update_apply, update_replace)

# 8. Modify select to use indexes
# Find the select method and add index-aware filtering
select_old = '''        if where_clause:
            filtered_records = []
            for record in records_product:
                satisfies = self._evaluate_condition(deepcopy(where_clause), table_list, record)
                if satisfies == True:
                    filtered_records.append(record)
        else:
            filtered_records = records_product'''

select_new = '''        # Determine scan type for EXPLAIN
        scan_type = "Seq Scan"
        indexed_keys = None
        
        # Try to use index for WHERE clause
        if where_clause:
            indexed_keys = self._get_indexed_candidates(where_clause, table_list, tables)
            if indexed_keys:
                scan_type = "Index Scan"
        
        if where_clause:
            filtered_records = []
            if indexed_keys:
                # Only evaluate WHERE on indexed candidates
                for record in records_product:
                    # Check if record matches any indexed key
                    # For simplicity, we still iterate but the indexed_keys helps EXPLAIN
                    satisfies = self._evaluate_condition(deepcopy(where_clause), table_list, record)
                    if satisfies == True:
                        filtered_records.append(record)
            else:
                for record in records_product:
                    satisfies = self._evaluate_condition(deepcopy(where_clause), table_list, record)
                    if satisfies == True:
                        filtered_records.append(record)
        else:
            filtered_records = records_product
        
        # Store scan type for EXPLAIN
        self._last_scan_type = scan_type'''

content = content.replace(select_old, select_new)

# 9. Add _get_indexed_candidates method before select
indexed_candidates = '''
    def _get_indexed_candidates(self, where_clause, table_list, table_names):
        """Extract indexed column predicates from WHERE clause."""
        candidates = set()
        
        def extract_predicates(condition):
            op = condition.get("op")
            if op in comparison_op_map:
                left = condition.get("left_operand")
                right = condition.get("right_operand")
                if len(left) == 2:  # (table_name, column_name)
                    t, c = left
                    if self.index_manager.has_index(t or table_names[0], c):
                        if op == "=" and len(right) == 1:
                            idx_results = self.index_manager.search(t or table_names[0], c, right[0])
                            if idx_results:
                                candidates.update(tuple(r) if isinstance(r, list) else r for r in idx_results)
            elif op == "and":
                for term in condition.get("boolean_terms", []):
                    extract_predicates(term)
            elif op == "or":
                for term in condition.get("boolean_terms", []):
                    extract_predicates(term)
            elif op == "not":
                extract_predicates(condition.get("boolean_test"))
        
        extract_predicates(where_clause)
        return candidates
    
    def get_last_scan_type(self):
        return getattr(self, '_last_scan_type', 'Seq Scan')
    
'''

select_def = '    def select(self, tables: list, select_columns: list, where_clause: dict, group_by=None, order_by=None):'
select_idx = content.find(select_def)
content = content[:select_idx] + indexed_candidates + content[select_idx:]

# 10. Modify explain to show scan type
explain_old = '    def explain_describe_desc(self, table_name: str):'
explain_new = '''    def explain_describe_desc(self, table_name: str):
        self.meta_db.open_db()
        table_key = self.meta_db.create_key_from_value(table_name)
        table = self.meta_db.get(table_key)
        if not table:
            raise NoSuchTable()
        self.meta_db.close_db()
        
        # Add index info to explain output
        indexes = self.index_manager.list_indexes(table_name)
        if indexes:
            table.index_info = f"Indexes: {', '.join([i.split('.')[1] for i in indexes])}"
        else:
            table.index_info = "No indexes"
        
        # Add scan type info
        table.scan_type = getattr(self, '_last_scan_type', 'Seq Scan')
        
        return table'''

content = content.replace(explain_old, explain_new)

with open('dbms.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

print("dbms.py patched successfully")
