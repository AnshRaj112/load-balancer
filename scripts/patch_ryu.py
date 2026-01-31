#!/usr/bin/env python3
"""
Patch script to fix ryu's ALREADY_HANDLED import issue.
eventlet removed ALREADY_HANDLED in newer versions, but ryu still tries to import it.
"""

import sys
import re

RYU_WSGI_PATH = '/usr/local/lib/python3.10/site-packages/ryu/app/wsgi.py'

# Original import line that fails in newer eventlet
OLD_IMPORT = 'from eventlet.wsgi import ALREADY_HANDLED'

# Fixed import with fallback - properly indented
NEW_IMPORT = '''try:
    from eventlet.wsgi import ALREADY_HANDLED
except ImportError:
    # Fallback for newer eventlet versions that removed ALREADY_HANDLED
    ALREADY_HANDLED = object()'''

try:
    with open(RYU_WSGI_PATH, 'r') as f:
        content = f.read()
    
    if OLD_IMPORT in content:
        # Find the line and replace it, maintaining proper structure
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            if line.strip() == OLD_IMPORT:
                # Get the indentation of the original line
                indent = len(line) - len(line.lstrip())
                indent_str = ' ' * indent
                # Add the try/except block with proper indentation
                new_lines.append(f'{indent_str}try:')
                new_lines.append(f'{indent_str}    from eventlet.wsgi import ALREADY_HANDLED')
                new_lines.append(f'{indent_str}except ImportError:')
                new_lines.append(f'{indent_str}    # Fallback for newer eventlet versions')
                new_lines.append(f'{indent_str}    ALREADY_HANDLED = object()')
            else:
                new_lines.append(line)
        
        content = '\n'.join(new_lines)
        with open(RYU_WSGI_PATH, 'w') as f:
            f.write(content)
        print(f"SUCCESS: Patched {RYU_WSGI_PATH}")
    elif 'try:' in content and 'ALREADY_HANDLED' in content:
        print(f"SKIPPED: {RYU_WSGI_PATH} already patched")
    else:
        print(f"WARNING: Could not find import to patch in {RYU_WSGI_PATH}")
        sys.exit(1)
except Exception as e:
    print(f"ERROR: Failed to patch {RYU_WSGI_PATH}: {e}")
    sys.exit(1)
