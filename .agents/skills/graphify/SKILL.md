---
name: graphify
description: "코드베이스와 문서를 분석하여 지식 그래프를 생성/쿼리합니다. 사용자가 아키텍처나 구조를 물어볼 때 `graphify-out/GRAPH_REPORT.md`가 존재하면 파일 검색 전 무조건 이 스킬을 우선 참조하십시오."
compatibility: [python 3.10+, tree-sitter, WSL/Ubuntu]
---

# /graphify

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive HTML, GraphRAG-ready JSON, and a plain-language GRAPH_REPORT.md.

## Usage

```
/graphify                                             # full pipeline on current directory
/graphify <path>                                      # full pipeline on specific path
/graphify <path> --mode deep                          # thorough extraction, richer INFERRED edges
/graphify <path> --update                             # incremental - re-extract only new/changed files
/graphify <path> --directed                            # build directed graph
/graphify <path> --cluster-only                       # rerun clustering on existing graph
/graphify <path> --no-viz                             # skip visualization, just report + JSON
/graphify add <url>                                   # fetch URL, save to ./raw, update graph
/graphify query "<question>"                          # BFS traversal - broad context
/graphify query "<question>" --dfs                    # DFS - trace a specific path
/graphify path "AuthModule" "Database"                # shortest path between two concepts
/graphify explain "SwinTransformer"                   # plain-language explanation of a node
```

## What graphify is for

1. **Persistent graph** - relationships are stored in `graphify-out/graph.json` and survive across sessions.
2. **Honest audit trail** - every edge is tagged EXTRACTED, INFERRED, or AMBIGUOUS.
3. **Cross-document surprise** - community detection finds connections between concepts in different files.

## What You Must Do When Invoked

If no path was given, use `.` (current directory). Do not ask the user for a path.
Follow these steps in order. Do not skip steps.

### Step 1 - Define Python Interpreter (WSL Optimized)

이 스킬은 공용 Conda 가상환경인 `graphify_env`를 사용합니다.

```bash
mkdir -p graphify-out
# WSL Conda 환경 경로 자동 설정
PYTHON_PATH=$(conda info --base)/envs/graphify_env/bin/python

if [ ! -f "$PYTHON_PATH" ]; then
  echo "Error: graphify_env not found. Please create it using requirements.txt in this folder."
  exit 1
fi

echo "$PYTHON_PATH" > graphify-out/.graphify_python
```

**모든 후속 작업에서 `python3` 대신 `$(cat graphify-out/.graphify_python)`를 사용하십시오.**

### Step 2 - Detect files

```bash
$(cat graphify-out/.graphify_python) .agents/skills/graphify/scripts/step2_detect.py "INPUT_PATH"
```

Replace INPUT_PATH with the actual path the user provided. Read `graphify-out/.graphify_detect.json` silently and present a clean summary instead:

```
Corpus: X files · ~Y words
  code:     N files
  docs:     N files
  papers:   N files
```

- If `total_files` is 0: stop with "No supported files found in [path]."
- If `total_words` > 2,000,000 OR `total_files` > 200: show the warning and the top 5 subdirectories by file count, then ask which subfolder to run on.

### Step 3 - Extract entities and relationships

**Run Part A (AST) and Part B (semantic) sequentially.**

#### Part A - Structural extraction for code files

```bash
$(cat graphify-out/.graphify_python) .agents/skills/graphify/scripts/step3a_ast.py
```

#### Part B - Semantic extraction (Sequential processing)

If detection found zero docs, papers, and images, skip Part B entirely and go straight to Part C.

**Step B0 - Check extraction cache first**

```bash
$(cat graphify-out/.graphify_python) .agents/skills/graphify/scripts/step3b_cache.py
```

Only process files listed in `graphify-out/.graphify_uncached.txt`. If all are cached, skip to Part C.

**Step B1 - Sequential Semantic Extraction**

Read the files listed in `graphify-out/.graphify_uncached.txt`.
You must process them sequentially (chunk by chunk). For each chunk (up to 15 files):
1. Read the files.
2. Extract the knowledge graph fragment into valid JSON matching the schema below.
3. Save the result to `graphify-out/.graphify_chunk_N.json` (where N is the chunk number) using a file write tool.

Prompt rules for your extraction:
- EXTRACTED: relationship explicit in source
- INFERRED: reasonable inference
- AMBIGUOUS: uncertain - flag for review
- Node ID format: lowercase, only [a-z0-9_]. Format: {stem}_{entity}.

Schema to save:
{"nodes":[{"id":"session_validatetoken","label":"Human Readable Name","file_type":"code|document","source_file":"relative/path"}],"edges":[{"source":"node_id","target":"node_id","relation":"calls|implements","confidence":"EXTRACTED|INFERRED","confidence_score":1.0,"source_file":"relative/path"}],"hyperedges":[]}

**Step B2 - Merge and Cache**

After all chunks are saved:

```bash
$(cat graphify-out/.graphify_python) .agents/skills/graphify/scripts/step3c_merge.py
```

### Step 4 - Build graph, cluster, analyze, generate outputs

```bash
$(cat graphify-out/.graphify_python) .agents/skills/graphify/scripts/step4_build.py "INPUT_PATH"
```

### Step 5 - Label communities

Read `graphify-out/.graphify_analysis.json`. For each community, look at its node labels and write a 2-5 word plain-language name.
Save these labels into `graphify-out/.graphify_new_labels.json` like this:
```json
{
  "0": "Data Processing",
  "1": "UI Components"
}
```

Then regenerate the report:

```bash
$(cat graphify-out/.graphify_python) .agents/skills/graphify/scripts/step5_label.py "INPUT_PATH"
```

### Step 6 - Clean up

```bash
rm -f graphify-out/.graphify_detect.json graphify-out/.graphify_extract.json graphify-out/.graphify_ast.json graphify-out/.graphify_semantic.json graphify-out/.graphify_analysis.json graphify-out/.graphify_labels.json graphify-out/.graphify_chunk_*.json
```
