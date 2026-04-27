import sys, json
from graphify.detect import detect
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: step2_detect.py <input_path>")
        sys.exit(1)
        
    input_path = Path(sys.argv[1])
    result = detect(input_path)
    
    out_dir = Path('graphify-out')
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / '.graphify_detect.json'
    
    out_file.write_text(json.dumps(result, indent=2), encoding='utf-8')

if __name__ == "__main__":
    main()
