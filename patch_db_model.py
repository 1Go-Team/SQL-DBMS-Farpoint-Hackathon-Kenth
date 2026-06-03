import re

with open('db_model.py', 'r') as f:
    content = f.read()

# Find and replace the __str__ method tail
old = '''            info += "{:<25}{:<15}{:<10}{:<10}\\n".format(column, column_type, null_str, key_str)
        info += "-----------------------------------------------------------------"
        return info'''

new = '''            info += "{:<25}{:<15}{:<10}{:<10}\\n".format(column, column_type, null_str, key_str)
        info += "-----------------------------------------------------------------\\n"
        if hasattr(self, 'scan_type'):
            info += f"Scan Type: {self.scan_type}\\n"
        if hasattr(self, 'index_info'):
            info += f"{self.index_info}\\n"
        info += "-----------------------------------------------------------------"
        return info'''

if old in content:
    content = content.replace(old, new)
    with open('db_model.py', 'w') as f:
        f.write(content)
    print('db_model.py updated successfully')
else:
    print('Pattern not found - checking content around line 50')
    lines = content.split('\n')
    for i, line in enumerate(lines[48:56], start=49):
        print(f'{i}: {repr(line)}')
