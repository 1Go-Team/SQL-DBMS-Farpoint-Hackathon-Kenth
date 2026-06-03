import subprocess
import sys
import os
import shutil

# Clean DB before test
if os.path.exists("DB"):
    shutil.rmtree("DB")

# Read SQL statements
with open('test/1-3.sql', 'r') as f:
    sql_content = f.read()

# Parse statements (handle comments)
statements = []
current = []
for line in sql_content.split('\n'):
    line = line.strip()
    if not line or line.startswith('/*') or line.startswith('*/') or line.startswith('--'):
        continue
    line = line.split('--')[0].strip()
    line = line.split('/*')[0].strip()
    if line:
        current.append(line)
        if line.endswith(';'):
            stmt = ' '.join(current).strip().rstrip(';')
            if stmt:
                statements.append(stmt)
            current = []

# Read expected results from 1-3.txt
with open('test/1-3.txt', 'r') as f:
    content = f.read()

print("=" * 70)
print("RUNNING TEST SUITE (test/1-3.sql)")
print("=" * 70)

results = []
for i, stmt in enumerate(statements):
    if not stmt:
        continue
    
    try:
        result = subprocess.run(
            [sys.executable, 'run.py'],
            input=stmt + ';\nexit;\n',
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout.strip()
        
        # Check if error occurred
        has_error = 'has failed' in output.lower()
        
        # Find expected result in 1-3.txt
        expected = 'VALID'
        lines = content.split('\n')
        for j, line in enumerate(lines):
            if line.strip().startswith(stmt[:40]):
                # Look backward for annotation
                for k in range(j-1, max(0, j-10), -1):
                    if lines[k].strip().startswith('**'):
                        expected = lines[k].strip().replace('**', '').strip()
                        break
                    if lines[k].strip().startswith('! Valid'):
                        expected = 'VALID'
                        break
        
        # Determine pass/fail
        is_pass = False
        if expected == 'VALID' and not has_error:
            is_pass = True
        elif expected != 'VALID' and has_error:
            is_pass = True  # Expected error occurred
        elif expected == 'VALID' and has_error:
            is_pass = False  # Unexpected error
        else:
            is_pass = True  # No error, valid query
        
        status = "PASS" if is_pass else "FAIL"
        results.append({'status': status, 'stmt': stmt, 'output': output, 'expected': expected, 'has_error': has_error})
        
        if not is_pass:
            print(f"{status}: {stmt[:65]}...")
            print(f"  Expected: {expected}")
            print(f"  Output:   {output[-100:]}")
        else:
            print(f"{status}: {stmt[:65]}...")
            
    except Exception as e:
        print(f"ERROR: {stmt[:65]}... -> {e}")
        results.append({'status': 'ERROR', 'stmt': stmt, 'error': str(e)})

# Summary
pass_count = sum(1 for r in results if r['status'] == 'PASS')
fail_count = sum(1 for r in results if r['status'] == 'FAIL')
error_count = sum(1 for r in results if r['status'] == 'ERROR')

print("\n" + "=" * 70)
print(f"TOTAL: {len(results)} | PASSED: {pass_count} | FAILED: {fail_count} | ERRORS: {error_count}")
print("=" * 70)

if fail_count > 0:
    print("\nFailed tests:")
    for r in results:
        if r['status'] == 'FAIL':
            print(f"  - {r['stmt'][:60]}...")
            print(f"    Expected: {r['expected']}, Got error: {r['has_error']}")
