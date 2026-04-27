import sys, json
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json, to_html
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: step4_build.py <input_path>")
        sys.exit(1)
        
    input_path = sys.argv[1]
    out_dir = Path('graphify-out')
    
    extraction = json.loads((out_dir / '.graphify_extract.json').read_text(encoding='utf-8'))
    detection  = json.loads((out_dir / '.graphify_detect.json').read_text(encoding='utf-8'))

    G = build_from_json(extraction)

    if G.number_of_nodes() == 0:
        print('ERROR: Graph is empty - extraction produced no nodes.')
        sys.exit(1)

    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: f'Community {cid}' for cid in communities}
    questions = suggest_questions(G, communities, labels)

    report = generate(G, communities, cohesion, labels, gods, surprises, detection, {}, input_path, suggested_questions=questions)
    (out_dir / 'GRAPH_REPORT.md').write_text(report, encoding='utf-8')
    to_json(G, communities, str(out_dir / 'graph.json'))
    to_html(G, communities, str(out_dir / 'graph.html'))

    analysis = {
        'communities': {str(k): v for k, v in communities.items()},
        'cohesion': {str(k): v for k, v in cohesion.items()},
        'gods': gods,
        'surprises': surprises,
        'questions': questions,
    }
    (out_dir / '.graphify_analysis.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities")

if __name__ == "__main__":
    main()
