from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from dbms import DBMS
from sql_transformer import SQLTransformer
from lark import Lark

app = FastAPI(title="SQL DBMS API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

with open('grammar.lark') as file:
    sql_parser = Lark(file.read(), start="command", lexer="basic")

dbms = DBMS()


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    scan_type: Optional[str] = None
    headers: Optional[List[str]] = None
    rows: Optional[List[List[str]]] = None
    is_table: bool = False


def parse_tabulate(text: str):
    """Parse tabulate grid output into headers and rows."""
    lines = text.strip().split('\n')
    headers = None
    rows = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('+'):
            continue
        if line.startswith('|'):
            cells = [cell.strip() for cell in line[1:-1].split('|')]
            if headers is None:
                headers = cells
            else:
                rows.append(cells)
    return headers, rows


@app.post("/query", response_model=QueryResponse)
def execute_query(req: QueryRequest):
    try:
        sql_transformer = SQLTransformer()
        parsed = sql_parser.parse(req.query)
        transformed = sql_transformer.transform(parsed)
        statement, table, record, tables, select_columns, where, group_by, order_by = transformed

        result = None
        is_table = False
        headers = None
        rows = None

        if statement == "create table":
            result = str(dbms.create_table(table))
        elif statement == "create index":
            result = str(dbms.create_index(table["table_name"], table["column_name"]))
        elif statement == "drop table":
            result = str(dbms.drop_table(table["table_name"]))
        elif statement in ("explain", "describe", "desc"):
            result = str(dbms.explain_describe_desc(table["table_name"]))
        elif statement == "show tables":
            result = dbms.show_tables()
        elif statement == "insert":
            result = str(dbms.insert(table, record))
        elif statement == "delete":
            r, extra = dbms.delete(table["table_name"], where)
            result = str(r)
            if extra:
                result += "\n" + str(extra)
        elif statement == "select":
            raw = dbms.select(tables, select_columns, where, group_by, order_by)
            headers, rows = parse_tabulate(raw)
            is_table = True
            result = raw
        elif statement == "update":
            r, extra = dbms.update(table["table_name"], table["assignments"], where)
            result = str(r)
            if extra:
                result += "\n" + str(extra)
        elif statement == "begin":
            result = dbms.begin_transaction()
        elif statement == "commit":
            result = dbms.commit_transaction()
        elif statement == "rollback":
            result = dbms.rollback_transaction()
        else:
            result = "Unknown statement"

        scan_type = dbms.get_last_scan_type() if hasattr(dbms, 'get_last_scan_type') else None
        return QueryResponse(
            success=True,
            result=result,
            scan_type=scan_type,
            headers=headers,
            rows=rows,
            is_table=is_table
        )
    except Exception as e:
        return QueryResponse(success=False, error=str(e))


@app.get("/tables")
def list_tables():
    raw = dbms.show_tables().strip()
    lines = [l for l in raw.split("\n") if l and not l.startswith("-")]
    return {"tables": lines}


@app.get("/tables/{table_name}")
def describe_table(table_name: str):
    try:
        table = dbms.explain_describe_desc(table_name)
        return {
            "name": table.table_name,
            "columns": {k: v for k, v in table.columns.items()},
            "primary_key": table.primary_key,
            "foreign_keys": table.foreign_keys,
            "not_null": list(table.not_null_keys)
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/transaction/begin")
def tx_begin():
    return {"result": dbms.begin_transaction()}


@app.post("/transaction/commit")
def tx_commit():
    return {"result": dbms.commit_transaction()}


@app.post("/transaction/rollback")
def tx_rollback():
    return {"result": dbms.rollback_transaction()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
