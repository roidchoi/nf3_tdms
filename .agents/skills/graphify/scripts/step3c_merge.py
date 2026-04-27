import sys, json, glob
from graphify.cache import save_semantic_cache
from pathlib import Path

def main():
    out_dir = Path('graphify-out')
    
    # 1. Merge chunks
    new_nodes, new_edges, new_hyperedges = [], [], []
    chunk_files = list(out_dir.glob('.graphify_chunk_*.json'))
    
    for cf in chunk_files:
        try:
            data = json.loads(cf.read_text(encoding='utf-8'))
            new_nodes.extend(data.get('nodes', []))
            new_edges.extend(data.get('edges', []))
            new_hyperedges.extend(data.get('hyperedges', []))
        except Exception as e:
            print(f"Warning: Failed to parse {cf}: {e}")
            
    # Save cache
    saved = save_semantic_cache(new_nodes, new_edges, new_hyperedges)
    print(f"Cached {saved} new semantic files from {len(chunk_files)} chunks")
    
    # 2. Merge with cached semantics
    cached_file = out_dir / '.graphify_cached.json'
    cached = json.loads(cached_file.read_text(encoding='utf-8')) if cached_file.exists() else {'nodes':[],'edges':[],'hyperedges':[]}
    
    all_sem_nodes = cached.get('nodes', []) + new_nodes
    all_sem_edges = cached.get('edges', []) + new_edges
    all_sem_hyperedges = cached.get('hyperedges', []) + new_hyperedges
    
    # deduplicate nodes
    seen_sem = set()
    deduped_sem_nodes = []
    for n in all_sem_nodes:
        if n['id'] not in seen_sem:
            seen_sem.add(n['id'])
            deduped_sem_nodes.append(n)
            
    sem_merged = {
        'nodes': deduped_sem_nodes,
        'edges': all_sem_edges,
        'hyperedges': all_sem_hyperedges
    }
    (out_dir / '.graphify_semantic.json').write_text(json.dumps(sem_merged, indent=2), encoding='utf-8')
    
    # 3. Final Merge (AST + Sem)
    ast_file = out_dir / '.graphify_ast.json'
    ast = json.loads(ast_file.read_text(encoding='utf-8')) if ast_file.exists() else {'nodes':[],'edges':[]}
    
    seen = {n['id'] for n in ast.get('nodes', [])}
    final_nodes = list(ast.get('nodes', []))
    for n in sem_merged['nodes']:
        if n['id'] not in seen:
            final_nodes.append(n)
            seen.add(n['id'])
            
    final_merged = {
        'nodes': final_nodes,
        'edges': ast.get('edges', []) + sem_merged['edges'],
        'hyperedges': sem_merged['hyperedges']
    }
    (out_dir / '.graphify_extract.json').write_text(json.dumps(final_merged, indent=2), encoding='utf-8')
    
    print(f"Merged Final Extract: {len(final_nodes)} nodes, {len(final_merged['edges'])} edges")

if __name__ == "__main__":
    main()
