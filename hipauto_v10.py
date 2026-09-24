#!/usr/bin/env python3
"""HIPAUTO V10 — uma linha por impressora física conectada."""
import socket,time
from urllib.parse import urlparse
import hipauto_v9 as v9

core=v9.core;BASE_DISCOVER=v9.v8.discover

def printer_uris():
    _,output=core.run(['lpstat','-v']);result={}
    for line in output.splitlines():
        if line.startswith('device for ') and ': ' in line:
            name,uri=line[len('device for '):].split(': ',1);result[name]=uri
    return result

def network_online(uri):
    parsed=urlparse(uri);host=parsed.hostname
    if not host:return False
    port=parsed.port or {'ipp':631,'ipps':631,'http':80,'https':443,'socket':9100,'lpd':515}.get(parsed.scheme,9100)
    try:
        with socket.create_connection((host,port),timeout=.7):return True
    except OSError:return False

def merge_printers(devices):
    uris=printer_uris();physical=[d for d in devices if d['category']=='printer' and d['id'].startswith('usb:')];remove=set();result=[]
    for device in devices:
        if device['category']!='printer' or not device['id'].startswith('printer:'):continue
        queue=device['id'].split(':',1)[1];uri=uris.get(queue,'');device['printer_uri']=uri
        if uri.startswith('usb://'):
            uri_name=core.norm(uri)
            candidates=[p for p in physical if core.norm(p['name']) in uri_name or any(token in uri_name for token in core.norm(p['name']).split())]
            if not candidates and len(physical)==1:candidates=physical
            if candidates:
                match=candidates[0];remove.add(match['id'])
                for key in ('vendor_id','product_id','serial_number','driver','confidence','homologation','evidence'):
                    if match.get(key):device[key]=match[key]
                device['usb_path']=match.get('path');device['connection']='USB'
                device['port_name']=queue;device['port_details']['description']=f"{match['name']} - fila {queue}";device['port_details']['device']=match.get('path');device['port_details']['stable']=uri
        elif device['connection']=='Rede' and not network_online(uri):remove.add(device['id'])
    for device in devices:
        if device['id'] not in remove:result.append(device)
    return result

def discover():
    devices=merge_printers(BASE_DISCOVER())
    with core.REGISTRY_LOCK:core.REGISTRY.clear();core.REGISTRY.update({item['id']:item for item in devices})
    return devices

def report(run_tests=False):
    devices=discover();results={}
    if run_tests:
        for device in devices:
            try:results[device['id']]=core.test_device(device)
            except Exception as exc:results[device['id']]={'status':'error','detail':str(exc)}
            device.update(results[device['id']])
    env=v9.v8.v7.v6.v5.environment();return {'schemaVersion':3,'appVersion':'10.0','environment':env,'devices':devices,'recommendations':v9.v8.v7.v6.v5.recommendations(devices,env),'testResults':results}

class Handler(v9.Handler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/health':return self.json({'ok':True,'version':'10.0','platform':'Ubuntu Desktop','testScope':'PC-interface; scale=real-weight'})
        if path=='/api/devices':return self.json({'devices':discover(),'environment':v9.v8.v7.v6.v5.environment(),'scannedAt':int(time.time())})
        if path=='/api/report':return self.json(report(False))
        return super().do_GET()
    def do_POST(self):
        if urlparse(self.path).path=='/api/test-all':return self.json(report(True))
        return super().do_POST()
core.discover=discover;core.Handler=Handler
if __name__=='__main__':core.main()
