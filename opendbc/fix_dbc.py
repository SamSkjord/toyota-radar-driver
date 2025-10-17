#!/usr/bin/python3
"""
Fix overlapping signals in Toyota DBC files
This script removes duplicate signal definitions that cause parsing errors
"""

import sys
import os
import re
from pathlib import Path

def fix_dbc_file(filepath):
    """Remove overlapping signal definitions from DBC file"""
    print(f"Processing: {filepath}")
    
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return False
    
    # Backup original file
    backup_path = filepath + '.backup'
    if not os.path.exists(backup_path):
        print(f"Creating backup: {backup_path}")
        with open(filepath, 'r') as f:
            content = f.read()
        with open(backup_path, 'w') as f:
            f.write(content)
    
    # Read the file
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # Track seen signals per message
    current_message = None
    seen_signals = {}
    fixed_lines = []
    removed_count = 0
    
    for line in lines:
        # Check if this is a message definition
        msg_match = re.match(r'BO_ (\d+) (\w+):', line)
        if msg_match:
            current_message = msg_match.group(2)
            seen_signals[current_message] = set()
            fixed_lines.append(line)
            continue
        
        # Check if this is a signal definition
        sig_match = re.match(r'\s+SG_ (\w+)', line)
        if sig_match and current_message:
            signal_name = sig_match.group(1)
            
            # Check for duplicate signal in this message
            if signal_name in seen_signals[current_message]:
                print(f"  Removing duplicate signal: {signal_name} in message {current_message}")
                removed_count += 1
                continue
            else:
                seen_signals[current_message].add(signal_name)
        
        fixed_lines.append(line)
    
    if removed_count > 0:
        # Write fixed file
        with open(filepath, 'w') as f:
            f.writelines(fixed_lines)
        print(f"✓ Fixed {removed_count} overlapping signals in {filepath}")
        return True
    else:
        print(f"✓ No overlapping signals found in {filepath}")
        return True

def main():
    print("=" * 60)
    print("Toyota DBC File Fixer")
    print("Removes overlapping signal definitions")
    print("=" * 60)
    print()
    
    # Find DBC files
    opendbc_dir = Path('opendbc')
    
    if not opendbc_dir.exists():
        print("ERROR: opendbc directory not found!")
        print("Make sure you're in the toyota_radar_control_can directory")
        print("and have run: git submodule update --init")
        sys.exit(1)
    
    # Find all Toyota DBC files
    dbc_files = list(opendbc_dir.glob('toyota*.dbc'))
    
    if not dbc_files:
        print("ERROR: No Toyota DBC files found in opendbc/")
        sys.exit(1)
    
    print(f"Found {len(dbc_files)} DBC files to check:\n")
    
    success = True
    for dbc_file in dbc_files:
        if not fix_dbc_file(str(dbc_file)):
            success = False
        print()
    
    if success:
        print("=" * 60)
        print("✓ All DBC files processed successfully!")
        print("=" * 60)
        print("\nYou can now run: sudo python3 toyota_radar_rpi.py")
    else:
        print("=" * 60)
        print("✗ Some errors occurred")
        print("=" * 60)
        sys.exit(1)

if __name__ == '__main__':
    main()
