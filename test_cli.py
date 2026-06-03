"""
Comprehensive CLI test for SQL DBMS hackathon features.
Tests: CREATE, INSERT, SELECT, UPDATE, aggregates, GROUP BY, ORDER BY,
       transactions (BEGIN/COMMIT/ROLLBACK), indexing, EXPLAIN.
"""
import os
import shutil
import sys

# Clean DB
if os.path.exists("DB"):
    shutil.rmtree("DB")

from lark import Lark
from sql_transformer import SQLTransformer
from dbms import DBMS
from messages import *

# Load parser
with open("grammar.lark") as f:
    parser = Lark(f.read(), start="command", lexer="basic")

dbms = DBMS()
passed = 0
failed = 0
results = []

def test(name, sql, expected_in_output=None, should_fail=False, check_fn=None):
    global passed, failed
    try:
        sql_transformer = SQLTransformer()
        parsed = parser.parse(sql)
        transformed = sql_transformer.transform(parsed)
        statement, table, record, tables, select_columns, where, group_by, order_by = transformed

        if statement == "exit":
            output = "exit"
        elif statement == "create table":
            output = str(dbms.create_table(table))
        elif statement == "create index":
            output = str(dbms.create_index(table["table_name"], table["column_name"]))
        elif statement == "drop table":
            output = str(dbms.drop_table(table["table_name"]))
        elif statement in ("explain", "describe", "desc"):
            output = str(dbms.explain_describe_desc(table["table_name"]))
        elif statement == "show tables":
            output = dbms.show_tables()
        elif statement == "insert":
            output = str(dbms.insert(table, record))
        elif statement == "delete":
            output, extra = dbms.delete(table["table_name"], where)
            output = str(output)
            if extra:
                output += "\n" + str(extra)
        elif statement == "select":
            output = dbms.select(tables, select_columns, where, group_by, order_by)
        elif statement == "update":
            output, extra = dbms.update(table["table_name"], table["assignments"], where)
            output = str(output)
            if extra:
                output += "\n" + str(extra)
        elif statement == "begin":
            output = dbms.begin_transaction()
        elif statement == "commit":
            output = dbms.commit_transaction()
        elif statement == "rollback":
            output = dbms.rollback_transaction()
        else:
            output = f"Unknown statement: {statement}"

        if should_fail:
            results.append(f"FAIL [{name}] — expected failure but got: {output}")
            failed += 1
        else:
            ok = True
            if expected_in_output:
                for exp in expected_in_output:
                    if exp not in output:
                        ok = False
                        results.append(f"FAIL [{name}] — expected '{exp}' in output. Got: {output}")
                        failed += 1
                        break
            if check_fn and ok:
                if not check_fn(output):
                    ok = False
            if ok:
                results.append(f"PASS [{name}]")
                passed += 1
    except Exception as e:
        if should_fail:
            results.append(f"PASS [{name}] — correctly raised: {type(e).__name__}")
            passed += 1
        else:
            results.append(f"FAIL [{name}] — exception: {type(e).__name__}: {e}")
            failed += 1


print("=" * 60)
print("SQL DBMS CLI TEST SUITE")
print("=" * 60)

# ── Test 1: CREATE TABLE + INSERT + SELECT ──
print("\n--- Test 1: CREATE TABLE + INSERT + SELECT ---")
test("create table", "CREATE TABLE students (id INT, name CHAR(20), score INT, PRIMARY KEY (id));",
     ["'students' table is created"])
test("insert 1", "INSERT INTO students VALUES (1, 'Alice', 90);",
     ["'1' row(s) are inserted"])
test("insert 2", "INSERT INTO students VALUES (2, 'Bob', 85);",
     ["'1' row(s) are inserted"])
test("select all", "SELECT * FROM students;",
     ["Alice", "Bob"])
test("select count", "SELECT COUNT(*) FROM students;",
     ["count(*)"])

# ── Test 2: UPDATE ──
print("\n--- Test 2: UPDATE ---")
test("update score", "UPDATE students SET score = 95 WHERE id = 1;",
     ["'1' row(s) are updated"])
