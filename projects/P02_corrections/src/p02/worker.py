"""Crash/restart worker. No sockets or external side effects."""
import argparse
from .engine import Engine

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("database")
    ap.add_argument("--mode", default="portable_graph")
    ap.add_argument("--owner")
    ap.add_argument("--crash-at", choices=["before_write", "during_transaction", "after_commit"])
    args = ap.parse_args()
    engine = Engine(args.database, mode=args.mode)
    if args.crash_at:
        engine.process_one(owner=args.owner, crash_at=args.crash_at)
    else:
        engine.drain(owner=args.owner)
    engine.close()

if __name__ == "__main__": main()
