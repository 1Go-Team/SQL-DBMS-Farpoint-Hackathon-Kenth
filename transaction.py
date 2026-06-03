import json
from pathlib import Path
from typing import List, Dict, Any


class TransactionManager:
    """Manages transaction buffering and WAL durability."""
    
    def __init__(self, wal_path: str = "./DB/wal.log"):
        self.wal_path = Path(wal_path)
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        self.operations: List[Dict[str, Any]] = []
        self.in_transaction = False
    
    def begin(self):
        self.in_transaction = True
        self.operations = []
    
    def add_operation(self, op_type: str, **kwargs):
        self.operations.append({"type": op_type, **kwargs})
    
    def commit(self):
        if not self.in_transaction:
            return None
        # Write to WAL before applying
        self._append_to_wal(self.operations)
        self.in_transaction = False
        ops = self.operations
        self.operations = []
        return ops
    
    def rollback(self):
        self.in_transaction = False
        self.operations = []
        return []
    
    def _append_to_wal(self, operations):
        if not operations:
            return
        with open(self.wal_path, "a") as f:
            f.write(json.dumps({"ops": operations}) + "\n")
    
    def replay_wal(self, dbms):
        if not self.wal_path.exists():
            return
        replayed = 0
        with open(self.wal_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    for op in entry.get("ops", []):
                        if self._replay_operation(dbms, op):
                            replayed += 1
                except (json.JSONDecodeError, Exception):
                    continue
        return replayed
    
    def _replay_operation(self, dbms, op):
        op_type = op.get("type")
        try:
            if op_type == "insert":
                dbms.insert(
                    {"table_name": op["table_name"], "column_name_list": op.get("column_name_list")},
                    op["values"]
                )
            elif op_type == "delete":
                dbms.delete(op["table_name"], op.get("where"))
            elif op_type == "update":
                dbms.update(op["table_name"], op["assignments"], op.get("where"))
            elif op_type == "create_table":
                dbms.create_table(op["table_dict"])
            elif op_type == "drop_table":
                dbms.drop_table(op["table_name"])
            elif op_type == "create_index":
                dbms.create_index(op["table_name"], op["column_name"])
            return True
        except Exception:
            return False
    
    def clear_wal(self):
        if self.wal_path.exists():
            self.wal_path.unlink()
