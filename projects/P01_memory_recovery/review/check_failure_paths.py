"""Execute selected original/corrected AST paths with explicit test doubles."""
from __future__ import annotations

import ast
import builtins
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

import argparse
import anyio

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate', type=Path, required=True)
parser.add_argument('--previous', type=Path, required=True)
parser.add_argument('--conftest', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
ARGS = parser.parse_args()



def compiled(nodes, name):
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    return compile(ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[])), name, 'exec')


def inspect(source):
    data = source.read_bytes()
    tree = ast.parse(data)
    shared = ast.parse(ARGS.conftest.read_bytes())
    guard = next(n for n in shared.body if isinstance(n, ast.FunctionDef) and n.name == 'try_import')
    imports = [n for n in tree.body if isinstance(n, (ast.With, ast.If)) and 'imports_successful' in ast.unparse(n)]
    records = []
    for scenario in ('dependency_missing', 'integration_broken', 'imports_succeed'):
        def fake_import(name, *args, **kwargs):
            if name == 'dbos':
                if scenario == 'dependency_missing':
                    raise ImportError('simulated missing dbos')
                return SimpleNamespace(DBOS=object, DBOSConfig=dict, SetWorkflowID=object)
            if name == 'pydantic_ai.durable_exec.dbos':
                if scenario == 'integration_broken':
                    raise ImportError('simulated integration defect')
                return SimpleNamespace(DBOSDurability=object)
            return builtins.__import__(name, *args, **kwargs)
        ns = {'contextmanager': contextmanager, 'TYPE_CHECKING': False}
        exec(compiled([guard], 'actual_try_import'), ns)
        ns['__builtins__'] = dict(vars(builtins), __import__=fake_import)
        try:
            exec(compiled(imports, str(source)), ns)
        except ImportError:
            observed = 'PROPAGATED_IMPORT_ERROR'
        else:
            observed = 'IMPORT_SUCCEEDED' if ns['imports_successful']() else 'OPTIONAL_DEPENDENCY_SKIP'
        wanted = {'dependency_missing': 'OPTIONAL_DEPENDENCY_SKIP',
                  'integration_broken': 'PROPAGATED_IMPORT_ERROR', 'imports_succeed': 'IMPORT_SUCCEEDED'}[scenario]
        records.append({'case': scenario, 'observed': observed, 'expectation_met': observed == wanted})

    fixture = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'dbos')
    fixture.decorator_list = []
    for scenario in ('launch_fails', 'destroy_fails', 'normal_teardown'):
        events = []
        class FakeDBOS:
            def __init__(self, *, config):
                events.append('construct')
            @classmethod
            def launch(cls):
                events.append('launch')
                if scenario == 'launch_fails':
                    raise RuntimeError('launch failure')
            @classmethod
            def destroy(cls):
                events.append('destroy')
                if scenario == 'destroy_fails':
                    raise RuntimeError('destroy failure')
        ns = {'DBOS': FakeDBOS, 'detach_dbos_logging': lambda: events.append('detach')}
        exec(compiled([fixture], str(source)), ns)
        with tempfile.TemporaryDirectory(prefix='p01-cleanup-probe-') as folder:
            generator = ns['dbos'](SimpleNamespace(mktemp=lambda name: Path(folder)))
            try:
                next(generator)
                generator.close()
            except RuntimeError as error:
                observed = str(error)
            else:
                observed = 'CLEAN_EXIT'
        wanted_error = {'launch_fails': 'launch failure', 'destroy_fails': 'destroy failure', 'normal_teardown': 'CLEAN_EXIT'}[scenario]
        records.append({'case': scenario, 'events': events, 'observed': observed,
                        'expectation_met': events == ['construct', 'launch', 'destroy', 'detach'] and observed == wanted_error})

    timeout_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.With) and 'fail_after(' in ast.unparse(n.items[0].context_expr)]
    timeout_events = []
    if timeout_nodes:
        def immediate_deadline(seconds):
            assert seconds == 10
            timeout_events.append('configured_10_seconds_injected_zero_for_probe')
            return anyio.fail_after(0)
        class FakeHandle:
            async def get_result(self):
                try:
                    timeout_events.append('get_result_started')
                    await anyio.sleep_forever()
                finally:
                    timeout_events.append('get_result_cancelled_and_cleaned')
        async def resume(workflow_id):
            return FakeHandle()
        ns = {'fail_after': immediate_deadline, 'DBOS': SimpleNamespace(resume_workflow_async=resume), 'workflow_id': 'probe-only'}
        args = ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[])
        fn = ast.AsyncFunctionDef(name='probe', args=args, body=timeout_nodes, decorator_list=[])
        exec(compiled([fn], str(source)), ns)
        try:
            anyio.run(ns['probe'])
        except TimeoutError:
            observed = 'TIMEOUT_RAISED'
        else:
            observed = 'NO_TIMEOUT'
    else:
        observed = 'NO_TIMEOUT_SCOPE'
    records.append({'case': 'bounded_result_wait', 'observed': observed, 'events': timeout_events,
                    'expectation_met': observed == 'TIMEOUT_RAISED' and 'get_result_cancelled_and_cleaned' in timeout_events})
    return {'source_sha256': hashlib.sha256(data).hexdigest(), 'checks': records,
            'passed': sum(r['expectation_met'] for r in records), 'total': len(records),
            'scope': 'Selected exact AST paths, simulated imports/DBOS/handle; no real workflow, provider or wait.'}


results = {'before': inspect(ARGS.previous),
           'after': inspect(ARGS.candidate)}
assert results['after']['passed'] == results['after']['total'] == 7
assert not ARGS.out.exists(), 'Use a new output file'
ARGS.out.parent.mkdir(parents=True, exist_ok=True)
ARGS.out.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
print(json.dumps(results))
