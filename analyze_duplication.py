import os
import hashlib
import json
from collections import defaultdict
import glob

def get_file_hash(filepath):
    """Compute SHA256 hash of a file."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()
    except Exception as e:
        return None

def find_exact_duplicates(root_dirs, ignore_patterns):
    hashes = defaultdict(list)
    for root_dir in root_dirs:
        for dirpath, _, filenames in os.walk(root_dir):
            # Skip skipped directories
            if any(ignore in dirpath for ignore in ignore_patterns):
                continue
            
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                # Skip hidden files and ignored extensions
                if filename.startswith('.') or filename.endswith('.pyc') or filename.endswith('.lock') or 'node_modules' in filepath or '__pycache__' in filepath:
                    continue
                
                file_hash = get_file_hash(filepath)
                if file_hash:
                    hashes[file_hash].append(filepath)
    
    # Filter for multiples
    duplicates = {h: paths for h, paths in hashes.items() if len(paths) > 1}
    return duplicates

def get_lines_clean(filepath):
    """Read file and return list of stripped lines, skipping comments/empty."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        cleaned = []
        for i, line in enumerate(lines):
            s_line = line.strip()
            if not s_line:
                continue
            # Simple comment check (python/js)
            if s_line.startswith('#') or s_line.startswith('//'):
                continue
            cleaned.append((s_line, i + 1, line)) # Content, original line number, raw content
        return cleaned
    except:
        return []

def find_inline_duplicates(root_dirs, min_lines=6):
    """Find duplicated blocks of code across files."""
    # This is a naive implementation of clone detection
    # We will hash blocks of `min_lines` size
    
    block_map = defaultdict(list)
    files_to_scan = []
    
    extensions = ['.py', '.tsx', '.ts', '.js', '.css', '.html']
    ignore_patterns = ['node_modules', '__pycache__', '.git', '.next', 'dist', 'build']

    for root_dir in root_dirs:
        for dirpath, _, filenames in os.walk(root_dir):
            if any(ignore in dirpath for ignore in ignore_patterns):
                continue
            for filename in filenames:
                if any(filename.endswith(ext) for ext in extensions):
                    files_to_scan.append(os.path.join(dirpath, filename))

    print(f"Scanning {len(files_to_scan)} files for inline duplicates...")
    
    for filepath in files_to_scan:
        cleaned_lines = get_lines_clean(filepath)
        if len(cleaned_lines) < min_lines:
            continue
            
        # Sliding window
        for i in range(len(cleaned_lines) - min_lines + 1):
            window = cleaned_lines[i : i + min_lines]
            # Use the stripped content for the key
            block_content = ''.join([item[0] for item in window])
            block_hash = hashlib.md5(block_content.encode('utf-8')).hexdigest()
            
            start_line = window[0][1]
            end_line = window[-1][1]
            
            block_map[block_hash].append({
                'file': filepath,
                'start': start_line,
                'end': end_line,
                'content': ''.join([item[2] for item in window]) # Store raw content for display
            })

    # Filter distinct duplicates (occurring in more than one place)
    duplicates = []
    for h, occurrences in block_map.items():
        if len(occurrences) > 1:
            # We want to group them if they are adjacent (extending the block), but for now return raw blocks
            # Filter out overlapping blocks in same file roughly? 
            # Actually, standard clone detection is complex. Let's just dump the top offenders.
            duplicates.append(occurrences)
            
    # Sort by number of occurrences * length (impact)
    duplicates.sort(key=lambda x: len(x), reverse=True)
    return duplicates

if __name__ == "__main__":
    search_roots = ['agents', 'dashboard-frontend']
    print(f"Searching in: {search_roots}")
    
    # Add .venv and other distinct junk folders to ignore
    ignore_list = ['node_modules', '__pycache__', '.git', '.venv', 'dist', 'build', 'env', 'venv']
    
    exact_dupes = find_exact_duplicates([os.path.join('/Users/farzad/polyagent', r) for r in search_roots], ignore_list)
    
    # Inline dupes with 10 lines min to reduce noise
    inline_dupes = find_inline_duplicates([os.path.join('/Users/farzad/polyagent', r) for r in search_roots], min_lines=10)
    
    # Filter out any results that might still have slipped through (double check)
    filtered_inline = []
    for group in inline_dupes:
        clean_group = [x for x in group if not any(bad in x['file'] for bad in ignore_list)]
        if len(clean_group) > 1:
            filtered_inline.append(clean_group)
            
    filtered_inline.sort(key=lambda x: len(x), reverse=True)

    report = {
        'exact_duplicates': exact_dupes,
        'inline_duplicates_count': len(filtered_inline),
        'top_inline_duplicates': filtered_inline[:50] 
    }
    
    with open('duplication_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    print("Report written to duplication_report.json")
