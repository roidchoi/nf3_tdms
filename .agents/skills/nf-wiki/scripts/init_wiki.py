import os
import shutil
import argparse
from pathlib import Path

def init_wiki(wiki_root="./pjt_wiki", template_dir=".agents/skills/nf-wiki/templates", sub_projects=None):
    wiki_path = Path(wiki_root)
    template_path = Path(template_dir)
    
    if not template_path.exists():
        print(f"Error: Template directory '{template_dir}' not found.")
        return

    # 1. Create Base Structure
    if not wiki_path.exists():
        os.makedirs(wiki_path)
        print(f"Created wiki root at: {wiki_path}")
    else:
        print(f"Wiki root '{wiki_path}' already exists. Overwriting/updating missing files.")

    # 2. Copy 00_schema
    schema_src = template_path / "00_schema"
    schema_dest = wiki_path / "00_schema"
    if schema_src.exists():
        shutil.copytree(schema_src, schema_dest, dirs_exist_ok=True)
        # policy.md는 references로 옮겼으므로 복사본에 남아있다면 삭제
        policy_file = schema_dest / "policy.md"
        if policy_file.exists():
            os.remove(policy_file)
        print(f"Copied schema templates to {schema_dest}")

    # 3. Copy parent_wiki
    parent_src = template_path / "parent_wiki"
    parent_dest = wiki_path / "parent_wiki"
    if parent_src.exists():
        shutil.copytree(parent_src, parent_dest, dirs_exist_ok=True)
        print(f"Copied parent_wiki templates to {parent_dest}")

    # 4. Handle Sub Projects
    if sub_projects:
        for sp in sub_projects:
            sp_src = template_path / "pn_wiki"
            sp_dest = wiki_path / f"{sp}_wiki"
            if sp_src.exists():
                shutil.copytree(sp_src, sp_dest, dirs_exist_ok=True)
                print(f"Created sub-project wiki at: {sp_dest}")
            else:
                print(f"Warning: Sub-project template '{sp_src}' not found.")

    print("\n[nf-wiki] Initialization complete.")
    print("Next steps: Update 00_schema/index.md and parent_wiki/overview.md with your project details.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize project wiki (pjt_wiki).")
    parser.add_argument("--root", default="./pjt_wiki", help="Root directory for the wiki")
    parser.add_argument("--sub-project", nargs="*", help="List of sub-projects to initialize (e.g. p1 p2)")
    
    args = parser.parse_args()
    init_wiki(wiki_root=args.root, sub_projects=args.sub_project)
