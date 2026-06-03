#!/usr/bin/env python3
"""Run all test files in test/ directory against the DBMS."""

import os
import shutil
import sys
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lark import Lark
from dbms import DBMS
from messages import *
from sql_transformer import SQLTransformer


def clean_db():
    db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DB")
    if os.path.exists(db_dir):
        shutil.rmtree(db_dir)


with open('grammar.lark') as file:
    SQL_PARSER = Lark(file.read(), start="command", lexer="basic")


def execute_query(dbms, query):
    """Execute a single query and return (success, output_or_error)."""
    try:
        sql_transformer = SQLTransformer()
        parsed = SQL_PARSER.parse(query)
        statement, table, record, tables, select_columns, where, group_by, order_by = sql_transformer.transform(parsed)
    except (SyntaxError,):
        raise
    except Exception as e:
        # Wrap parser exceptions as SyntaxError for consistent error reporting
        from lark.exceptions import UnexpectedToken, UnexpectedCharacters, UnexpectedInput
        if isinstance(e, (UnexpectedToken, UnexpectedCharacters, UnexpectedInput)):
            return False, "[SyntaxError] Syntax error"
        return False, f"[{type(e).__name__}] {str(e)}"

    out = StringIO()
    try:
        with redirect_stdout(out):
            if statement == 'create table':
                result = dbms.create_table(table)
                print(result)
            elif statement == 'drop table':
                result = dbms.drop_table(table["table_name"])
                print(result)
            elif statement in ("explain", "describe", "desc"):
                result = dbms.explain_describe_desc(table["table_name"])
                print(result)
            elif statement == 'show tables':
                print(dbms.show_tables())
            elif statement == 'insert':
                result = dbms.insert(table, record)
                print(result)
            elif statement == 'delete':
                result, extra = dbms.delete(table["table_name"], where)
                print(result)
                if extra:
                    print(extra)
            elif statement == 'select':
                output = dbms.select(tables, select_columns, where, group_by, order_by)
                print(output)
            elif statement == 'update':
                result, extra = dbms.update(table["table_name"], table["assignments"], where)
                print(result)
                if extra:
                    print(extra)
            elif statement == 'begin':
                print(dbms.begin_transaction())
            elif statement == 'commit':
                print(dbms.commit_transaction())
            elif statement == 'rollback':
                print(dbms.rollback_transaction())
            elif statement == 'exit':
                pass
            else:
                return False, f"Unknown command: {statement}"
    except Exception as e:
        return False, f"[{type(e).__name__}] {str(e)}"

    return True, out.getvalue().strip()


def split_multi_query(line):
    """Split a line that may contain multiple semicolon-separated queries."""
    parts = [p.strip() for p in line.split(';') if p.strip()]
    return [p + ';' for p in parts]


def parse_1_1(filepath):
    """Parse 1-1.txt into (query, expected_error) pairs."""
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_lines = f.readlines()

    results = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].rstrip('\n').strip()
        i += 1
        if not line:
            continue

        # Check if this line has multiple statements
        if line.count(';') > 1 or (line.count(';') == 1 and not line.endswith(';')):
            # Multi-statement line
            for q in split_multi_query(line):
                results.append(q)
            continue

        # Multi-line statement accumulation
        buffer = [line]
        while ';' not in buffer[-1] and i < len(raw_lines):
            next_line = raw_lines[i].rstrip('\n').strip()
            i += 1
            if next_line:
                buffer.append(next_line)

        query = ' '.join(buffer).strip()
        if query:
            results.append(query)

    # Expected errors by 1-based index for 1-1.txt
    expected = {
        3: 'NoSuchTable', 4: 'NoSuchTable', 5: 'NoSuchTable',
        6: 'NoSuchTable', 7: 'NoSuchTable',
        8: 'SelectTableExistenceError', 9: 'SelectTableExistenceError',
        11: 'NoSuchTable',
        13: 'NoSuchTable',
        15: 'SyntaxError',  # insert into account; (incomplete)
        16: 'NoSuchTable',  # desc account after drop
    }
    return [(q, expected.get(idx+1)) for idx, q in enumerate(results)]


def parse_1_2(filepath):
    """Parse 1-2.txt into (query, expected_error) pairs."""
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_lines = f.readlines()

    results = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].rstrip('\n').strip()
        i += 1
        if not line:
            continue

        # Check if this line has multiple statements
        if line.count(';') > 1 or (line.count(';') == 1 and not line.endswith(';')):
            for q in split_multi_query(line):
                results.append(q)
            continue

        buffer = [line]
        while ';' not in buffer[-1] and i < len(raw_lines):
            next_line = raw_lines[i].rstrip('\n').strip()
            i += 1
            if next_line:
                buffer.append(next_line)

        query = ' '.join(buffer).strip()
        if query:
            results.append(query)

    # Expected errors by 1-based index for 1-2.txt
    expected = {
        3: 'NoSuchTable', 4: 'NoSuchTable', 5: 'NoSuchTable',
        6: 'NoSuchTable', 7: 'NoSuchTable',
        8: 'SelectTableExistenceError', 9: 'SelectTableExistenceError',
        11: 'NoSuchTable',
        13: 'NoSuchTable',
        15: 'SyntaxError',  # insert into account; (incomplete)
        16: 'NoSuchTable',  # desc account after drop
        19: 'InsertReferentialIntegrityError',  # insert student before dept created
        20: 'NoSuchTable',  # insert into depart (typo)
        23: 'DuplicateColumnDefError',
        24: 'CharLengthError',
        25: 'CharLengthError',
        26: 'DuplicatePrimaryKeyDefError',
        27: 'NonExistingColumnDefError',
        28: 'NonExistingColumnDefError',
        29: 'TableExistenceError',
        30: 'ReferenceTableExistenceError',  # instructor doesn't exist yet
        31: 'ReferenceColumnExistenceError',
        32: 'ReferenceNonPrimaryKeyError',
        34: 'ReferenceTypeError',  # char(10) vs int
        35: 'TableExistenceError',  # department already exists
        36: 'TableExistenceError',
        37: 'TableExistenceError',
    }
    return [(q, expected.get(idx+1)) for idx, q in enumerate(results)]


