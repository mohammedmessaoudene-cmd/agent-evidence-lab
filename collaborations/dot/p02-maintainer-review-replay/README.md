# A maintainer changed a review on the same commit

On 26 August 2026, `imran-siddique` approved `agentrust-io/cmcp` PR #575 at `1cb9b20f` to release its checks. Seven minutes later the same maintainer requested changes on that commit. The contributor, `mohammedmessaoudene-cmd`, submitted `1100c492`. The maintainer checked both corrections and approved the new commit. [First approval](https://github.com/agentrust-io/cmcp/pull/575#pullrequestreview-5026793366) · [Request for changes](https://github.com/agentrust-io/cmcp/pull/575#pullrequestreview-5026824915) · [Approval after correction](https://github.com/agentrust-io/cmcp/pull/575#pullrequestreview-5033604459)

The maintainer merged the contributor’s cmcp change at 20:00 UTC. GitHub’s closure event on issue #571 identifies PR #575 as the `closer` and records the same merge commit, `717ce86ca265d9c8cb2f4c18005c76169cf96c61`. [Merged PR](https://github.com/agentrust-io/cmcp/pull/575) · [Issue closure](https://github.com/agentrust-io/cmcp/issues/571#event-30065517304)

## What the replay measures

The lab subsequently asked which formal decision that maintainer had most recently submitted on each exact commit at the time of each review. The six GitHub review submissions include three decisions and three comments. Each observed decision updates only its own commit. Before the maintainer approved the second commit, comments by its author left that commit without a formal maintainer decision. [Review metadata and closure fields](source.json)

The historical P02 Node peer issued three local research receipts. The P02 Python engine verified and replayed all three. Separately, a SQLite query reads the same six source rows, filters by reviewer, commit and submission time, and selects the latest formal decision. Both paths give the same state and review ID at all twelve lookups, including retrospective queries on the second commit before it existed. The comparison covers recorded review decisions. GitHub separately records the actual merge. Use of P02 by cmcp and an advantage over SQLite remain unverified. [Reference receipt](receipt.json) · [Replay and SQL query](replay.py)

## Run from the lab repository

Use a Git clone containing commit `f5af76e5935ef475c1269a447e28128bdb8e457f`, Python 3.11 with `cryptography` installed, and Node.js on `PATH`. From the repository root, run the following command. For a package stored elsewhere, pass `--repo` and the path to the clone. [Pinned P02 source and requirements](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/tree/f5af76e5935ef475c1269a447e28128bdb8e457f/projects/P02_corrections)

```sh
python -I -B collaborations/dot/p02-maintainer-review-replay/replay.py
```

The script reads four source files from the pinned Git tree, runs both P02 programs in a temporary directory and checks the complete result against `receipt.json`. The local receipt hashes identify signatures made with the lab’s deterministic test key. GitHub supplies the historical review identities and outcomes. [Source projection](source.json) · [Expected output](receipt.json)
