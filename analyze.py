import os
import re
import ast

def analyze_directory(root_dir):
    report = []
    
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if not file.endswith('.py'):
                continue
            
            filepath = os.path.join(subdir, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            
            lines = content.split('\n')
            
            # Analyze using AST and Regex
            n_plus_one_loops = []
            unpaginated_all = []
            ilike_scans = []
            ineffective_joins = []
            
            for i, line in enumerate(lines):
                line_idx = i + 1
                # Check for .ilike(
                if '.ilike(' in line and 'search_term' in line:
                    ilike_scans.append((line_idx, line.strip()))
                
                # Check for ineffective joins
                if '.join(' in line and 'contains_eager' not in content and 'joinedload' not in content:
                    ineffective_joins.append((line_idx, line.strip()))
                
                # Check for .all() without limit/offset
                if '.all()' in line:
                    # Let's see if limit or offset is in the same statement
                    # Simplified heuristic
                    if '.limit(' not in line and '.offset(' not in line:
                        # Check context
                        unpaginated_all.append((line_idx, line.strip()))
            
            # Check for N+1 loops (db.query inside for loop or accessing relationships)
            for node in ast.walk(tree):
                if isinstance(node, ast.For):
                    # Check if db.query is called inside
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            if isinstance(child.func, ast.Attribute) and child.func.attr == 'query':
                                n_plus_one_loops.append((node.lineno, "db.query inside loop"))
            
            # If we found any issues, add to report
            if n_plus_one_loops or unpaginated_all or ilike_scans or ineffective_joins:
                rel_path = os.path.relpath(filepath, root_dir)
                report.append(f"### File: `{rel_path}`\n")
                
                if n_plus_one_loops:
                    report.append("**N+1 Query inside loops:**")
                    for ln, msg in n_plus_one_loops:
                        report.append(f"- Line {ln}: {msg}")
                    report.append("")
                
                if ilike_scans:
                    report.append("**Potential Full Table Scan (.ilike without index):**")
                    for ln, msg in ilike_scans:
                        report.append(f"- Line {ln}: `{msg}`")
                    report.append("")
                
                if ineffective_joins:
                    report.append("**Ineffective Joins (missing eager loading):**")
                    for ln, msg in ineffective_joins:
                        report.append(f"- Line {ln}: `{msg}`")
                    report.append("")
                
                if unpaginated_all:
                    report.append("**Unpaginated `.all()` calls (potential memory leaks):**")
                    for ln, msg in unpaginated_all:
                        report.append(f"- Line {ln}: `{msg}`")
                    report.append("")

    return "\n".join(report)

if __name__ == "__main__":
    report_md = analyze_directory("/Ubuntu/home/keith-pc/Desktop/work/dadProject/HMS-2/backend/app")
    with open("/Ubuntu/home/keith-pc/Desktop/work/dadProject/HMS-2/query_analysis_report.md", "w") as f:
        f.write("# Database Queries Optimization Report\n\n")
        f.write(report_md)
    print("Analysis complete. Report written to query_analysis_report.md")
