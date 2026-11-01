"""Declared synthetic fixtures; no names here represent enrolled organizations."""
import random


def small():
    return {
        "leaves": {
            "A": {"issuer": "publisher-a", "revision": 0, "value": 10, "unit": "synthetic"},
            "B": {"issuer": "publisher-a", "revision": 0, "value": 20, "unit": "synthetic"},
            "C": {"issuer": "publisher-b", "revision": 0, "value": 30, "unit": "synthetic"},
            "U": {"issuer": "publisher-b", "revision": 0, "value": 40, "unit": "synthetic"}
        },
        "nodes": {
            "a": {"op": "identity", "inputs": ["A"]},
            "b": {"op": "identity", "inputs": ["B"]},
            "join": {"op": "mean", "inputs": ["a", "C"]},
            "unrelated": {"op": "identity", "inputs": ["U"]}
        },
        "decisions": {
            "D1": {"node": "a", "owner": "consumer-a", "threshold": 15, "policy": "ge-v1"},
            "D2": {"node": "b", "owner": "consumer-b", "threshold": 50, "policy": "ge-v1"},
            "D3": {"node": "join", "owner": "consumer-c", "threshold": 28, "policy": "ge-v1"},
            "D4": {"node": "unrelated", "owner": "consumer-c", "threshold": 35, "policy": "ge-v1"}
        },
        "graph_complete": True, "membership_closed": False, "cutoff": "synthetic-epoch-1",
        "data_kind": "SYNTHETIC"
    }


def random_graph(seed, leaves=12, transforms=24, decisions=16):
    r = random.Random(seed)
    f = {"leaves": {}, "nodes": {}, "decisions": {}, "graph_complete": True,
         "membership_closed": False, "cutoff": f"synthetic-seed-{seed}", "data_kind": "SYNTHETIC"}
    available = []
    for i in range(leaves):
        name = f"L{i:04d}"
        f["leaves"][name] = {"issuer": f"publisher-{i % 3}", "revision": 0,
                            "value": r.randint(-100, 100), "unit": "synthetic"}
        available.append(name)
    for i in range(transforms):
        name = f"N{i:04d}"
        ins = r.sample(available, r.randint(1, min(3, len(available))))
        f["nodes"][name] = {"op": r.choice(["mean", "min", "max", "sum"]), "inputs": ins}
        available.append(name)
    for i in range(decisions):
        f["decisions"][f"D{i:04d}"] = {"node": r.choice(available), "owner": f"consumer-{i % 3}",
                                      "threshold": r.randint(-60, 60), "policy": "ge-v1"}
    return f


def random_changes(fixture, seed):
    r = random.Random(seed ^ 0x5A17)
    keys = list(fixture["leaves"])
    r.shuffle(keys)
    # Three independent partitions, with two complete replacement revisions each.
    events = []
    for i, leaf in enumerate(keys[:3]):
        for rev in (1, 2):
            events.append({"id": f"s{seed}-l{i}-r{rev}", "issuer": fixture["leaves"][leaf]["issuer"],
                           "changes": [{"leaf": leaf, "revision": rev, "value": r.randint(-100, 100)}]})
    # At-least-once delivery and arbitrary order, identical for both arms.
    schedule = list(events) + [events[0], events[3]]
    r.shuffle(schedule)
    return events, schedule
