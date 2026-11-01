"""Classical durable worker and its small, explicitly versioned envelope adapter."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from .common import Refusal, canonical, read_json, rpc
from .contract import envelope, import_envelope, normalize_manifest
from .coordinator import Coordinator


def run(root,subject="A",mode="classic",crash=None,partition=False,lose_ack=False,lease=30,pause_file=None,input_file=None):
    root=Path(root)
    manifest=read_json(root/"manifest.json")
    if mode=="adapter":
        bundle=read_json(input_file) if input_file else envelope(manifest)
        manifest=import_envelope(bundle)
        (root/f"envelope-{subject}.json").write_text(canonical(bundle)+"\n")
    elif input_file:
        manifest=read_json(input_file)
    else:
        manifest=normalize_manifest(manifest)
    coord=Coordinator(root/"coordinator.sqlite",root/"fixture.key")
    provider=root/"provider.sqlite";key=root/"fixture.key"
    caps=rpc(provider,key,{"op":"capabilities"})["features"]
    if not caps["fencing"]:raise Refusal("FENCING_UNSUPPORTED")
    claim=coord.acquire(manifest,subject,lease)
    mission,epoch=claim["mission"],claim["epoch"]
    reply=rpc(provider,key,{"op":"fence","mission":mission,"grant":claim["grant"]},partition=partition)
    coord.activate(mission,subject,epoch,reply["fence_ack"])
    snapshot=coord.snapshot(mission)
    for ob in snapshot["obligations"]:
        if ob["status"]=="DONE":continue
        req=coord.prepare(mission,ob["id"],subject,epoch)
        if crash=="after_intent":os._exit(71)
        if pause_file:
            p=Path(pause_file)
            p.write_text(canonical({"pid":os.getpid(),"epoch":epoch,"request":req})+"\n")
            until=time.monotonic()+15
            while not Path(str(p)+".resume").exists():
                if time.monotonic()>until:raise Refusal("TEST_BARRIER_TIMEOUT")
                time.sleep(.005)
            pause_file=None
        if req["prior"]=="INTENT":
            if caps["lookup"]:
                found=rpc(provider,key,{"op":"lookup","mission":mission,"key":req["key"],"grant":req["lookup_grant"]})
                if found["found"]:
                    coord.acknowledge(mission,ob["id"],subject,epoch,found["receipt"])
                    continue
                # A late old request may still exist: fenced by completed barrier.
            elif not caps["idempotency"]:
                coord.mark_unknown(mission,ob["id"],subject,epoch)
                raise Refusal("UNRESOLVED_OUTCOME")
        try:
            outcome=rpc(provider,key,req,partition=partition,lose_ack=lose_ack)
        except Refusal as exc:
            if exc.code=="ACK_LOST" and not caps["lookup"] and not caps["idempotency"]:
                coord.mark_unknown(mission,ob["id"],subject,epoch)
            raise
        if crash=="after_effect":os._exit(72)
        coord.acknowledge(mission,ob["id"],subject,epoch,outcome["receipt"])
    return {"ok":True,"status":"COMPLETE","mission":mission,"subject":subject,"epoch":epoch,"pid":os.getpid(),"mode":mode}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("root");parser.add_argument("--subject",default="A");parser.add_argument("--mode",choices=["classic","adapter"],default="classic")
    parser.add_argument("--crash",choices=["after_intent","after_effect"]);parser.add_argument("--partition",action="store_true");parser.add_argument("--lose-ack",action="store_true")
    parser.add_argument("--lease",type=float,default=30);parser.add_argument("--pause-file");parser.add_argument("--input-file")
    args=vars(parser.parse_args());root=args.pop("root")
    try:result=run(root,**args)
    except Refusal as exc:result={"ok":False,"status":"BLOCKED","error":exc.code,"detail":exc.detail,"pid":os.getpid()}
    print(canonical(result),flush=True)
    if not result["ok"]:sys.exit(2)


if __name__=="__main__":main()
