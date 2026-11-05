# R3: an omitted mandatory exception field is not JSON null

Both reader profiles previously accepted otherwise valid synthetic observations
whose required `exception` member was missing. The contract requires an exception
name or explicit null. The correction adds one presence guard to each reader;
the ledger, adapters, generator, inputs and contract are unchanged.

Run `python -S -B check_required_exception.py --out results/required-exception`
from this directory. Use a new output directory. Two native local adapter calls
anchor F04 and X1, then six single-key omissions and two explicit non-null
exception controls are derived. These ten related observations exercise one
mechanism, not ten independent business scenarios.

The Windows Python3.11.9 before/after summaries preserve the initial false greens:
six omissions accepted before, all six rejected after; both native positives stay
accepted and both explicit exceptions stay rejected. Source hashes bind each arm.
The received cloud review used Linux; this Windows run is a same-team local replay,
not independent human validation. No native historical exception was concealed.

Full corrected CLI verification additionally executed the eighteen adapter cases,
eight malformed-output probes and six M4 source variants. The historical malformed
checker requires `results/adapter1/report.json`: the first coordinator invocation
used a different directory and failed before any probe. Its already executed
eighteen-case report was copied byte-for-byte to that fixed path; then all eight
probes passed. The failed attempt remains in the private execution receipt.

Root Dot integrates this correction. The received review's attribution to offre1
was stale and is not adopted here. Existing contributor credits and licence
notices are preserved. This fixes a local evidence reader; it establishes neither
external effects, invoice authenticity, production durability, upstream acceptance,
protocol novelty nor an optimization advantage. Historical evidence is unchanged.
