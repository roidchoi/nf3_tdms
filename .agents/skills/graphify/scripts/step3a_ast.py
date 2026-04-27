import sys, json
from graphify.extract import collect_files, extract
from pathlib import Path

def main():
    code_files = []
    detect_path = Path('graphify-out/.graphify_detect.json')
    if not detect_path.exists():
        print("Error: .graphify_detect.json not found.")
        sys.exit(1)
        
    detect = json.loads(detect_path.read_text(encoding='utf-8'))
    
    for f in detect.get('files', {}).get('code', []):
        p = Path(f)
        code_files.extend(collect_files(p) if p.is_dir() else [p])

    out_file = Path('graphify-out/.graphify_ast.json')
    
    if code_files:
        result = extract(code_files, cache_root=Path('.'))
        out_file.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(f"AST: {len(result.get('nodes', []))} nodes, {len(result.get('edges', []))} edges")
    else:
        out_file.write_text(json.dumps({'nodes':[],'edges':[],'input_tokens':0,'output_tokens':0}), encoding='utf-8')
        print('No code files - skipping AST extraction')

if __name__ == "__main__":
    main()
