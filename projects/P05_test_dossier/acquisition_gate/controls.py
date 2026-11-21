"""Read the frozen synthetic example; mutate independent in-memory copies only."""
from copy import deepcopy
import json
from pathlib import Path

from observer import inspect, read_bundle


fixture = Path(__file__).resolve().parent / "SYNTHETIC"
manifest, sources = read_bundle(fixture)
base = inspect(manifest, sources)
expected = [("A1", ["A1"], True, False), ("A1", [], False, True)]
assert [(r["consumed_conversion_id"], r["declared_conversion_ids_for_request"],
         r["consumed_response_uses_conversion_triggered_by_request"], r["low_alarm_disagrees_with_reference"])
        for r in base["rows"]] == expected
checks = {"linked_direct_and_cache": "PASS"}

copy = deepcopy(sources)
copy["acquisition"]["rows"].append(dict(copy["acquisition"]["rows"][0], id="A2", seq=2,
                                        trigger="Q2", t_ns=51, uv=121))
q2_result = inspect(manifest, copy)
q2 = q2_result["rows"][1]
assert q2["request"] == "Q2" and q2["decision"] == "D2" and q2["origin"] == "CACHE"
assert q2["declared_conversion_ids_for_request"] == ["A2"] and q2["consumed_conversion_id"] == "A1"
assert q2["consumed_response_uses_conversion_triggered_by_request"] is False
assert q2_result["acquisition_log_completeness"] == "UNKNOWN"
checks["q2_triggers_a2_but_cache_delivers_a1"] = "PASS"

# Change only the separate conversion. The cached response still consumes A1.
for tick, trigger, name in (
    (1, "Q2", "separate_conversion_before_cached_request"),
    (49, "Q2", "separate_conversion_one_tick_before_request"),
    (9, "Q1", "separate_conversion_before_direct_request"),
):
    copy["acquisition"]["rows"][-1].update(t_ns=tick, trigger=trigger)
    try:
        inspect(manifest, copy)
    except ValueError as error:
        assert str(error) == "declared conversion predates request"
    else:
        raise AssertionError(name)
    checks[name] = "REJECTED_AS_EXPECTED"

for tick, name in ((50, "separate_conversion_at_request_start"),
                   (53, "separate_conversion_after_decision")):
    copy["acquisition"]["rows"][-1].update(t_ns=tick, trigger="Q2")
    assert inspect(manifest, copy) == q2_result
    checks[name] = "PASS"


def check(name, role, index, changes, reason):
    data = deepcopy(sources)
    target = data[role] if index is None else data[role]["rows"][index]
    target.update(changes)
    try:
        inspect(manifest, data)
    except (ValueError, KeyError) as error:
        assert reason in str(error), (name, str(error))
    else:
        raise AssertionError(name)
    checks[name] = "REJECTED_AS_EXPECTED"


check("second_direct_same_conversion", "gateway", 1, {"origin": "DIRECT"}, "double direct attribution")
check("clock_mismatch", "witness", None, {"clock": "other"}, "clock mismatch")
check("fetch_timestamp_as_conversion", "gateway", 1, {"acq_ns": 51}, "fetch replaced acquisition")
check("decision_says_cache_is_direct", "decision", 1, {"input_origin": "DIRECT"}, "decision input mismatch")
check("unknown_response", "decision", 1, {"response": "absent"}, "absent")
check("decision_wrong_request", "decision", 1, {"request": "Q1"}, "unlinked decision")
check("reused_witness", "decision", 1, {"witness": "W1"}, "double decision attribution")
check("different_edge", "witness", 1, {"edge": "other"}, "witness edge mismatch")
check("different_tick", "witness", 1, {"t_ns": 53}, "witness edge mismatch")
check("insufficient_witness_coverage", "witness", 1, {"envelope_half_width_ns": 1},
      "witness envelope misses decision uncertainty")
check("same_instrument", "witness", None, {"device": "example-acquisition"}, "witness instrument reused")
check("different_point", "witness", 1, {"point": "other"}, "point or time")
check("cache_cannot_precede_publication", "gateway", 1, {"request_ns": 12}, "cache origin mismatch")

copy = deepcopy(sources)
copy["acquisition"]["rows"].append(dict(copy["acquisition"]["rows"][0], id="A1-alias"))
try:
    inspect(manifest, copy)
except ValueError as error:
    assert str(error) == "duplicate conversion"
else:
    raise AssertionError("duplicate conversion passed")
checks["duplicate_boot_sequence"] = "REJECTED_AS_EXPECTED"

copy = deepcopy(sources)
copy["witness"]["rows"][1].update(lower_uv=99, upper_uv=101)
row = inspect(manifest, copy)["rows"][1]
assert row["reference"] == "UNKNOWN" and row["low_alarm_disagrees_with_reference"] is None
checks["uncertain_reference"] = "UNKNOWN_AS_EXPECTED"
print(json.dumps({"scope": "SYNTHETIC", "controls": checks, "physical_test": "NOT_RUN",
                  "physical_cache_false_alarms": None}, indent=2))
