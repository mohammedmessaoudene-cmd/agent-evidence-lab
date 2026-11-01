"""A real old-owner process held at a portable file gate before dispatch.

The two inputs confer exactly the same authority. An envelope cannot mint a
grant, alter a provider capability or transfer permission by declaration.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

from p06_boundary.common import Refusal, canonical, read_json, rpc


def atomic_json(path, value):
    tmp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    tmp.write_text(canonical(value)+'\n',encoding='utf-8')
    os.replace(tmp,path)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--mode',choices=['classic','adapter'],required=True)
    p.add_argument('--ready',type=Path,required=True)
    p.add_argument('--resume',type=Path,required=True)
    a=p.parse_args()
    value=read_json(a.input)
    if a.mode=='adapter':
        if set(value)!={'schema','request'} or value['schema']!='p06-r2-boundary-envelope/1':
            raise Refusal('ENVELOPE_SCHEMA')
        request=value['request']
    else:
        request=value
    atomic_json(a.ready,{'pid':os.getpid(),'ready_at':time.time(),'mode':a.mode})
    until=time.monotonic()+18
    while not a.resume.exists():
        if time.monotonic()>=until:raise Refusal('FIXTURE_GATE_TIMEOUT')
        time.sleep(.005)
    submitted=time.time()
    try:
        result=rpc(a.root/'provider.sqlite',a.root/'fixture.key',request)
        output={'ok':True,'response':result}
    except Refusal as exc:
        output={'ok':False,'error':exc.code,'detail':exc.detail}
    output.update(pid=os.getpid(),submitted_at=submitted,completed_at=time.time(),mode=a.mode)
    sys.stdout.buffer.write((canonical(output)+'\n').encode('utf-8'))
    sys.stdout.buffer.flush()


if __name__=='__main__':main()
