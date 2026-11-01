# P06: bounded mission evidence and provider authority

This kit is two local experiments, not a cross-SDK checkpoint migration or a universal handoff protocol. Python3.11+ stdlib is sufficient for the provider experiment; Node20+ is additionally required for the two-parser experiment.

```sh
python -B provider_boundary/run.py --out results/provider_fresh
python -B handoff/compare_parsers.py --out results/parsers_fresh
```

Use absent output directories. The provider matrix executes20 observations, including **four expected dangerous counterexamples** when the provider deliberately does not enforce its own fence atomically. A correctly signed receipt alone cannot make that provider enforce authority. Local HMAC fixture keys, SQLite audit effects and process/file RPC are laboratory mechanisms. No account, money, remote provider, private customer data or hostile federation is involved. PASS means the declared expected observation was observed; it does not make the unsafe profiles safe.

The parser comparison uses the R4 binary transport correction. All14 cases must match expected admission results and show equal SHA256/size at Python input, saved fixture and bytes actually read by Node, including parse rejection. The JSON dossier is an inert historical test fixture: file references and old receipt fields do not imply those files were transferred or the statements are current. A private Library identifier in its metadata was replaced with `SYNTHETIC_ARCHIVE_NOT_INCLUDED` before publication. All14 parser cases were rerun against this sanitized public fixture; its SHA256 is `1c7dfa1432f8809fa057fdb76d3d8ee367e70838eafbc59e18e5a0705c761e7b`, distinct from the historical unredacted fixture. Both parsers permissively accepting a document is not itself authority or safe execution.

No gain over a competent classical queue, human-effort saving or inter-SDK checkpoint portability is claimed. In a separate historical DBOS experiment, the workflow used portable_json but step outputs remained py_pickle. Neither DBOS nor AgentHandoffKit code is vendored in this kit. Original provider/parser/profile code: repository MIT. SOURCES.json identifies retained sources and the corrected binary-transport files.
