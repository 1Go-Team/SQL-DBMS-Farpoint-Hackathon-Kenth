import re

with open('dbms.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add import
content = content.replace(
    'from index import IndexManager',
    'from index import IndexManager\nfrom transaction import TransactionManager'
)

# 2. Modify __init__ to add transaction manager and replay WAL
content = content.replace(
    '        self.index_manager = IndexManager()',
    '        self.index_manager = IndexManager()\n        self.transaction_manager = TransactionManager()\n        self.transaction_manager.replay_wal(self)'
)

# 3. Add transaction checks to create_table
old = '''        return CreateTableSuccess(table_name)'''
new = '''        if self.transaction_manager.in_transaction:\n            self.transaction_manager.add_operation("create_table", table_dict=table_dict)\n            return CreateTableSuccess(table_name)\n        return CreateTableSuccess(table_name)'''
content = content.replace(old, new)

# 4. Add transaction checks to drop_table
old = '''        return DropSuccess(table_name)'''
new = '''        if self.transaction_manager.in_transaction:\n            self.transaction_manager.add_operation("drop_table", table_name=table_name)\n            return DropSuccess(table_name)\n        return DropSuccess(table_name)'''
content = content.replace(old, new)

# 5. Add transaction checks to insert
old = '''        return InsertResult()'''
new = '''        if self.transaction_manager.in_transaction:\n            self.transaction_manager.add_operation("insert", table_name=table_dict["table_name"], column_name_list=table_dict.get("column_name_list"), values=value_list)\n            return InsertResult()\n        return InsertResult()'''
content = content.replace(old, new)

# 6. Add transaction checks to delete
old = '''        return DeleteResult(success_cnt), DeleteReferentialIntegrityPassed(fail_cnt) if fail_cnt else None'''
new = '''        if self.transaction_manager.in_transaction:\n            self.transaction_manager.add_operation("delete", table_name=table_name, where=where_clause)\n            return DeleteResult(0), None\n        return DeleteResult(success_cnt), DeleteReferentialIntegrityPassed(fail_cnt) if fail_cnt else None'''
content = content.replace(old, new)

# 7. Add transaction checks to update
old = '''        return UpdateResult(success_cnt), UpdateReferentialIntegrityPassed(fail_cnt) if fail_cnt else None'''
new = '''        if self.transaction_manager.in_transaction:\n            self.transaction_manager.add_operation("update", table_name=table_name, assignments=assignments, where=where_clause)\n            return UpdateResult(0), None\n        return UpdateResult(success_cnt), UpdateReferentialIntegrityPassed(fail_cnt) if fail_cnt else None'''
content = content.replace(old, new)

# 8. Add transaction checks to create_index
old = '''        return f"Index created on {table_name}({column_name})"'''
new = '''        if self.transaction_manager.in_transaction:\n            self.transaction_manager.add_operation("create_index", table_name=table_name, column_name=column_name)\n            return f"Index created on {table_name}({column_name})"\n        return f"Index created on {table_name}({column_name})"'''
content = content.replace(old, new)

# 9. Add transaction methods before _evaluate_condition
tx_methods = '''    def begin_transaction(self):
        self.transaction_manager.begin()
        return "Transaction started"
    
    def commit_transaction(self):
        ops = self.transaction_manager.commit()
        if ops is None:
            return "No active transaction"
        results = []
        for op in ops:
            try:
                if op["type"] == "insert":
                    result = self.insert(
                        {"table_name": op["table_name"], "column_name_list": op.get("column_name_list")},
                        op["values"]
                    )
                elif op["type"] == "delete":
                    result, extra = self.delete(op["table_name"], op.get("where"))
                elif op["type"] == "update":
                    result, extra = self.update(op["table_name"], op["assignments"], op.get("where"))
                elif op["type"] == "create_table":
                    result = self.create_table(op["table_dict"])
                elif op["type"] == "drop_table":
                    result = self.drop_table(op["table_name"])
                elif op["type"] == "create_index":
                    result = self.create_index(op["table_name"], op["column_name"])
                else:
                    result = "Unknown operation"
                results.append(str(result))
            except Exception as e:
                results.append(str(e))
        return "\\n".join(results) if results else "Transaction committed"
    
    def rollback_transaction(self):
        self.transaction_manager.rollback()
        return "Transaction rolled back"
    
'''

eval_pos = content.find('    def _evaluate_condition(self, condition, table_list: List[Table], record: dict):')
content = content[:eval_pos] + tx_methods + content[eval_pos:]

with open('dbms.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

print("dbms.py patched for transactions")
