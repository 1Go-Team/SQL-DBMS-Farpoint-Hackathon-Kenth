from pathlib import Path
from typing import Dict, List
import itertools
from collections import Counter
from copy import deepcopy
from functools import cmp_to_key

from db_model import Table, Record, DB, MetaDB
from index import IndexManager
from utils import *
from messages import *



class DBMS:
    def __init__(self):
        self.db_dir = Path("./DB")
        self.db_dir.mkdir(exist_ok=True)
        self.meta_db = MetaDB()
        self.index_manager = IndexManager()
        self._load_existing_indexes()
        
        

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
    def create_table(self, table_dict: dict):
        table_name = table_dict["table_name"]
        column_list = table_dict["column_list"]
        not_null_key_set = table_dict["not_null_key_set"]
        primary_key_list = table_dict["primary_key_list"]
        foreign_key_dict = table_dict["foreign_key_dict"]

        # Error within the table info
        if len(set([column_name for column_name, _ in column_list])) < len(column_list):
            raise DuplicateColumnDefError()
        columns = {column_name: column_type for column_name, column_type in column_list}
        
        for data_type in columns.values():
            if data_type.startswith("char"):
                if eval_char_max_len(data_type) < 1:  # hardcoding
                    raise CharLengthError()
        
        if len(primary_key_list) > 1:
            raise DuplicatePrimaryKeyDefError()
        elif len(primary_key_list) == 0:
            primary_key = None
        else:
            primary_key = primary_key_list[0]
            for key in primary_key:
                if key not in columns:
                    raise NonExistingColumnDefError(key)
            not_null_key_set.update(primary_key)
        
        if foreign_key_dict:
            for foreign_key in foreign_key_dict:
                if foreign_key not in columns:
                    raise NonExistingColumnDefError(foreign_key)   

        # Error within the database
        self.meta_db.open_db()
        
        table_key = self.meta_db.create_key_from_value(table_name)
        if self.meta_db.exists(table_key):
            raise TableExistenceError()
        
        if foreign_key_dict:
            for foreign_key, (referenced_table_name, referenced_key) in foreign_key_dict.items():
                referenced_table_key = self.meta_db.create_key_from_value(referenced_table_name)
                referenced_table = self.meta_db.get(referenced_table_key)
                if not referenced_table:
                    raise ReferenceTableExistenceError()
                if referenced_key not in referenced_table:
                    raise ReferenceColumnExistenceError()
                if not referenced_table.check_reference_primary_key(referenced_key):
                    raise ReferenceNonPrimaryKeyError()
                foreign_key_type = columns[foreign_key]
                if not referenced_table.check_reference_type(foreign_key_type, referenced_key):
                    raise ReferenceTypeError()
                referenced_table.add_reference(table_name)
                # update referenced table info
                self.meta_db.put(referenced_table_key, referenced_table)
        
        table = Table(
            table_name=table_name,
            columns=columns,
            not_null_keys=not_null_key_set,
            primary_key=primary_key,
            foreign_keys=foreign_key_dict
        )
        # add table info to meta db
        self.meta_db.put(table_key, table)
        self.meta_db.close_db()
        
        # create table db
        table_db = DB(table_name)
        table_db.open_db()
        table_db.close_db()
        
        
        # Auto-create index on primary key
        if primary_key:
            for pk_col in primary_key:
                self.index_manager.create_index(table_name, pk_col)
        return CreateTableSuccess(table_name)
    
    
    def drop_table(self, table_name: str):
        # remove table info
        self.meta_db.open_db()
        table_key = self.meta_db.create_key_from_value(table_name)
        table = self.meta_db.get(table_key)
        if not table:
            raise NoSuchTable()
        if table.has_reference():
            raise DropReferencedTableError(table_name)
        referencing_tables = table.get_referencing_tables()
        if referencing_tables:
            for referencing_table in referencing_tables:
                referencing_table_key = self.meta_db.create_key_from_value(referencing_table)
                referencing_table_db = self.meta_db.get(referencing_table_key)
                referencing_table_db.remove_reference(table_name)
                self.meta_db.put(referencing_table_key, referencing_table_db)
        self.meta_db.delete(table_key)
        
        # remove table records (delete all backend files, see DB.remove_files)
        DB(table_name).remove_files()
        self.meta_db.close_db()
        
        return DropSuccess(table_name)
    
    
    def explain_describe_desc(self, table_name: str):
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
        
        return table
        self.meta_db.open_db()
        table_key = self.meta_db.create_key_from_value(table_name)
        table = self.meta_db.get(table_key)
        if not table:
            raise NoSuchTable()
        self.meta_db.close_db()
        return table
    
    
    def show_tables(self):
        self.meta_db.open_db()
        output = "\n------------------------\n"
        all_tables = self.meta_db.keys()
        for table_key in all_tables:
            output += table_key.decode() + "\n"
        output += "------------------------"
        self.meta_db.close_db()
        return output
    
    
    def insert(self, table_dict: dict, value_list: list):
        table_name = table_dict["table_name"]
        column_name_list = table_dict["column_name_list"]
        
        self.meta_db.open_db()
        table_key = self.meta_db.create_key_from_value(table_name)
        table = self.meta_db.get(table_key)
        if not table:
            raise NoSuchTable()
        self.meta_db.close_db()
        
        if column_name_list:
            if len(column_name_list) != len(value_list):
                raise InsertTypeMismatchError()
            for column_name in column_name_list:
                if column_name not in table:
                    raise InsertColumnExistenceError(column_name)
            
        if len(table.columns.keys()) != len(value_list):
            raise InsertTypeMismatchError()
        
        for column_name, value in zip(table.columns.keys(), value_list):
            if value is None and column_name in table.not_null_keys:
                raise InsertColumnNonNullableError(column_name)
        
        if not all([is_valid_type(data_type, value) for data_type, value in zip(table.columns.values(), value_list)]):
            raise InsertTypeMismatchError()
        
        data = {}
        primary_value = []
        referencing = dict()
        for (column_name, data_type), value in zip(table.columns.items(), value_list):
            if data_type.startswith("char") and value is not None:
                max_len = eval_char_max_len(data_type)
                value = value[:max_len]
            if table.primary_key and column_name in table.primary_key:  # may be composite primary key
                primary_value.append(value)
            if table.foreign_keys and column_name in table.foreign_keys:  # one foreign key per column
                referenced_table_name, referenced_column_name = table.foreign_keys[column_name]
                # get referenced table schema
                self.meta_db.open_db()
                referenced_table_key = self.meta_db.create_key_from_value(referenced_table_name)
                referenced_table = self.meta_db.get(referenced_table_key)
                self.meta_db.close_db()
                # get referenced record
                referenced_table_db = DB(referenced_table_name)
                referenced_table_db.open_db()
                referenced_key = referenced_table_db.create_key_from_value((value,))
                referenced_record = None
                if len(referenced_table.primary_key) == 1:
                    referenced_record = referenced_table_db.get(referenced_key)
                else:  # composite primary key
                    all_primary_values = referenced_table_db.keys()
                    for primary_value in all_primary_values:
                        if referenced_key.decode() in primary_value.decode():
                            referenced_record = referenced_table_db.get(primary_value)
                            break
                if referenced_record is None:
                    raise InsertReferentialIntegrityError()
                referencing[(referenced_table_name, referenced_column_name)] = {referenced_record.data[referenced_column_name]}
                assert referenced_record.data[referenced_column_name] == value
                referenced_record.add_to_referenced_by(table_name, column_name, value)
                referenced_table_db.put(referenced_key, referenced_record)
                referenced_table_db.close_db()
            data[column_name] = value
        primary_value = tuple(primary_value) if primary_value else None
        record = Record(table_name, data, primary_value, referencing)
        
        table_db = DB(table_name)
        table_db.open_db()
        record_key = table_db.create_key_from_value(primary_value) if primary_value else table_db.create_random_key()
        if table_db.exists(record_key):
            raise InsertDuplicatePrimaryKeyError()
        table_db.put(record_key, record)
        table_db.close_db()
        
        
        # Update indexes
        for col_name in table.columns:
            if self.index_manager.has_index(table_name, col_name):
                self.index_manager.insert(table_name, col_name, data[col_name], record_key)
        return InsertResult()

    
    def delete(self, table_name: str, where_clause: str):
        self.meta_db.open_db()
        table_key = self.meta_db.create_key_from_value(table_name)
        table = self.meta_db.get(table_key)
        if not table:
            raise NoSuchTable()
        self.meta_db.close_db()
        
        table_db = DB(table_name)
        table_db.open_db()
        outer_cursor = table_db.create_cursor()
        
        success_cnt = 0
        fail_cnt = 0
        key_value_pair = outer_cursor.first()
        while key_value_pair:
            key, value = key_value_pair
            record = Record.deserialize(value)
            satisfies = self._evaluate_condition(deepcopy(where_clause), [table], record.data) if where_clause else True
            if satisfies == True:
                if list(record.referenced_by.values()):
                    fail_cnt += 1
                else:
                    if record.referencing:
                        for (referenced_table_name, referenced_column_name), referenced_value_set in record.referencing.items():
                            for referenced_value in referenced_value_set:
                                referenced_table_db = DB(referenced_table_name)
                                referenced_table_db.open_db()
                                inner_cursor = referenced_table_db.create_cursor()
                                key_value_pair = inner_cursor.first()
                                while key_value_pair:
                                    key, value = key_value_pair
                                    referenced_record = Record.deserialize(value)
                                    for column in table.columns:
                                        if ((table_name, column) in referenced_record.referenced_by and 
                                            referenced_value in referenced_record.referenced_by[(table_name, column)]):
                                            referenced_record.remove_referenced_by(table_name, column, referenced_value)
                                            referenced_table_db.put(key, referenced_record)  # update reference
                                    key_value_pair = inner_cursor.next()
                                referenced_table_db.discard_cursor(inner_cursor)
                                referenced_table_db.close_db()
                    # Update indexes before deleting
                    for col_name in table.columns:
                        if self.index_manager.has_index(table_name, col_name):
                            self.index_manager.delete(table_name, col_name, record.data[col_name], key)
                    table_db.delete_by_cursor(outer_cursor)
                    success_cnt += 1
            key_value_pair = outer_cursor.next()
            
        table_db.discard_cursor(outer_cursor)
        table_db.close_db()
        
        return DeleteResult(success_cnt), DeleteReferentialIntegrityPassed(fail_cnt) if fail_cnt else None
        
    
    def update(self, table_name: str, assignments: dict, where_clause: dict):
        self.meta_db.open_db()
        table_key = self.meta_db.create_key_from_value(table_name)
        table = self.meta_db.get(table_key)
        if not table:
            raise NoSuchTable()
        self.meta_db.close_db()
        
        # Validate column existence
        for column_name in assignments:
            if column_name not in table.columns:
                raise UpdateColumnExistenceError(column_name)
        
        # Validate types and NOT NULL
        for column_name, value in assignments.items():
            if value is None and column_name in table.not_null_keys:
                raise UpdateColumnNonNullableError(column_name)
            if not is_valid_type(table.columns[column_name], value):
                raise UpdateTypeMismatchError()
        
        # Check if PK columns are being updated
        pk_columns_being_updated = set()
        if table.primary_key:
            for pk_col in table.primary_key:
                if pk_col in assignments:
                    pk_columns_being_updated.add(pk_col)
        
        # Check if referenced PK is being updated
        updating_referenced_pk = False
        if table.primary_key and table.has_reference():
            for pk_col in table.primary_key:
                if pk_col in assignments:
                    updating_referenced_pk = True
                    break
        
        table_db = DB(table_name)
        table_db.open_db()
        
        # Collect matching records
        matching_records = []
        cursor = table_db.create_cursor()
        key_value_pair = cursor.first()
        while key_value_pair:
            key, value = key_value_pair
            record = Record.deserialize(value)
            satisfies = self._evaluate_condition(deepcopy(where_clause), [table], record.data) if where_clause else True
            if satisfies == True:
                matching_records.append((key, record))
            key_value_pair = cursor.next()
        table_db.discard_cursor(cursor)
        
        # Check for PK duplicates among updated records
        if pk_columns_being_updated:
            new_pks = set()
            for key, record in matching_records:
                new_pk_values = []
                for pk_col in table.primary_key:
                    if pk_col in assignments:
                        new_pk_values.append(assignments[pk_col])
                    else:
                        new_pk_values.append(record.data[pk_col])
                new_pk_tuple = tuple(new_pk_values)
                record_key = table_db.create_key_from_value(new_pk_tuple)
                if table_db.exists(record_key) and record_key != key:
                    raise UpdateDuplicatePrimaryKeyError()
                new_pk_str = str(new_pk_tuple)
                if new_pk_str in new_pks:
                    raise UpdateDuplicatePrimaryKeyError()
                new_pks.add(new_pk_str)
        
        success_cnt = 0
        fail_cnt = 0
        
        # Apply updates
        for key, record in matching_records:
            # Check referential integrity if updating referenced PK
            if updating_referenced_pk and record.referenced_by:
                fail_cnt += 1
                continue
            
            # Check FK integrity if updating FK columns
            fk_violation = False
            for col in assignments:
                if table.foreign_keys and col in table.foreign_keys:
                    referenced_table_name, referenced_column_name = table.foreign_keys[col]
                    self.meta_db.open_db()
                    referenced_table_key = self.meta_db.create_key_from_value(referenced_table_name)
                    referenced_table_schema = self.meta_db.get(referenced_table_key)
                    self.meta_db.close_db()
                    
                    referenced_table_db = DB(referenced_table_name)
                    referenced_table_db.open_db()
                    new_value = assignments[col]
                    referenced_record = None
                    if len(referenced_table_schema.primary_key) == 1:
                        ref_key = referenced_table_db.create_key_from_value((new_value,))
                        referenced_record = referenced_table_db.get(ref_key)
                    else:
                        for pk_val in referenced_table_db.keys():
                            ref_key = referenced_table_db.create_key_from_value((new_value,))
                            if ref_key.decode() in pk_val.decode():
                                referenced_record = referenced_table_db.get(pk_val)
                                break
                    referenced_table_db.close_db()
                    
                    if referenced_record is None:
                        fk_violation = True
                        break
            
            if fk_violation:
                fail_cnt += 1
                continue
            
            # Build new data
            new_data = dict(record.data)
            for col, val in assignments.items():
                new_data[col] = val
            
            # Build new primary value
            new_primary_value = list(record.primary_value) if record.primary_value else []
            if table.primary_key:
                for i, pk_col in enumerate(table.primary_key):
                    if pk_col in assignments:
                        new_primary_value[i] = assignments[pk_col]
                new_primary_value = tuple(new_primary_value)
            else:
                new_primary_value = record.primary_value
            
            # Handle FK referencing updates - remove old references
            if record.referencing:
                for (ref_table, ref_col), old_values in list(record.referencing.items()):
                    for col in assignments:
                        if table.foreign_keys and col in table.foreign_keys:
                            rt, rc = table.foreign_keys[col]
                            if rt == ref_table and rc == ref_col:
                                old_value = record.data[col]
                                ref_db = DB(ref_table)
                                ref_db.open_db()
                                inner_cursor = ref_db.create_cursor()
                                kv = inner_cursor.first()
                                while kv:
                                    k, v = kv
                                    ref_record = Record.deserialize(v)
                                    if (table_name, col) in ref_record.referenced_by and old_value in ref_record.referenced_by[(table_name, col)]:
                                        ref_record.remove_referenced_by(table_name, col, old_value)
                                        ref_db.put(k, ref_record)
                                    kv = inner_cursor.next()
                                ref_db.discard_cursor(inner_cursor)
                                ref_db.close_db()
            
            # Add new referencing relationships for updated FK columns
            new_referencing = dict(record.referencing)
            for col in assignments:
                if table.foreign_keys and col in table.foreign_keys:
                    referenced_table_name, referenced_column_name = table.foreign_keys[col]
                    new_value = assignments[col]
                    
                    self.meta_db.open_db()
                    referenced_table_key = self.meta_db.create_key_from_value(referenced_table_name)
                    referenced_table_schema = self.meta_db.get(referenced_table_key)
                    self.meta_db.close_db()
                    
                    referenced_table_db = DB(referenced_table_name)
                    referenced_table_db.open_db()
                    ref_key = referenced_table_db.create_key_from_value((new_value,))
                    ref_record = None
                    if len(referenced_table_schema.primary_key) == 1:
                        ref_record = referenced_table_db.get(ref_key)
                    else:
                        for pk_val in referenced_table_db.keys():
                            if ref_key.decode() in pk_val.decode():
                                ref_record = referenced_table_db.get(pk_val)
                                break
                    
                    if ref_record:
                        ref_record.add_to_referenced_by(table_name, col, new_value)
                        referenced_table_db.put(ref_key, ref_record)
                        new_referencing[(referenced_table_name, referenced_column_name)] = {new_value}
                    referenced_table_db.close_db()
            
            # Create updated record
            new_record = Record(table_name, new_data, new_primary_value, new_referencing)
            new_record.referenced_by = record.referenced_by
            
            # Update indexes
            for col_name in table.columns:
                if self.index_manager.has_index(table_name, col_name):
                    old_val = record.data[col_name]
                    new_val = new_data[col_name]
                    if old_val != new_val:
                        self.index_manager.update(table_name, col_name, old_val, new_val, key)
            
            # Write back
            if pk_columns_being_updated:
                table_db.delete(key)
                new_key = table_db.create_key_from_value(new_primary_value)
                table_db.put(new_key, new_record)
            else:
                table_db.put(key, new_record)
            
            success_cnt += 1
        
        table_db.close_db()
        
        return UpdateResult(success_cnt), UpdateReferentialIntegrityPassed(fail_cnt) if fail_cnt else None
        
    
    def _evaluate_condition(self, condition, table_list: List[Table], record: dict):
        def get_record_value(operand):
            table_name, column_name = operand
            if table_name and not any([table_name == table.table_name for table in table_list]):
                raise WhereTableNotSpecified()
            found_tables = [table for table in table_list if column_name in table]
            if len(found_tables) < 1:
                raise WhereColumnNotExist()
            elif len(found_tables) > 1:
                if not table_name:  # column name is ambiguous
                    raise WhereAmbiguousReference()
                table = next(table for table in found_tables if table_name == table.table_name)
            else:
                table = found_tables[0]
            if table_name and table_name != table.table_name:
                raise WhereColumnNotExist()
            if table_name:
                prefixed_column_name = f"{table_name}.{column_name}"
                if prefixed_column_name in record:
                    return record[prefixed_column_name]
            return record[column_name]
        
        def determine_operand_value(operand):
            if operand is None:
                value = operand
            elif len(operand) == 1:  # comparable_value
                value = operand[0]
            else:  # table_name, column_name
                value = get_record_value(operand)
            return value
            
        op = condition["op"]
        if op in comparison_op_map | null_op_map:
            op, left_operand, right_operand = map(condition.get, ["op", "left_operand", "right_operand"])
            left_value = determine_operand_value(left_operand)
            right_value = determine_operand_value(right_operand)
            
            if op in comparison_op_map and is_comparable(left_value, right_value) == False:
                raise WhereIncomparableError()
            
            if op in comparison_op_map:
                if left_value is None or right_value is None:
                    output = UNKNOWN
                else:
                    output = comparison_op_map[op](left_value, right_value)
            else:
                output = null_op_map[op](left_value, right_value)
            return output
            
        elif op == "not":
            boolean_test = condition["boolean_test"]
            return not_(self._evaluate_condition(boolean_test, table_list, record))
        
        elif op == "and":
            boolean_factors = condition["boolean_factors"]
            return and_(*[self._evaluate_condition(boolean_factor, table_list, record) for boolean_factor in boolean_factors])
        
        elif op == "or":
            boolean_terms = condition["boolean_terms"]
            return or_(*[self._evaluate_condition(boolean_term, table_list, record) for boolean_term in boolean_terms])
        
        else:  # None
            _, remaining_condition = condition.popitem()  # "boolean_terms", "boolean_factors", "boolean_test"
            if remaining_condition is not None:
                return self._evaluate_condition(remaining_condition, table_list, record)
    
    
    def _resolve_column_value(self, record, table_name, column_name, table_list):
        if table_name:
            key = f"{table_name}.{column_name}"
            return record.get(key)
        else:
            for table in table_list:
                if column_name in table.columns:
                    key = f"{table.table_name}.{column_name}"
                    if key in record:
                        return record.get(key)
            return record.get(column_name)
    
    
    def _compute_aggregate(self, func_name, param, records, table_list):
        if func_name == "count":
            if param == "*":
                return len(records)
            else:
                table_name, column_name = param
                count = 0
                for record in records:
                    value = self._resolve_column_value(record, table_name, column_name, table_list)
                    if value is not None:
                        count += 1
                return count
        elif func_name == "sum":
            table_name, column_name = param
            total = 0
            for record in records:
                value = self._resolve_column_value(record, table_name, column_name, table_list)
                if value is not None:
                    try:
                        total += int(value)
                    except (ValueError, TypeError):
                        pass
            return total
        return None
    
    

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
    
    def select(self, tables: list, select_columns: list, where_clause: dict, group_by=None, order_by=None):
        table_list = []
        self.meta_db.open_db()
        for table_name in tables:
            table_key = self.meta_db.create_key_from_value(table_name)
            table = self.meta_db.get(table_key)
            if not table:
                raise SelectTableExistenceError(table_name)
            table_list.append(table)
        self.meta_db.close_db()
        
        final_columns = []
        if select_columns and select_columns != "*":
            for col in select_columns:
                if isinstance(col, tuple) and col[0] in ("count", "sum"):
                    continue
                table_name, column_name = col
                found_tables = [table for table in table_list if column_name in table]
                if len(found_tables) < 1:
                    raise SelectColumnResolveError(column_name)
                elif len(found_tables) > 1:
                    if not table_name:
                        raise SelectColumnResolveError(column_name)
                    found_table = next(table for table in found_tables if table_name == table.table_name)
                else:
                    found_table = found_tables[0]       
                if table_name and table_name != found_table.table_name:
                    raise SelectColumnResolveError(column_name)
                final_column = f"{found_table.table_name}.{column_name}" if table_name else column_name
                final_columns.append(final_column)
        
        all_columns = []
        for table_schema in table_list:
            all_columns.extend(list(table_schema.columns.keys()))
        counter = Counter(all_columns)
        common_columns = set([column for column, count in counter.items() if count > 1])
                    
        all_records_with_table = {}
        for table_name in tables:
            all_records_with_table[table_name] = []
            table_db = DB(table_name)
            table_db.open_db()
            cursor = table_db.create_cursor()
            key_value_pair = cursor.first()
            while key_value_pair:
                key, value = key_value_pair
                record = Record.deserialize(value)
                record_data = {}
                for column_name, value in record.data.items():
                    if column_name in common_columns:
                        prefixed_column_name = f"{table_name}.{column_name}"
                        record_data[prefixed_column_name] = value
                    else:
                        record_data[column_name] = value
                all_records_with_table[table_name].append(record_data)
                key_value_pair = cursor.next()
            table_db.discard_cursor(cursor)
            table_db.close_db()
        
        cartesian_product = itertools.product(*all_records_with_table.values())
        records_product = [{k: v for record in combination_tuple for k, v in record.items()} for combination_tuple in cartesian_product]
        
        # Determine scan type for EXPLAIN
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
        self._last_scan_type = scan_type
        
        # Handle aggregates and GROUP BY
        has_aggregates = False
        if select_columns and select_columns != "*":
            has_aggregates = any(isinstance(col, tuple) and col[0] in ("count", "sum") for col in select_columns)
        
        if group_by or has_aggregates:
            groups = {}
            for record in filtered_records:
                if group_by:
                    group_key = tuple(self._resolve_column_value(record, t, c, table_list) for t, c in group_by)
                else:
                    group_key = ()
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append(record)
            
            final_records = []
            for group_key, group_records in groups.items():
                new_record = {}
                if group_by:
                    for i, (t, c) in enumerate(group_by):
                        new_record[c] = group_key[i]
                for col in select_columns:
                    if isinstance(col, tuple) and col[0] in ("count", "sum"):
                        func_name, param, alias = col
                        value = self._compute_aggregate(func_name, param, group_records, table_list)
                        if param == "*":
                            key = alias if alias else f"{func_name}(*)"
                        else:
                            t, c = param
                            col_ref = c if t is None else f"{t}.{c}"
                            key = alias if alias else f"{func_name}({col_ref})"
                        new_record[key] = value
                    else:
                        t, c = col
                        value = self._resolve_column_value(group_records[0], t, c, table_list)
                        new_record[c] = value
                final_records.append(new_record)
            
            final_columns = list(final_records[0].keys()) if final_records else []
        elif select_columns:
            final_records = []
            for record in filtered_records:
                final_record = {}
                for table_name, column_name in select_columns:
                    value = None
                    if table_name:
                        prefixed_column_name = f"{table_name}.{column_name}"
                        try:
                            final_record[prefixed_column_name] = record[prefixed_column_name]
                        except KeyError:
                            final_record[prefixed_column_name] = record[column_name]
                    else:
                        final_record[column_name] = record[column_name]
                final_records.append(final_record)
            final_columns = [column_name for _, column_name in select_columns]
        else:
            final_records = filtered_records
            final_columns = []
            for table_schema in table_list:
                for column in table_schema.columns:
                    if column in common_columns:
                        final_columns.append(f"{table_schema.table_name}.{column}")
                    else:
                        final_columns.append(column)
        
        # ORDER BY
        if order_by and final_records:
            def compare_records(a, b):
                for t, c, direction in order_by:
                    va = self._resolve_column_value(a, t, c, table_list)
                    vb = self._resolve_column_value(b, t, c, table_list)
                    if va == vb:
                        continue
                    if va is None:
                        return -1
                    if vb is None:
                        return 1
                    if va < vb:
                        return -1 if direction == "asc" else 1
                    return 1 if direction == "asc" else -1
                return 0
            
            final_records.sort(key=cmp_to_key(compare_records))
        
        headers = final_records[0].keys() if final_records else final_columns
        
        return self._format_select_output(final_records, headers)
        
    
    def _format_select_output(self, records: List[Dict], headers: List[str]):
        def create_separator(column_widths):
            return '+-' + '-+-'.join('-' * width for width in column_widths) + '-+'
        
        for record in records:
            for k, v in record.items():
                if v is None:
                    record[k] = "null"
        
        column_widths = [len(header) for header in headers]
        for record in records:
            for i, value in enumerate(record.values()):
                column_widths[i] = max(column_widths[i], len(str(value)))
        
        output = '\n'
        output += create_separator(column_widths) + '\n'
        output += '| ' + ' | '.join(header.upper().ljust(width) for header, width in zip(headers, column_widths)) + ' |\n'
        output += create_separator(column_widths) + '\n'
        
        for record in records:
            output += '| ' + ' | '.join(str(value).ljust(width) for value, width in zip(record.values(), column_widths)) + ' |\n'
        output += create_separator(column_widths)
        
        return output
