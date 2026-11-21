# Trace a voltage decision back to its acquisition

This offline observer follows the conversion that supplied a caller's voltage reading. A second conversion may be triggered by the same request while the gateway serves an older value from cache. The fixture and all expected results are synthetic.

## Run

From this directory in the repository, run the commands below with Python 3.11 or later. The observer uses the standard library and the sibling P05 collection module for strict JSON parsing and file identity checks. [P05 collection module](../pilot_r3/pilot_collect.py)

```sh
python -B observer.py SYNTHETIC
python -B verify.py
```

The first command reads five bounded JSON logs and their manifest. It prints a JSON result and returns 0 for a structurally linked trace or 2 for a rejected input. The second command runs 17 named controls and one additional file-integrity control. It compares four complete JSON outputs against the expected file, including the counterexample below and the refusal after one byte is appended to a temporary witness file. Its temporary copies are removed on exit. [Expected outputs](EXPECTED.json) · [Controls](controls.py)

## Two conversions with different roles

In the initial fixture, request Q1 triggers A1 at 11 ns. Both Q1 and Q2 receive its 80 µV value. The counterexample adds A2, declared for Q2 at 51 ns with a value of 121 µV. Q2 still receives 80 µV from A1. An independent witness log places the reference in the interval 118–122 µV at the decision marker. In this synthetic example the caller's low-voltage alarm disagrees with the reference.

For the second decision in the counterexample, the observer reports the following fields.

```json
{
  "request": "Q2",
  "consumed_conversion_id": "A1",
  "declared_conversion_ids_for_request": ["A2"],
  "consumed_response_uses_conversion_triggered_by_request": false
}
```

An empty list means that the supplied acquisition log contains no row declaring that trigger. Acquisition-log completeness is always `UNKNOWN`.

## Input and scope

The normalized inputs are a manifest and five files named `acquisition.json`, `publication.json`, `gateway.json`, `decision.json` and `witness.json`. The manifest records the file names, byte counts, SHA-256 digests, run, electrical point, clock domain and low-voltage threshold. Each file is limited to 128 KiB and each log to 256 rows. The example records the complete field names and units. [Synthetic input](SYNTHETIC/manifest.json)

The supported profile uses on-demand direct conversions, a common native clock in nanoseconds and a shared decision/witness edge. Acquisition identity includes boot and sequence. A cache hit references an older publication and preserves its conversion timestamp. Each decision links to the consumed response, caller rule and a unique reference edge on the same electrical point. The observer checks the declared instrument identities, timing order, marker uncertainties and reference voltage bounds. A reference interval that straddles the threshold produces `UNKNOWN`.

The controls include duplicate direct attribution, mismatched clocks, a fetch time substituted for acquisition time, a decision linked to the wrong request, a reused witness and insufficient reference time coverage. A hash binds file contents. Assessing clock provenance, calibration, actual instrument independence and the completeness of the underlying records requires evidence from the bench. `STRUCTURALLY_LINKED` describes the declared links. All runs report `physical_test: NOT_RUN` and leave physical cache false alarms unquantified.

The original code and synthetic fixtures are distributed under the included MIT license. [License](LICENSE)
