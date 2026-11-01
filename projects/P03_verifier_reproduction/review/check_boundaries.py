# SPDX-License-Identifier: MIT
"""Bounded synthetic regressions; no network, complete gym, or LLM run."""
from __future__ import annotations

import argparse
import ast
import asyncio
import copy
import hashlib
import importlib.util
import json
import platform
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

DRIVERS = {
    "baseline": "2f6ba69d4b69d1392d303cdd39a837e360e249905c14caf29a403f0923a74ff4",
    "hardened": "7027f86eaadaa842a0aa1040219a9870a8b0faf6834f5c7b2a6c053f47fd2bb8",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(project, variant):
    path = project / "reproduce.py"
    if digest(path) != DRIVERS[variant]:
        raise ValueError("Unexpected driver bytes")
    spec = importlib.util.spec_from_file_location("p03_boundary_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReachedMethodLoading(Exception):
    pass


def preflight(module, project, hardened):
    rows = []
    for mutation in ("unchanged", "crlf_only", "content_changed"):
        with tempfile.TemporaryDirectory(prefix="p03-boundary-") as directory:
            target = Path(directory)
            shutil.copytree(project / "vendor", target / "vendor")
            source = target / "vendor/main_executor.py"
            original = source.read_bytes()
            if mutation == "crlf_only":
                altered = original.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                if altered == original:
                    raise RuntimeError("CRLF probe did not alter bytes")
                source.write_bytes(altered)
            elif mutation == "content_changed":
                source.write_bytes(original + b"\n# synthetic alteration\n")
            with patch.object(module, "ROOT", target), patch.object(
                module, "load_method", side_effect=ReachedMethodLoading
            ) as boundary, patch.object(module, "run_case") as cases, patch.object(
                module, "SQLFixture"
            ) as fixtures, patch.object(sys, "argv", ["reproduce.py", "--out", str(target / "out.json")]):
                coroutine = module.main()
                error = None
                try:
                    coroutine.send(None)
                except ReachedMethodLoading:
                    accepted = True
                except ValueError as exc:
                    accepted = False
                    error = str(exc)
                else:
                    raise RuntimeError("Preflight unexpectedly yielded")
                finally:
                    coroutine.close()
                if cases.called or fixtures.called:
                    raise RuntimeError("Preflight scope exceeded")
                expected = mutation == "unchanged" or (mutation == "crlf_only" and not hardened)
                rows.append(dict(case=mutation, accepted=accepted, expected=expected,
                                 matches_expected=accepted == expected,
                                 method_loading_boundary_calls=boundary.call_count,
                                 run_case_calls=cases.call_count, fixture_constructions=fixtures.call_count,
                                 original_sha256=hashlib.sha256(original).hexdigest(),
                                 tested_sha256=digest(source), error=error))
    return rows


def connection_open(db):
    try:
        db.execute("SELECT 1").fetchone()
        return True
    except sqlite3.ProgrammingError as exc:
        if "closed" not in str(exc).lower():
            raise
        return False


async def semantics(module, project, hardened):
    verifiers = json.loads((project / "vendor/task.json").read_text(encoding="utf-8"))["verifiers"]
    source = (project / "vendor/main_executor.py").read_text(encoding="utf-8")
    methods = {"main": module.load_method(source), "stable_index": module.load_method(source, True),
               "pr24": module.load_method((project / "vendor/pr24_executor.py").read_text(encoding="utf-8"))}
    rows = []
    for case in ("positive", "all_gyms_absent", "empty", "false_prerequisite_executed",
                 "false_prerequisite_skipped", "unknown_none", "unknown_string", "sql_exception"):
        configured = copy.deepcopy(verifiers)
        if case == "positive":
            for index, item in enumerate(configured):
                item["name"] = f"synthetic-obligation-{index}"
        elif case == "all_gyms_absent":
            for item in configured:
                item["gym_name"] = "synthetic-unconfigured-gym"
        elif case == "empty":
            configured = []
        elif case == "false_prerequisite_skipped":
            configured[0]["gym_name"] = "synthetic-unconfigured-gym"
        elif case == "sql_exception":
            configured[0]["validation_config"]["query"] = "SELECT COUNT(*) FROM synthetic_missing_table"
        for arm, method in methods.items():
            instances = []
            original_fixture = module.SQLFixture

            class ObservedFixture(original_fixture):
                def __init__(self, marc, tonya):
                    super().__init__(marc, tonya)
                    instances.append(self)
                    if case.startswith("false_prerequisite"):
                        self.db.execute("DELETE FROM installed_product")

                async def execute_verifier(self, verifier, *args, **kwargs):
                    result = await super().execute_verifier(verifier, *args, **kwargs)
                    if case.startswith("unknown_") and "installed_product" in verifier.validation_config["query"]:
                        result["passed"] = None if case == "unknown_none" else "UNKNOWN"
                        self.observed[-1]["passed"] = result["passed"]
                    return result

            record, error = None, None
            try:
                with patch.object(module, "SQLFixture", ObservedFixture):
                    try:
                        record = await module.run_case(method, configured, True, True)
                    except (ValueError, sqlite3.OperationalError) as exc:
                        error = type(exc).__name__
                if len(instances) != 1:
                    raise RuntimeError("Unexpected fixture count")
                opened = connection_open(instances[0].db)
                success = None if record is None else record["reported_success"]
                expected_error = "OperationalError" if case == "sql_exception" else (
                    "ValueError" if hardened and case in {"all_gyms_absent", "empty", "false_prerequisite_skipped", "unknown_none", "unknown_string"} else None)
                expected_success = None if expected_error else case not in {"false_prerequisite_executed", "unknown_none"}
                expected_open = case == "sql_exception" and not hardened
                matches = (error, success, opened) == (expected_error, expected_success, expected_open)
                if case == "positive":
                    matches = matches and record["configured_checks"] == record["executed_checks"] == record["retained_checks"] == 4
                rows.append(dict(case=case, arm=arm, error=error, reported_success=success,
                                 connection_open_before_probe_cleanup=opened, matches_expected=matches,
                                 configured=len(configured), observed=len(instances[0].observed),
                                 retained=None if record is None else record["retained_checks"],
                                 expected_error=expected_error, expected_success=expected_success,
                                 expected_connection_open=expected_open))
            finally:
                for instance in instances:
                    instance.db.close()
    return rows


def summary_guards(project, hardened):
    tree = ast.parse((project / "reproduce.py").read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "main")
    def assigned(node, name):
        return isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
    start = next(i for i, n in enumerate(main.body) if assigned(n, "upstream_fp"))
    end = next(i for i, n in enumerate(main.body) if assigned(n, "result"))
    rows = []
    for optimize in (0, 1):
        unit = ast.fix_missing_locations(ast.Module(body=copy.deepcopy(main.body[start:end]), type_ignores=[]))
        code = compile(unit, "p03-summary-fragment", "exec", optimize=optimize)
        for case in ("valid", "empty", "main_fp", "candidate_fp", "pr24_fp", "main_retained", "candidate_retained", "pr24_retained"):
            cases = {str(i): {"upstream": {"false_positive": True, "retained_checks": 3},
                              "stable_index_candidate": {"false_positive": False, "retained_checks": 4},
                              "pr24": {"false_positive": False, "retained_checks": 4}} for i in range(2)}
            if case == "empty":
                cases = {}
            elif case != "valid":
                arm, field = case.split("_")
                row = cases["0"][{"main": "upstream", "candidate": "stable_index_candidate", "pr24": "pr24"}[arm]]
                row["false_positive" if field == "fp" else "retained_checks"] = (arm != "main") if field == "fp" else 1
            error = None
            try:
                exec(code, {"cases": cases})
            except (AssertionError, RuntimeError) as exc:
                error = type(exc).__name__
            accepted = error is None
            expected = case == "valid" or (not hardened and (optimize == 1 or case == "pr24_retained"))
            rows.append(dict(case=case, compile_optimization=optimize, accepted=accepted,
                             expected=expected, matches_expected=accepted == expected, error=error))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--variant", choices=DRIVERS, default="hardened")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("Choose a fresh report path")
    module = load(args.project, args.variant)
    hardened = args.variant == "hardened"
    groups = {"preflight": preflight(module, args.project, hardened),
              "run_case": asyncio.run(semantics(module, args.project, hardened)),
              "summary_fragment": summary_guards(args.project, hardened)}
    ok = all(row["matches_expected"] for rows in groups.values() for row in rows)
    result = dict(status="PASS" if ok else "FAIL", variant=args.variant,
                  driver_sha256=digest(args.project / "reproduce.py"), probe_sha256=digest(Path(__file__)),
                  python=sys.version, platform=platform.platform(), no_site=sys.flags.no_site,
                  dont_write_bytecode=sys.dont_write_bytecode, observations=groups,
                  scope="3 stopped CLI preflights; 8 synthetic run_case boundaries across 3 extracted methods; 8 artificial summary shapes compiled at 0/1. No complete CLI or historical eight-case run here.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"status": result["status"], "observations": {k: len(v) for k, v in groups.items()}}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
