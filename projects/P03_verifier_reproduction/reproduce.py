"""Execute the unchanged upstream method with real task SQL and a SQLite fixture.

This isolates aggregation, not the complete ServiceNow gym or an agent benchmark.
Configuration objects and the transport adapter are replaced; SQL is unchanged.
"""
from pathlib import Path
import argparse, ast, asyncio, copy, hashlib, json, logging, sqlite3, sys
from types import SimpleNamespace
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent

def blob_sha(raw):
    return hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()

def load_method(source, corrected=False):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'BenchmarkExecutor')
    method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_run_verifiers'))
    if corrected:
        replacements = 0
        for node in ast.walk(method):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == 'verification_results':
                        target.slice = ast.parse("f'{i}:{verifier_name}'", mode='eval').body
                        replacements += 1
        if replacements != 1:
            raise ValueError(f'Expected one aggregation assignment, received {replacements}')
    unit = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace = {'Dict': Dict, 'Any': Any, 'logger': logging.getLogger('isolated-upstream'),
                 'VerifierConfig': SimpleNamespace}
    exec(compile(unit, 'upstream/benchmark/executor.py', 'exec'), namespace)
    return namespace['_run_verifiers']

class SQLFixture:
    def __init__(self, marc, tonya):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('''
          CREATE TABLE installed_product(installed_product_id INTEGER, location_id INTEGER, status TEXT);
          CREATE TABLE customer_case(account_id INTEGER, contact_id INTEGER, channel TEXT, priority TEXT, state TEXT);
          CREATE TABLE notification(case_id INTEGER, email TEXT, type TEXT);
          INSERT INTO installed_product VALUES(40,692,'in_use');
          INSERT INTO customer_case VALUES(8,10,'alert','low','closed');
        ''')
        for exists, email in ((marc, 'marc.henry@stark-industries.com'), (tonya, 'tonya.stevens@stark-industries.com')):
            if exists:
                self.db.execute('INSERT INTO notification VALUES (?,?,?)', (1233,email,'update'))
        self.observed = []

    async def execute_verifier(self, verifier, *args, **kwargs):
        validation = verifier.validation_config
        if validation['comparison_type'] != 'equals':
            raise ValueError('The SQLite fixture supports only equals comparisons')
        observed = self.db.execute(validation['query']).fetchone()[0]
        result = {'passed': observed == validation['expected_value'], 'actual_count': observed}
        self.observed.append({'name': verifier.name, 'query': validation['query'], **result})
        return result

async def run_case(method, verifiers, marc, tonya):
    engine = SQLFixture(marc, tonya)
    try:
        obj = SimpleNamespace(config=SimpleNamespace(verifiers=verifiers),
                              gym_configs=[{'mcp_server_name':'sn-csm-server','database_id':'fixture'}],
                              verifier_engine=engine)
        results = await method(obj, {'final_response':'', 'tool_results':[]})
        # An executed-only oracle cannot decide omitted obligations. Refuse the
        # incomplete case; do not rewrite the upstream aggregation or its keys.
        if not verifiers or len(engine.observed) != len(verifiers):
            raise ValueError('Configured verifier coverage is empty or incomplete')
        if not isinstance(results, dict) or not results:
            raise ValueError('No usable verifier results')
        if any(type(row.get('passed')) is not bool for row in engine.observed) or any(
            not isinstance(row, dict) or type(row.get('passed')) is not bool
            for row in results.values()
        ):
            raise ValueError('Verifier passed values must be booleans; UNKNOWN cannot pass')
        truth = all(r['passed'] for r in engine.observed)
        reported = all(r['passed'] for r in results.values())
        return {'configured_checks':len(verifiers),'executed_checks':len(engine.observed),
                'retained_checks':len(results),'all_executed_pass':truth,
                'reported_success':reported, 'false_positive':not truth and reported,
                'oracle':engine.observed,'retained':results}
    finally:
        engine.db.close()

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    pins=json.loads((ROOT/'vendor/UPSTREAM.json').read_text(encoding='utf-8'))
    raw={name:(ROOT/record['path']).read_bytes() for name,record in pins.items()}
    for name,record in pins.items():
        if blob_sha(raw[name])!=record['git_blob_sha'] or hashlib.sha256(raw[name]).hexdigest()!=record['sha256']:
            raise ValueError('Upstream source identity mismatch: '+name)
    text={name:data.decode('utf-8') for name,data in raw.items()}
    source_record,task_record=pins['main'],pins['task']
    source,task_text=text['main'],text['task']
    verifiers = json.loads(task_text)['verifiers']
    methods = {'upstream':load_method(source), 'stable_index_candidate':load_method(source, True), 'pr24':load_method(text['pr24'])}
    cases = {}
    for marc, tonya in ((False,False),(False,True),(True,False),(True,True)):
        for reverse in (False,True):
            current = copy.deepcopy(verifiers)
            if reverse:
                current[-2:] = reversed(current[-2:])
            name = f'marc={marc};tonya={tonya};reversed={reverse}'
            cases[name] = {m:await run_case(fn,current,marc,tonya) for m,fn in methods.items()}
    upstream_fp = sum(c['upstream']['false_positive'] for c in cases.values())
    candidate_fp = sum(c['stable_index_candidate']['false_positive'] for c in cases.values())
    pr24_fp = sum(c['pr24']['false_positive'] for c in cases.values())
    if (upstream_fp, candidate_fp, pr24_fp) != (2, 0, 0):
        raise RuntimeError('Unexpected aggregation outcomes in the pinned fixture')
    if not all(c['upstream']['retained_checks']==3 and c['stable_index_candidate']['retained_checks']==4
               and c['pr24']['retained_checks']==4 for c in cases.values()):
        raise RuntimeError('Unexpected retained verifier cardinality')
    result = {'scope':'isolated unchanged upstream aggregation method + actual public task queries + SQLite fixture; no full gym or LLM run',
              'source_blob_sha':source_record['git_blob_sha'],'task_blob_sha':task_record['git_blob_sha'],
              'python':sys.version,'cases':cases,'upstream_false_positives':upstream_fp,
              'candidate_false_positives':candidate_fp, 'pr24_false_positives':pr24_fp,
              'interpretation':'Known issue #23 reproduced in pinned upstream source. Stable-index mitigation retains checks in these fixtures; no novelty, general alignment, adoption or production-readiness claim.'}
    output=args.out
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'cases':len(cases),'upstream_false_positives':upstream_fp,'candidate_false_positives':candidate_fp,'output':str(output)}))

if __name__=='__main__':
    asyncio.run(main())
