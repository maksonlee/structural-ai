"""Limited, non-certifying pre-publication scan of working files or Git-tracked files."""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','.venv','__pycache__','.pytest_cache','.codex','.local','private'}
RUNS=ROOT/'project/structural/outputs/runs'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tracked',action='store_true',help='Scan Git tracked files; a Git checkout is required')
    args=parser.parse_args()
    if args.tracked:
        proc=subprocess.run(['git','-C',str(ROOT),'ls-files','-z'],capture_output=True,check=True)
        files=[ROOT/p.decode() for p in proc.stdout.split(b'\0') if p]
    else:
        files=[]
        for directory, dirs, names in os.walk(ROOT):
            directory=Path(directory)
            dirs[:]=[name for name in dirs if name not in SKIP and not name.endswith('.egg-info')]
            if directory==RUNS:
                dirs[:]=[]
                names=[name for name in names if name=='README.md']
            files.extend(directory/name for name in names)
    # These patterns are intentionally limited; absence of matches is not proof of privacy.
    patterns={
        'private_key':re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
        'absolute_local_path':re.compile(r'(?:/home/[A-Za-z0-9_.-]+/|/mnt/data/|[A-Z]:\\Users\\[^\\]+\\)'),
        'likely_token':re.compile(r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}\b'),
    }
    findings=[]
    for path in files:
        rel=path.relative_to(ROOT).as_posix()
        if args.tracked and path.is_relative_to(RUNS) and path!=RUNS/'README.md':
            findings.append({'path':rel,'kind':'raw_run_must_not_be_tracked'})
        if rel==Path(__file__).relative_to(ROOT).as_posix():
            continue
        if path.stat().st_size>10*1024*1024:
            findings.append({'path':rel,'kind':'large_tracked_or_candidate_file'})
        try:
            text=path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        for kind,pat in patterns.items():
            if pat.search(text):
                findings.append({'path':rel,'kind':kind})
    print(json.dumps({'findings':findings,'files_checked':len(files),
                     'scope':'Limited automated check. Review metadata, images, logs, Git history, data rights and licenses separately.'},indent=2))
    return 1 if findings else 0

if __name__=='__main__':
    sys.exit(main())