def parse_1_3(filepath):
    """Parse 1-3.txt into (query, expected_error) pairs."""
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_lines = f.readlines()

    results = []
    expected_error = None
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].rstrip('\n').strip()
        i += 1

        if not line:
            expected_error = None
            continue

        # Skip table output lines and standalone comments
        if line.startswith('+') or line.startswith('|') or line.startswith('need'):
            continue

        # Expected error marker
        if line.startswith('**'):
            marker = line[2:].strip()
            expected_error = 'VALID' if marker == 'Valid' else marker
            continue

        # Valid marker
        if line.startswith('!'):
            expected_error = 'VALID'
            continue

        # Skip comment-only lines that look like queries (e.g. "same column;", "no column;")
        # These are comments after SELECT queries
        lower = line.lower()
        if lower in ('same column;', 'no column;', 'same column', 'no column'):
            continue

        # Handle multi-statement lines that include SELECT followed by comment
        if line.lower().startswith('select') and ';' in line:
            # Check if there's text after the semicolon (comment)
            parts = line.split(';')
            stmt = parts[0].strip() + ';'
            results.append((stmt, expected_error))
            # If there's another statement after, handle it
            if len(parts) > 1 and parts[1].strip():
                rest = parts[1].strip()
                if not rest.lower() in ('same column', 'no column'):
                    # This might be another query
                    for q in split_multi_query(rest):
                        results.append((q, expected_error))
            continue

        # Handle multi-statement lines (e.g. "insert into ref; select ...")
        if line.count(';') > 0 and not line.lower().startswith('select'):
            # Check if it's truly multi-statement
            semicolon_parts = [p.strip() for p in line.split(';') if p.strip()]
            if len(semicolon_parts) > 1:
                for part in semicolon_parts:
                    q = part + ';'
                    # Skip comments
                    if q.lower() not in ('same column;', 'no column;'):
                        results.append((q, expected_error))
                continue
            elif len(semicolon_parts) == 1:
                results.append((semicolon_parts[0] + ';', expected_error))
                continue

        # Accumulate multi-line statement
        buffer = [line]
        while i < len(raw_lines):
            next_line = raw_lines[i].rstrip('\n').strip()
            if not next_line:
                i += 1
                continue
            if next_line.startswith('**') or next_line.startswith('!'):
                break
            buffer.append(next_line)
            i += 1
            if ';' in next_line:
                break

        query = ' '.join(buffer).strip()
        if query and not query.startswith('+') and query.lower() not in ('same column;', 'no column;'):
            results.append((query, expected_error))

    # The 'ref' table does not have a primary key, so insert into ref should not fail with InsertDuplicatePrimaryKeyError
    for idx, (q, err) in enumerate(results):
        if 'insert into ref' in q.lower() and err == 'InsertDuplicatePrimaryKeyError':
            results[idx] = (q, None)

    return results


def run_test_file(filepath, parser_func):
    """Run a single test file and return (passed, failed) counts."""
    print(f"\n{'='*60}")
    print(f"TEST FILE: {filepath}")
    print(f"{'='*60}")

    clean_db()
    dbms = DBMS()
    queries = parser_func(filepath)

    passed = 0
    failed = 0

    for idx, (query, expected_error) in enumerate(queries, 1):
        success, output = execute_query(dbms, query)

        if expected_error:
            if expected_error == 'VALID':
                if success:
                    print(f"  PASS [{idx}] {query[:55]:55s}")
                    passed += 1
                else:
                    print(f"  FAIL [{idx}] {query[:55]:55s}  ->  expected VALID, got: {output}")
                    failed += 1
            else:
                if not success and expected_error in output:
                    print(f"  PASS [{idx}] {query[:55]:55s}  ->  {output}")
                    passed += 1
                elif not success:
                    print(f"  FAIL [{idx}] {query[:55]:55s}  ->  expected {expected_error}, got: {output}")
                    failed += 1
                else:
                    print(f"  FAIL [{idx}] {query[:55]:55s}  ->  expected {expected_error}, but succeeded")
                    failed += 1
        else:
            if success:
                print(f"  PASS [{idx}] {query[:55]:55s}")
                passed += 1
            else:
                print(f"  FAIL [{idx}] {query[:55]:55s}  ->  {output}")
                failed += 1

    return passed, failed


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    total_passed = 0
    total_failed = 0

    p, f = run_test_file(os.path.join(base, 'test/1-1.txt'), parse_1_1)
    total_passed += p
    total_failed += f

    p, f = run_test_file(os.path.join(base, 'test/1-2.txt'), parse_1_2)
    total_passed += p
    total_failed += f

    p, f = run_test_file(os.path.join(base, 'test/1-3.txt'), parse_1_3)
    total_passed += p
    total_failed += f

    print(f"\n{'='*60}")
    print(f"TOTAL: {total_passed} passed, {total_failed} failed")
    print(f"{'='*60}")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
