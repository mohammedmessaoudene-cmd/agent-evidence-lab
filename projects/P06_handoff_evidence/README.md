# P06: bounded mission evidence and provider authority

This kit is two local experiments, not a cross-SDK checkpoint migration or a universal handoff protocol. Python3.11+ stdlib is sufficient for the provider experiment; Node20+ is additionally required for the two-parser experiment.

```sh
python -B provider_boundary/run.py --out results/provider_fresh
python -B handoff/compare_parsers.py --out results/parsers_fresh
```

Use absent output directories. The provider matrix executes20 observations, including **four expected dangerous counterexamples** when the provider deliberately does not enforce its own fence atomically. A correctly signed receipt alone cannot make that provider enforce authority. Local HMAC fixture keys, SQLite audit effects and process/file RPC are laboratory mechanisms. No account, money, remote provider, private customer data or hostile federation is involved. PASS means the declared expected observation was observed; it does not make the unsafe profiles safe.

The parser comparison uses the R4 binary transport correction. All14 cases must match expected admission results and show equal SHA256/size at Python input, saved fixture and bytes actually read by Node, including parse rejection. The JSON dossier is an inert historical test fixture: file references and old receipt fields do not imply those files were transferred or the statements are current. A private Library identifier in its metadata was replaced with `SYNTHETIC_ARCHIVE_NOT_INCLUDED` before publication. All14 parser cases were rerun against this sanitized public fixture; its SHA256 is `1c7dfa1432f8809fa057fdb76d3d8ee367e70838eafbc59e18e5a0705c761e7b`, distinct from the historical unredacted fixture. Both parsers permissively accepting a document is not itself authority or safe execution.

No gain over a competent classical queue, human-effort saving or inter-SDK checkpoint portability is claimed. In a separate historical DBOS experiment, the workflow used portable_json but step outputs remained py_pickle. Neither DBOS nor AgentHandoffKit code is vendored in this kit. Original provider/parser/profile code: repository MIT. SOURCES.json identifies retained sources and the corrected binary-transport files.

## Targeted correction and new evidence

The source delta requires T05's expected unique effect, its request binding,
and `EFFECT_COMMIT < FENCE_COMMIT` for the new owner. It rejects malformed
fields consumed by the finite dossier profile. Provider and worker transport
uses explicit UTF-8 bytes and UTF-8 file writes. The provider's authority,
coordinator, capability profiles and UNKNOWN rules are unchanged. A DONE field
in an imported dossier remains data; it is neither proof of execution nor a
permission. The profile is not a universal schema.

Run the following from this project with a base Python 3.11+ and Node 20+.
Each output directory must be absent. The probes use isolated copies for the
T05 mutant and target this project's current source by default:

```sh
python -S -B review/check_t05_effect.py --mode classic --out results/t05_classic_mutant
python -S -B review/check_t05_effect.py --mode adapter --out results/t05_adapter_mutant
python -S -B review/check_t05_effect.py --mode classic --fault none --out results/t05_classic_control
python -S -B review/check_t05_effect.py --mode adapter --fault none --out results/t05_adapter_control
python -S -B review/check_parser_shapes.py --include-positive-control --out results/parser_shapes
python -S -B review/check_unicode_transport.py --phase after --out results/unicode_transport
```

The mutant's expected runner status is FAIL: the probe returns success only
when that failure and zero effects are observed. Controls require PASS and one
effect. This challenges the evaluator, not a claim that the original provider
loses real effects. Parser probes use actual Python/Node parsing on three new
malformed shapes and the unchanged public dossier as a positive control.

`evidence/hardening/` contains new Windows Python 3.11.9 receipts: two expected
red T05 baseline mutant runs, four corrected T05 runs, three baseline parser
observations, four corrected parser observations, and twelve corrected Unicode
transport observations. The Unicode matrix contains six ordinary completions,
two atomic lost-ack reconciliations, two opaque lost-ack refusals and two old
worker CLI transport checks. The opaque cases keep UNKNOWN/PENDING and exactly
one effect through restart. They do not silently retry an unresolved action.

The inherited `ASCII` label in the Unicode protocol means UTF-8 mode was
disabled; the new Windows receipts record the actual encoding as **cp1252**.
The other selected mode records UTF-8. No new Windows ASCII execution is
claimed. Each worker wrapper records its active encodings and `no_site`; it
does not reconfigure the target's streams or authorization behavior. It runs
the actual worker module and communicates via bytes. Synthetic fixture keys
and audit events are public laboratory inputs.

These targeted runs do not rerun the original 20-provider/14-parser matrices.
The old `evidence/verification_20261101.json` remains unchanged and applies to
the original source. Its Windows/Linux results are historical; new source
execution here is Windows only. Full final-source CI is a separate result.
Portable evidence copies replace local paths; raw receipts remain retained by
the author. `SOURCES.json` and `FILE_MANIFEST.json` identify the exact candidate
and probe bytes. Source identities establish consistency, not independent
attestation or remote adoption. No report-verifier implementation is duplicated
in this project; the repository's common verifier handles report consistency.

The T05 and parser probes retain the received review's `base_commit=da6e193...`
label. That inherited field does **not** identify the checkout executed by
these new receipts. The 17 original project files were compared byte for byte
against `fa7e46776cc5e0ea38ebe1bf11a78b23cdd13e49` before integration; corrected
source identities are the `source_sha256` fields and the source-change table in
`evidence/hardening/verification.json`. The Unicode runtime metadata separately
pins the actual seven source files, protocol and probe at execution time.
