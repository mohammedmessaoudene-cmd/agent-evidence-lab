#!/usr/bin/env python3
"""Independent, deterministic review of native OpenHTF exports.

No candidate adapter imports, normalized candidate output, instrument control,
network access, or LLM calls.  The supported profile is specified by the frozen
R2 protocol.  READY_FOR_REVIEW is documentary, never a material release.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
from pathlib import Path


def _strict_json(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError("Non-finite JSON constant: " + value)

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("JSON exponent overflows a finite float")
        return result

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=bad_constant, parse_float=finite_float)


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _scalar(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _millis(value):
    # A finite nonnegative integer count is the supported framework profile.
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 253402300799999


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _same(a, b):
    # Keep JSON booleans distinct from integers and retain type information.
    return json.dumps(a, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(b, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _attachment_bytes(value):
    if not isinstance(value, str) or not value.isascii():
        raise ValueError("Attachment data must be ASCII base64")
    raw = base64.b64decode(value, validate=True)
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("Noncanonical base64 attachment")
    return raw


def review(contract_path, expected_contract_sha256, input_dir):
    """Review native exports with an independently supplied contract digest.

    Parsing and checks here are independent of the candidate adapter.  Unknown
    physical authentication remains explicit even when all checks pass.
    """
    issues = []
    findings = []
    source_files = []
    duplicates = 0
    seen_hashes = set()
    seen_duts = set()
    seen_run_ids = set()
    contract_hash = None

    def problem(code, location, detail):
        issues.append({"code": code, "location": location, "detail": detail})

    def require(condition, code, location, detail):
        if not condition:
            problem(code, location, detail)
        return bool(condition)

    def obj(value, label):
        if not isinstance(value, dict):
            raise ValueError(label + " must be a JSON object")
        return value

    def outcome():
        return {
            "schema": "p05-independent-native-review/2",
            "status": "INCOMPLETE" if issues else "READY_FOR_REVIEW",
            "measurement_summary": "UNKNOWN" if issues else ("FAIL" if any(x["computed_outcome"] == "FAIL" for x in findings) else "PASS"),
            "material_release_authorized": False,
            "physical_validation": "NOT_RUN",
            "instrument_equivalence": "NOT_ESTABLISHED",
            "evidence_authentication": "NOT_IMPLEMENTED",
            "clock_authentication": "UNKNOWN",
            "calibration_authentication": "UNKNOWN",
            "human_review_time": "NOT_MEASURED",
            "decision_engine": "INDEPENDENT_DETERMINISTIC_SCRIPT",
            "contract_sha256": contract_hash,
            "contract_expected_digest_matched": contract_hash == expected_contract_sha256,
            "duplicate_identical_replays": duplicates,
            "unique_exports": len(seen_hashes),
            "sources": source_files,
            "measurements": findings,
            "issues": issues,
            "scope": "Documentary consistency of the declared simple scalar profile; no source, clock, calibration or physical authentication",
        }

    try:
        contract_raw = Path(contract_path).read_bytes()
        contract_hash = _hash(contract_raw)
        require(isinstance(expected_contract_sha256, str) and len(expected_contract_sha256) == 64 and contract_hash == expected_contract_sha256,
                "CONTRACT_UNTRUSTED", "contract", "Expected SHA256 must match and arrive outside submitted exports")
        contract = obj(_strict_json(contract_raw), "contract")
        require(contract.get("schema") == "p05-openhtf-contract/2" and contract.get("profile") == "SIMPLE_SCALAR_IN_RANGE",
                "CONTRACT_PROFILE", "contract", "Only the frozen simple-scalar contract is supported")
        identities = obj(contract.get("identity"), "identity")
        order = obj(contract.get("work_order"), "work_order")
        expected_runs = obj(order.get("expected_runs"), "expected_runs")
        require(bool(expected_runs) and all(_nonempty(k) and _nonempty(v) for k, v in expected_runs.items()) and len(set(expected_runs.values())) == len(expected_runs),
                "CONTRACT_POPULATION", "contract", "Unique nonempty DUT/run mapping is required")
        spec = obj(contract.get("measurement"), "measurement")
        low, high = spec.get("lower"), spec.get("upper")
        require(_scalar(low) and _scalar(high) and low <= high, "CONTRACT_LIMITS", "contract", "Finite ordered inclusive limits required")
        require(spec.get("validators") == [f"{low} <= x <= {high}"], "CONTRACT_VALIDATOR", "contract", "The single validator string must match the approved bounds")
        require(all(_nonempty(identities.get(k)) for k in ("product", "board_revision", "firmware_sha256", "procedure_version")),
                "CONTRACT_IDENTITY", "contract", "Nonempty identity fields required")
        require(all(_nonempty(order.get(k)) for k in ("lot_id", "station_id", "evidence_kind")), "CONTRACT_JOB", "contract", "Nonempty work-order fields required")
        require(all(_nonempty(spec.get(k)) for k in ("phase", "name", "instrument_id")), "CONTRACT_MEASUREMENT", "contract", "Phase, measurement and instrument identity required")
        unit_spec = obj(spec.get("unit"), "unit")
        require(set(unit_spec) == {"name", "code", "suffix"} and all(_nonempty(v) for v in unit_spec.values()), "CONTRACT_UNIT", "contract", "Exact native unit descriptor required")
        clock_policy = obj(contract.get("clock_policy"), "clock_policy")
        instrument_policy = obj(contract.get("instrument_policy"), "instrument_policy")
        require(all(_nonempty(clock_policy.get(k)) for k in ("basis", "status")), "CONTRACT_CLOCK", "contract", "Clock declaration policy required")
        require(all(_nonempty(instrument_policy.get(k)) for k in ("id", "serial", "calibration_status")), "CONTRACT_INSTRUMENT", "contract", "Declared instrument policy required")
        require(instrument_policy.get("id") == spec.get("instrument_id"), "CONTRACT_INSTRUMENT", "contract", "Measurement and instrument policy differ")
        require(contract.get("release_policy") == "NEVER_AUTHORIZE", "RELEASE_POLICY", "contract", "This script cannot authorize release")
        attachments_required = contract.get("required_attachments")
        if not isinstance(attachments_required, list) or not all(isinstance(x, dict) for x in attachments_required):
            raise ValueError("required_attachments must be a list of objects")
        root = Path(input_dir).resolve()
        if not root.is_dir():
            raise ValueError("input_dir is not a directory")
        files = sorted(root.glob("*.json"))
        require(bool(files), "NO_EXPORTS", "input", "At least one native export required")
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError, AttributeError, RecursionError, RuntimeError) as exc:
        problem("CONTRACT_OR_INPUT_INVALID", "input", type(exc).__name__ + ": " + str(exc))
        return outcome()

    for path in files:
        loc = path.name
        try:
            if not path.resolve().is_relative_to(root) or not path.is_file():
                raise ValueError("Source path leaves evidence directory or is not a file")
            if path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Source exceeds the 10 MiB input profile")
            raw = path.read_bytes()
            source_hash = _hash(raw)
            source_files.append({"path": path.name, "bytes": len(raw), "sha256": source_hash})
            if source_hash in seen_hashes:
                duplicates += 1
                continue
            seen_hashes.add(source_hash)
            record = obj(_strict_json(raw), "export")
            uid = record.get("dut_id")
            if not require(_nonempty(uid), "DUT_MISSING", loc, "Native dut_id is missing or invalid"):
                continue
            require(uid in expected_runs, "DUT_UNEXPECTED", loc, "DUT differs from independently approved population")
            require(uid not in seen_duts, "DUT_DUPLICATE", loc, "Different source records for one DUT require human adjudication")
            seen_duts.add(uid)
            require(record.get("station_id") == order.get("station_id"), "STATION_MISMATCH", loc, "Native station differs from work order")
            metadata = obj(record.get("metadata"), "metadata")
            declarations = obj(metadata.get("p05"), "metadata.p05")
            for key in ("product", "board_revision", "firmware_sha256", "procedure_version"):
                require(declarations.get(key) == identities.get(key), "IDENTITY_MISMATCH", loc + ":" + key, "Declared identity differs from approved contract")
            for key in ("lot_id", "evidence_kind"):
                require(declarations.get(key) == order.get(key), "WORK_ORDER_MISMATCH", loc + ":" + key, "Declared job differs from approved work order")
            run_id = declarations.get("run_id")
            require(_nonempty(run_id) and run_id == expected_runs.get(uid), "RUN_MISMATCH", loc, "Declared run does not match approved DUT/run mapping")
            if _nonempty(run_id):
                require(run_id not in seen_run_ids, "RUN_DUPLICATE", loc, "Different exports share one run identifier")
                seen_run_ids.add(run_id)
            clock = obj(declarations.get("clock"), "clock declaration")
            require(_same(clock, clock_policy), "CLOCK_DECLARATION", loc, "Exact clock declaration policy required; authenticity remains unknown")
            run_start, run_end = record.get("start_time_millis"), record.get("end_time_millis")
            valid_run_time = _millis(run_start) and _millis(run_end) and 0 < run_start <= run_end
            require(valid_run_time, "RUN_TIME", loc, "Ordered integer native run timestamps required")

            instruments = declarations.get("instruments")
            if not isinstance(instruments, list) or not all(isinstance(x, dict) for x in instruments):
                raise ValueError("instruments must be a list of objects")
            require(len(instruments) == 1, "INSTRUMENT_PROFILE", loc, "The supported profile has exactly one instrument declaration")
            ids = [x.get("id") for x in instruments]
            if not all(_nonempty(x) for x in ids):
                raise ValueError("Instrument IDs must be nonempty strings")
            require(len(ids) == len(set(ids)), "INSTRUMENT_DUPLICATE", loc, "Instrument IDs must be unique")
            chosen = [x for x in instruments if x.get("id") == spec["instrument_id"]]
            if len(chosen) != 1:
                raise ValueError("Exactly one source declaration for the measurement instrument required")
            instrument = chosen[0]
            for key, expected_value in instrument_policy.items():
                require(key in instrument and _same(instrument[key], expected_value), "INSTRUMENT_DECLARATION", loc + ":" + key, "Required declared instrument metadata is missing or differs")
            cal_from, cal_until = instrument.get("calibration_valid_from_millis"), instrument.get("calibration_valid_until_millis")
            valid_cal_time = _millis(cal_from) and _millis(cal_until) and cal_from <= cal_until
            require(valid_cal_time, "CALIBRATION_UNKNOWN", loc, "Declared calibration interval is missing or invalid")
            binding = obj(declarations.get("measurement_instruments"), "measurement_instruments")
            require(_same(binding, {spec["name"]: spec["instrument_id"]}), "INSTRUMENT_BINDING", loc, "Exact measurement-to-instrument declaration required")

            phases = record.get("phases")
            if not isinstance(phases, list) or len(phases) != 1 or not isinstance(phases[0], dict):
                raise ValueError("The supported profile requires one phase, without repeated attempts")
            phase = phases[0]
            require(phase.get("name") == spec["phase"], "PHASE_IDENTITY", loc, "Unexpected phase")
            require(phase.get("marginal") is None or phase.get("marginal") is False, "UNSUPPORTED_PHASE_MARGINAL", loc, "Phase marginality must be absent/null or Boolean false in this profile")
            phase_start, phase_end = phase.get("start_time_millis"), phase.get("end_time_millis")
            valid_phase_time = _millis(phase_start) and _millis(phase_end) and phase_start <= phase_end
            require(valid_phase_time and valid_run_time and run_start <= phase_start <= phase_end <= run_end,
                    "PHASE_TIME", loc, "Phase must have ordered native timestamps within the run")
            require(valid_run_time and valid_cal_time and cal_from <= run_start <= run_end <= cal_until,
                    "CALIBRATION_INTERVAL", loc, "The entire run must fit the declared calibration interval under the conservative profile; this is not authentication")
            measurements = obj(phase.get("measurements"), "measurements")
            require(set(measurements) == {spec["name"]}, "MEASUREMENT_POPULATION", loc, "Exactly the required scalar measurement is supported")
            measurement = obj(measurements.get(spec["name"]), "measurement")
            require(measurement.get("name") == spec["name"], "MEASUREMENT_IDENTITY", loc, "Measurement key and native name differ")
            require(measurement.get("marginal") is None or measurement.get("marginal") is False, "UNSUPPORTED_MEASUREMENT_MARGINAL", loc, "Measurement marginality must be absent/null or Boolean false in this profile")
            require(_same(measurement.get("units"), spec["unit"]), "UNIT_MISMATCH", loc, "No implicit unit conversion is allowed")
            require(_same(measurement.get("validators"), spec["validators"]), "VALIDATOR_MISMATCH", loc, "Native validator text differs from the approved simple range")
            for field in ("dimensions", "conditional_validators"):
                value = measurement.get(field)
                require(value is None or (isinstance(value, list) and len(value) == 0), "UNSUPPORTED_MEASUREMENT", loc + ":" + field, "Only an absent/null or an empty list is compatible with the scalar profile")
            allow_fail = measurement.get("allow_fail")
            require(allow_fail is None or allow_fail is False, "FAILURE_OVERRIDE", loc, "A present failure override must be the Boolean false; integer zero is not false metadata")
            individual_time = measurement.get("set_time_millis")
            if individual_time is not None:
                require(_millis(individual_time) and valid_phase_time and phase_start <= individual_time <= phase_end,
                        "MEASUREMENT_TIME", loc, "A supplied measurement timestamp must be an integer within the phase")
            value = measurement.get("measured_value")
            valid_value = _scalar(value)
            require(valid_value, "MEASUREMENT_VALUE", loc, "Finite scalar numeric measurement required; booleans are not numbers")
            computed = ("PASS" if low <= value <= high else "FAIL") if valid_value and _scalar(low) and _scalar(high) else "UNKNOWN"
            require(measurement.get("outcome") == computed, "MEASUREMENT_OUTCOME", loc, "Native outcome contradicts value and approved bounds")
            require(phase.get("outcome") == computed, "PHASE_OUTCOME", loc, "Phase outcome contradicts this profile's complete measurement")
            phase_result = obj(phase.get("result"), "phase result")
            require(_same(phase_result, {"phase_result": "CONTINUE"}), "PHASE_RESULT", loc, "Only an unqualified CONTINUE phase is supported; CONTINUE does not mean PASS")
            require(record.get("outcome") == computed, "RUN_OUTCOME", loc, "Native run outcome contradicts the single supported phase")
            for key in ("diagnoses", "diagnosers", "subtests", "branches", "checkpoints", "outcome_details"):
                value = record.get(key)
                require(key not in record or (isinstance(value, list) and not value), "UNSUPPORTED_RUN_STRUCTURE", loc + ":" + key, "Only an absent field or an empty native list is within this profile")
            require(record.get("marginal") is None or record.get("marginal") is False, "UNSUPPORTED_MARGINAL", loc, "Marginal results require an explicit profile")
            for key in ("diagnosis_results", "failure_diagnosis_results", "diagnosers"):
                value = phase.get(key)
                require(key not in phase or (isinstance(value, list) and not value), "UNSUPPORTED_PHASE_STRUCTURE", loc + ":" + key, "Only an absent field or an empty native list is within this profile")
            require(phase.get("subtest_name") is None, "UNSUPPORTED_PHASE_STRUCTURE", loc + ":subtest_name", "A subtest association requires a separate profile")

            attached = obj(phase.get("attachments"), "attachments")
            checked_attachments = {}
            for name, attached_value in attached.items():
                data = obj(attached_value, "attachment")
                payload = _attachment_bytes(data.get("data"))
                require(_nonempty(data.get("mimetype")), "ATTACHMENT_MIMETYPE", loc + ":" + name, "Attachment media type is missing")
                require(data.get("sha1") == hashlib.sha1(payload).hexdigest(), "ATTACHMENT_SHA1", loc + ":" + name, "Native attachment digest does not match decoded bytes")
                checked_attachments[name] = {"sha256": _hash(payload), "bytes": len(payload), "mimetype": data.get("mimetype")}
            for required in attachments_required:
                if required.get("phase") != phase.get("name"):
                    problem("REQUIRED_ATTACHMENT_PHASE", loc, "Required attachment phase is absent")
                    continue
                name = required.get("name")
                actual = checked_attachments.get(name)
                require(actual is not None, "ATTACHMENT_MISSING", loc, "Required attachment is absent")
                if actual is not None:
                    require(actual["sha256"] == required.get("sha256") and actual["mimetype"] == required.get("mimetype"),
                            "ATTACHMENT_CONTRACT", loc + ":" + name, "Attachment bytes or media type differ from contract")
            findings.append({
                "dut_id": uid,
                "run_id": run_id,
                "source_sha256": source_hash,
                "phase": phase.get("name"),
                "name": measurement.get("name"),
                "value": value,
                "units": measurement.get("units"),
                "validators": measurement.get("validators"),
                "native_measurement_outcome": measurement.get("outcome"),
                "native_phase_outcome": phase.get("outcome"),
                "native_phase_result": phase.get("result"),
                "native_run_outcome": record.get("outcome"),
                "computed_outcome": computed,
                "run_time_millis": [run_start, run_end],
                "phase_time_millis": [phase_start, phase_end],
                "individual_measurement_time": individual_time,
                "individual_measurement_time_status": "EXPORTED_FIELD_UNAUTHENTICATED" if "set_time_millis" in measurement else "UNKNOWN_NOT_EXPORTED",
                "allow_fail": allow_fail,
                "allow_fail_status": "EXPORTED_FIELD_UNAUTHENTICATED" if "allow_fail" in measurement else "UNKNOWN_NOT_EXPORTED",
                "clock_declaration": clock,
                "instrument_declaration": instrument,
                "attachments": checked_attachments,
            })
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, UnicodeError, binascii.Error, RecursionError, RuntimeError) as exc:
            problem("NATIVE_EXPORT_INVALID", loc, type(exc).__name__ + ": " + str(exc))

    require(seen_duts == set(expected_runs), "POPULATION_INCOMPLETE", "input", "Submitted DUT population must exactly match the independently approved work order")
    require(len(findings) == len(expected_runs), "MEASUREMENT_COVERAGE", "input", "Every expected DUT must have one complete supported observation")
    return outcome()


def _save_new_report(path, result):
    """Write one fresh UTF-8 JSON report without replacing evidence."""
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise FileExistsError("Output destination already exists: " + str(path))
    raw = (json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with path.open("xb") as stream:
            created = True
            stream.write(raw)
    except (OSError, ValueError):
        if created:
            try:
                path.unlink()
            except OSError:
                pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--expected-contract-sha256", required=True)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = review(args.contract, args.expected_contract_sha256, args.input_dir)
    if args.out is not None:
        try:
            _save_new_report(args.out, result)
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            result = dict(result)
            result.update(status="INCOMPLETE", measurement_summary="UNKNOWN",
                          material_release_authorized=False)
            result["issues"] = list(result.get("issues", [])) + [{
                "code": "OUTPUT_PERSISTENCE", "location": "output",
                "detail": type(exc).__name__ + ": " + str(exc)}]
    encoded = json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    print(encoded, end="")
    return 0 if result["status"] == "READY_FOR_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())

