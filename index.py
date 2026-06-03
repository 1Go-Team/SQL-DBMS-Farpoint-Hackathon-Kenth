import bisect
from typing import List, Tuple, Any, Dict

class ColumnIndex:
    """Lightweight sorted-list index for fast equality and range lookups."""
    
    def __init__(self, table_name: str, column_name: str):
        self.table_name = table_name
        self.column_name = column_name
        self.entries: List[Tuple[Any, Any]] = []  # sorted by (value, record_key)
    
    def insert(self, value, record_key):
        bisect.insort(self.entries, (value, record_key))
    
    def delete(self, value, record_key):
        idx = bisect.bisect_left(self.entries, (value, record_key))
        if idx < len(self.entries) and self.entries[idx] == (value, record_key):
            self.entries.pop(idx)
    
    def update(self, old_value, new_value, record_key):
        self.delete(old_value, record_key)
        self.insert(new_value, record_key)
    
    def search(self, value) -> List[Any]:
        """Exact match search."""
        idx = bisect.bisect_left(self.entries, (value, None))
        results = []
        while idx < len(self.entries) and self.entries[idx][0] == value:
            results.append(self.entries[idx][1])
            idx += 1
        return results
    
    def range_search(self, op: str, value) -> List[Any]:
        """Range search for <, <=, >, >=."""
        results = []
        for entry_value, record_key in self.entries:
            if op == '<' and entry_value < value:
                results.append(record_key)
            elif op == '<=' and entry_value <= value:
                results.append(record_key)
            elif op == '>' and entry_value > value:
                results.append(record_key)
            elif op == '>=' and entry_value >= value:
                results.append(record_key)
        return results
    
    def clear(self):
        self.entries = []


class IndexManager:
    """Manages all indexes for the database."""
    
    def __init__(self):
        self.indexes: Dict[str, ColumnIndex] = {}  # key: "table_name.column_name"
    
    def _key(self, table_name: str, column_name: str) -> str:
        return f"{table_name}.{column_name}"
    
    def create_index(self, table_name: str, column_name: str):
        key = self._key(table_name, column_name)
        if key not in self.indexes:
            self.indexes[key] = ColumnIndex(table_name, column_name)
    
    def has_index(self, table_name: str, column_name: str) -> bool:
        return self._key(table_name, column_name) in self.indexes
    
    def drop_index(self, table_name: str, column_name: str):
        key = self._key(table_name, column_name)
        if key in self.indexes:
            del self.indexes[key]
    
    def insert(self, table_name: str, column_name: str, value, record_key):
        key = self._key(table_name, column_name)
        if key in self.indexes:
            self.indexes[key].insert(value, record_key)
    
    def delete(self, table_name: str, column_name: str, value, record_key):
        key = self._key(table_name, column_name)
        if key in self.indexes:
            self.indexes[key].delete(value, record_key)
    
    def update(self, table_name: str, column_name: str, old_value, new_value, record_key):
        key = self._key(table_name, column_name)
        if key in self.indexes:
            self.indexes[key].update(old_value, new_value, record_key)
    
    def search(self, table_name: str, column_name: str, value) -> List[Any]:
        key = self._key(table_name, column_name)
        if key in self.indexes:
            return self.indexes[key].search(value)
        return []
    
    def range_search(self, table_name: str, column_name: str, op: str, value) -> List[Any]:
        key = self._key(table_name, column_name)
        if key in self.indexes:
            return self.indexes[key].range_search(op, value)
        return []
    
    def get_index(self, table_name: str, column_name: str) -> ColumnIndex:
        return self.indexes.get(self._key(table_name, column_name))
    
    def list_indexes(self, table_name: str = None) -> List[str]:
        if table_name:
            return [k for k in self.indexes if k.startswith(f"{table_name}.")]
        return list(self.indexes.keys())