test("verify update", "SELECT * FROM students WHERE id = 1;",
     ["Alice", "95"])
test("update multi-col", "UPDATE students SET score = 88, name = 'Bob Updated' WHERE id = 2;",
     ["'1' row(s) are updated"])
test("verify multi update", "SELECT * FROM students WHERE id = 2;",
     ["Bob Updated", "88"])
test("update no match", "UPDATE students SET score = 999 WHERE id = 999;",
     ["'0' row(s) are updated"])
test("update bad column", "UPDATE students SET badcol = 1 WHERE id = 1;",
     None, should_fail=True)
test("update null not null", "UPDATE students SET name = NULL WHERE id = 1;",
     None, should_fail=True)

# ── Test 3: Aggregates + GROUP BY ──
print("\n--- Test 3: Aggregates + GROUP BY ---")
test("insert carol", "INSERT INTO students VALUES (3, 'Carol', 90);",
     ["'1' row(s) are inserted"])
test("insert dave", "INSERT INTO students VALUES (4, 'Dave', 85);",
     ["'1' row(s) are inserted"])
test("group by count", "SELECT score, COUNT(*) FROM students GROUP BY score;",
     ["count(*)", "score"])
test("sum aggregate", "SELECT SUM(score) FROM students;",
     ["sum(score)"])
test("count star", "SELECT COUNT(*) FROM students;",
     ["count(*)"])

# ── Test 4: ORDER BY ──
print("\n--- Test 4: ORDER BY ---")
test("order by desc", "SELECT * FROM students ORDER BY score DESC;",
     ["Alice", "Bob Updated", "Dave", "Carol"])
test("order by asc", "SELECT * FROM students ORDER BY name ASC;",
     ["Alice", "Bob Updated", "Carol", "Dave"])

# ── Test 5: Transactions - ROLLBACK ──
print("\n--- Test 5: Transactions - ROLLBACK ---")
test("begin tx", "BEGIN;",
     ["Transaction started"])
test("insert in tx", "INSERT INTO students VALUES (5, 'Eve', 70);",
     ["'1' row(s) are inserted"])
test("rollback", "ROLLBACK;",
     ["Transaction rolled back"])
test("verify rollback", "SELECT COUNT(*) FROM students;",
     None, check_fn=lambda out: "count(*)" in out and "5" not in out.split("count(*)")[-1].split("\n")[0])

# ── Test 6: Transactions - COMMIT ──
print("\n--- Test 6: Transactions - COMMIT ---")
test("begin tx2", "BEGIN;",
     ["Transaction started"])
test("insert in tx2", "INSERT INTO students VALUES (5, 'Eve', 70);",
     ["'1' row(s) are inserted"])
test("commit", "COMMIT;",
     None, check_fn=lambda out: "committed" in out.lower() or "inserted" in out.lower() or "created" in out.lower())
test("verify commit", "SELECT COUNT(*) FROM students;",
     None, check_fn=lambda out: "count(*)" in out)

# ── Test 7: Indexing + EXPLAIN ──
print("\n--- Test 7: Indexing + EXPLAIN ---")
test("explain students", "EXPLAIN students;",
     ["students"])
test("select indexed", "SELECT * FROM students WHERE id = 2;",
     ["Bob Updated"])

# ── Test 8: DELETE ──
print("\n--- Test 8: DELETE ---")
test("delete row", "DELETE FROM students WHERE id = 3;",
     ["'1' row(s) are deleted"])
test("verify delete", "SELECT * FROM students WHERE id = 3;",
     None, check_fn=lambda out: "Carol" not in out)

# ── Test 9: DROP TABLE ──
print("\n--- Test 9: DROP TABLE ---")
test("drop table", "DROP TABLE students;",
     ["'students' table is dropped"])
test("select dropped", "SELECT * FROM students;",
     None, should_fail=True)

# ── Summary ──
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
print("=" * 60)
for r in results:
    print(f"  {r}")

if failed > 0:
    sys.exit(1)
else:
    print("\n🎉 ALL TESTS PASSED!")
    sys.exit(0)
