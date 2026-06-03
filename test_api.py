import requests

BASE = "http://127.0.0.1:8000"

def q(sql):
    r = requests.post(f"{BASE}/query", json={"query": sql})
    return r.json()

results = []

# 1. CREATE TABLE
results.append(("CREATE TABLE", q("CREATE TABLE test (id INT, name CHAR(20), age INT, score INT, PRIMARY KEY (id));")))

# 2. INSERT
results.append(("INSERT 1", q("INSERT INTO test VALUES (1, 'Alice', 20, 90);")))
results.append(("INSERT 2", q("INSERT INTO test VALUES (2, 'Bob', 21, 85);")))
results.append(("INSERT 3", q("INSERT INTO test VALUES (3, 'Charlie', 20, 92);")))

# 3. SELECT *
results.append(("SELECT *", q("SELECT * FROM test;")))

# 4. ORDER BY DESC
results.append(("ORDER BY DESC", q("SELECT * FROM test ORDER BY score DESC;")))

# 5. GROUP BY + COUNT
results.append(("GROUP BY COUNT", q("SELECT age, COUNT(*) FROM test GROUP BY age;")))

# 6. SUM aggregate
results.append(("SUM COUNT", q("SELECT SUM(score), COUNT(*) FROM test;")))

# 7. UPDATE
results.append(("UPDATE", q("UPDATE test SET score = 95 WHERE id = 1;")))

# 8. Verify UPDATE
results.append(("VERIFY UPDATE", q("SELECT * FROM test WHERE id = 1;")))

# 9. Transaction BEGIN + INSERT + ROLLBACK
results.append(("BEGIN", q("BEGIN;")))
results.append(("TX INSERT", q("INSERT INTO test VALUES (4, 'Diana', 22, 88);")))
results.append(("COUNT IN TX", q("SELECT COUNT(*) FROM test;")))
results.append(("ROLLBACK", q("ROLLBACK;")))
results.append(("COUNT AFTER ROLLBACK", q("SELECT COUNT(*) FROM test;")))

# 10. Transaction BEGIN + INSERT + COMMIT
results.append(("BEGIN 2", q("BEGIN;")))
results.append(("TX INSERT 2", q("INSERT INTO test VALUES (4, 'Diana', 22, 88);")))
results.append(("COMMIT", q("COMMIT;")))
results.append(("COUNT AFTER COMMIT", q("SELECT COUNT(*) FROM test;")))

# 11. CREATE INDEX
results.append(("CREATE INDEX", q("CREATE INDEX idx_score ON test(score);")))

# 12. EXPLAIN
results.append(("EXPLAIN", q("EXPLAIN test;")))

# 13. Index scan query
results.append(("INDEX SCAN", q("SELECT * FROM test WHERE score > 90;")))

# 14. DELETE
results.append(("DELETE", q("DELETE FROM test WHERE id = 4;")))

# 15. SHOW TABLES
results.append(("SHOW TABLES", q("SHOW TABLES;")))

# 16. DROP TABLE
results.append(("DROP TABLE", q("DROP TABLE test;")))
results.append(("SHOW TABLES AFTER DROP", q("SHOW TABLES;")))

# Print results
for label, data in results:
    status = "PASS" if data.get("success") else "FAIL"
    result = data.get("result") or ""
    error = data.get("error") or ""
    scan = data.get("scan_type") or ""
    print(f"{status} {label:25s} | {str(result)[:60]:60s} | {str(error)[:40]:40s} | {scan}")
