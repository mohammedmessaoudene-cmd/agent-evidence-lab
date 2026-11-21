# P02 preregistration for cmcp pull request #851

At the local freeze on 2026-11-21 at 05:26:12 UTC, the pull request was open. On head commit `01af41c8201dc30cd06b1b1957e8be8ec0d82985`, GitHub recorded an approval by `drk-ram` and a change request by `noah-ing`. GitHub also reported the aggregate review decision `CHANGES_REQUESTED`. [Pull request](https://github.com/agentrust-io/cmcp/pull/851) · [GitHub review records](https://api.github.com/repos/agentrust-io/cmcp/pulls/851/reviews)

## Observation rule

The qualifying event is an `APPROVED` or `CHANGES_REQUESTED` review by `noah-ing`, with an ID absent from the baseline, submitted strictly after the freeze. Its reviewed commit SHA must equal the PR head SHA at observation. A later review of a superseded head counts only in the history of that commit.

For each named reviewer, P02 and SQLite will receive the same public records. We predict agreement on the latest formal review ID and state for the observed head, or `NO_FORMAL_REVIEW_ON_THIS_SHA` when no such review exists. Comments and reviews by other accounts do not supply that reviewer's decision. If a frozen review disappears or is dismissed, the comparison requires reassessment. The PR's aggregate review decision is recorded separately.

Observation uses read-only queries. A qualifying result would demonstrate prospective reading of a public decision. Upstream adoption or influence would require evidence that a participant used P02.

The SHA-256 digest below identifies the exact bytes of the [frozen baseline](baseline.json). The freeze time records local capture. A public repository timestamp, when available, dates publication separately.

`b2d2a66534d9fc2a3abda1d6ef84d05a766bc419ea63f310dc72d2a21e186d9d`
