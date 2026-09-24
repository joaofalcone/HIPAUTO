#!/usr/bin/env python3
"""HIPAUTO V11 — visão Kanban por tipo e detecção de monitores."""
import re,time
from pathlib import Path
from urllib.parse import urlparse
import hipauto_v10 as v10

core=v10.core;BASE_DISCOVER=v10.discover;BASE_TEST=core.test_device

def monitor_connection(connector):
    name=connector.upper()
    if 'HDMI' in name:return 'HDMI'
    if 'DP-' in name or 'DISPLAYPORT' in name:return 'DisplayPort'
    if 'VGA' in name:return 'VGA'
    if 'DVI' in name:return 'DVI'
    if 'EDP' in name:return 'eDP interno'
    return 'Vídeo'

def monitors():
    result=[];root=Path('/sys/class/drm')
    if not root.exists():return result
    connectors=[]
    for status in root.glob('card*-*/status'):
        if core.read(status)!='connected':continue
        connector=status.parent.name.split('-',1)[1] if '-' in status.parent.name else status.parent.name
        connectors.append((connector,status))
    for index,(connector,status) in enumerate(sorted(connectors),1):
        result.append({'id':f'monitor:{connector}','category':'monitor','name':f'Monitor {index}','connection':monitor_connection(connector),'port':None,'port_name':connector,'path':str(status),'vendor_id':None,'product_id':None,'serial_number':None,'driver':'drm','status':'detected','detail':f'Monitor conectado na saída {connector}','weight':None,'homologation':{'status':'unknown','label':'Modelo não identificado'},'stable_ports':[],'recommended_port':connector,'confidence':{'level':'high','label':'Alta','reason':'Conector DRM reportou estado conectado'},'evidence':[f'DRM {connector}: connected'],'port_details':{'device':str(status),'stable':None,'description':f'Saída de vídeo {connector}','baudrate':None,'data_bits':None,'stop_bits':None,'parity':None,'access':'Não testado'}})
    return result

def discover():
    devices=BASE_DISCOVER()+monitors()
    with core.REGISTRY_LOCK:core.REGISTRY.clear();core.REGISTRY.update({item['id']:item for item in devices})
    return devices

def test_device(device):
    if device.get('category')=='monitor':
        connected=core.read(device.get('path'))=='connected'
        return {'status':'ok' if connected else 'error','detail':'Comunicação com PC OK: monitor ativo no DRM' if connected else 'NÃO OK: saída de vídeo não está mais conectada','test_scope':'pc-interface'}
    return BASE_TEST(device)

core.test_device=test_device
def report(run_tests=False):
    devices=discover();results={}
    if run_tests:
        for device in devices:
            try:results[device['id']]=test_device(device)
            except Exception as exc:results[device['id']]={'status':'error','detail':str(exc)}
            device.update(results[device['id']])
    env=v10.v9.v8.v7.v6.v5.environment();return {'schemaVersion':4,'appVersion':'11.0','environment':env,'devices':devices,'recommendations':v10.v9.v8.v7.v6.v5.recommendations(devices,env),'testResults':results}

class Handler(v10.Handler):
    def translate_path(self,path):
        if urlparse(path).path=='/':path='/index-v11.html'
        return super().translate_path(path)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/health':return self.json({'ok':True,'version':'11.0','platform':'Ubuntu Desktop','testScope':'PC-interface; scale=real-weight'})
        if path=='/api/devices':return self.json({'devices':discover(),'environment':v10.v9.v8.v7.v6.v5.environment(),'scannedAt':int(time.time())})
        if path=='/api/report':return self.json(report(False))
        return super().do_GET()
    def do_POST(self):
        if urlparse(self.path).path=='/api/test-all':return self.json(report(True))
        return super().do_POST()
core.discover=discover;core.Handler=Handler
if __name__=='__main__':core.main()
