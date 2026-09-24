#!/usr/bin/env python3
"""HIPAUTO V9 — rotas usam inventário V8 com portas e deduplicação."""
import time
from urllib.parse import urlparse
import hipauto_v8 as v8

core=v8.core

def report(run_tests=False):
    devices=v8.discover();results={}
    if run_tests:
        for device in devices:
            try:results[device['id']]=core.test_device(device)
            except Exception as exc:results[device['id']]={'status':'error','detail':str(exc)}
            device.update(results[device['id']])
            if device.get('port_details'):device['port_details']['access']='OK' if device['status']=='ok' else 'NÃO OK'
    env=v8.v7.v6.v5.environment()
    return {'schemaVersion':2,'appVersion':'9.0','environment':env,'devices':devices,'recommendations':v8.v7.v6.v5.recommendations(devices,env),'testResults':results}

class Handler(v8.Handler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/health':return self.json({'ok':True,'version':'9.0','platform':'Ubuntu Desktop','testScope':'PC-interface; scale=real-weight'})
        if path=='/api/devices':return self.json({'devices':v8.discover(),'environment':v8.v7.v6.v5.environment(),'scannedAt':int(time.time())})
        if path=='/api/report':return self.json(report(False))
        return super().do_GET()
    def do_POST(self):
        if urlparse(self.path).path=='/api/test-all':return self.json(report(True))
        return super().do_POST()

core.discover=v8.discover;core.Handler=Handler
if __name__=='__main__':core.main()
