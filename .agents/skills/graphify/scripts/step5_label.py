import sys, json
from graphify.build import build_from_json
from graphify.cluster import score_all
from graphify.analyze import suggest_questions
from graphify.report import generate
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: step5_label.py <input_path>")
        sys.exit(1)
        
    input_path = sys.argv[1]
    out_dir = Path('graphify-out')
    
    extraction = json.loads((out_dir / '.graphify_extract.json').read_text(encoding='utf-8'))
    detection  = json.loads((out_dir / '.graphify_detect.json').read_text(encoding='utf-8'))
    analysis   = json.loads((out_dir / '.graphify_analysis.json').read_text(encoding='utf-8'))

    # Load the new labels that the agent generated
    new_labels_file = out_dir / '.graphify_new_labels.json'
    if not new_labels_file.exists():
        print("Error: .graphify_new_labels.json not found. Generate labels first.")
        sys.exit(1)
        
    labels = json.loads(new_labels_file.read_text(encoding='utf-8'))
    # convert keys to int for python
    labels = {int(k): v for k, v in labels.items()}

    G = build_from_json(extraction)
    communities = {int(k): v for k, v in analysis['communities'].items()}
    cohesion = {int(k): v for k, v in analysis['cohesion'].items()}

    questions = suggest_questions(G, communities, labels)
    report = generate(G, communities, cohesion, labels, analysis['gods'], analysis['surprises'], detection, {}, input_path, suggested_questions=questions)
    
    (out_dir / 'GRAPH_REPORT.md').write_text(report, encoding='utf-8')
    (out_dir / '.graphify_labels.json').write_text(json.dumps({str(k): v for k, v in labels.items()}), encoding='utf-8')
    
    print("Report updated with community labels")

if __name__ == "__main__":
    main()
