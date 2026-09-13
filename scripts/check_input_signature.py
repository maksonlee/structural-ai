"""Revision-specific input regression; never numerical or engineering validation."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('model', type=Path)
    args=p.parse_args()
    m=json.loads(args.model.read_text())
    fixtures={'R06':'a01_input_signature.json','H02':'h02_input_signature.json','H03-C':'h03c_input_signature.json'}
    if m.get('revision') not in fixtures:
        raise ValueError('No reviewed regression fixture for this model revision')
    fixture=fixtures[m['revision']]
    expected=json.loads((ROOT/'tests/fixtures'/fixture).read_text())
    encoded=json.dumps({k:m[k] for k in expected['signature_keys']}, sort_keys=True, separators=(',',':'), ensure_ascii=False).encode()
    actual=hashlib.sha256(encoded).hexdigest()
    result={'passed':actual==expected['canonical_input_signature_sha256'],
            'actual_sha256':actual,'expected_sha256':expected['canonical_input_signature_sha256'],
            'scope':'Revision input regression ONLY; not engineering/numerical validation', 'fixture':fixture}
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1

if __name__=='__main__':
    sys.exit(main())
