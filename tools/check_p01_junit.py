from pathlib import Path
import sys,xml.etree.ElementTree as ET
root=ET.parse(Path(sys.argv[1])).getroot();cases=root.findall('.//testcase');suites=root.findall('.//testsuite')
expected={('tests.harness.memory.test_dbos_recovery.TestMemoryDBOSRecovery','test_recovery_restores_snapshot_after_compaction'),('tests.harness.memory.test_memory','test_snapshot_load_dispatches_as_durable_operation')}
observed=[(c.get('classname'),c.get('name')) for c in cases]
if len(cases)!=2 or len(set(observed))!=2 or set(observed)!=expected or any(c.find(x) is not None for c in cases for x in ['failure','error','skipped']):raise SystemExit('P01 requires the exact native and dispatch cases, each passing once, no skip/error')
if len(suites)!=1 or any(int(suites[0].get(k,'-1'))!=v for k,v in {'tests':2,'failures':0,'errors':0,'skipped':0}.items()):raise SystemExit('P01 suite counters missing or inconsistent')
print('PASS: one native journal case + one recording-dispatch case')
