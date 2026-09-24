#!/usr/bin/env python3
"""HIPAUTO V5 — assistente de instalação e relatório técnico para Ubuntu Desktop."""
from __future__ import annotations
import json, os, platform, socket, subprocess, threading, time
from pathlib import Path
from urllib.parse import urlparse
import hipauto_release as release

core=release.core; BASE_DISCOVER=release.discover

def stable_ports():
    mapping={}
    for folder in (Path('/dev/serial/by-id'),Path('/dev/serial/by-path')):
        if not folder.exists():continue
        for link in folder.iterdir():
            try:mapping.setdefault(str(link.resolve()),[]).append(str(link))
            except OSError:pass
    return mapping

def usb_inventory():
    devices=[]; root=Path('/sys/bus/usb/devices')
    if not root.exists():return devices
    for path in root.iterdir():
        vid=core.read(path/'idVendor');pid=core.read(path/'idProduct')
        if not vid or not pid or core.read(path/'bDeviceClass')=='09':continue
        manufacturer=core.read(path/'manufacturer');product=core.read(path/'product');serial=core.read(path/'serial')
        name=' '.join(value for value in (manufacturer,product) if value).strip() or f'Dispositivo USB {vid}:{pid}'
        known=core.KNOWN.get(f'{vid}:{pid}'.lower());category=known[0] if known else core.classify(name)
        if category=='unknown':continue
        device=core.Device(id=f'usb:{path.name}',category=category,name=known[1] if known else name,connection='USB',vendor_id=vid,product_id=pid,path=str(path),serial_number=serial or None,driver=(path/'driver').resolve().name if (path/'driver').exists() else None,detail='Detectado diretamente no barramento USB')
        device.homologation=core.homologation(device);devices.append(core.asdict(device))
    return devices

def confidence(device):
    if device.get('vendor_id') and device.get('product_id') and device.get('serial_number'):return {'level':'high','label':'Alta','reason':'VID, PID e número de série confirmados'}
    if device.get('vendor_id') and device.get('product_id'):return {'level':'medium','label':'Média','reason':'VID e PID confirmados; equipamento não informou serial'}
    if device.get('port') or device.get('path'):return {'level':'medium','label':'Média','reason':'Interface Linux confirmada; modelo não possui identidade USB completa'}
    return {'level':'low','label':'Baixa','reason':'Identificação baseada somente no nome reportado'}

def enrich(device,ports):
    device['stable_ports']=ports.get(device.get('port'),[]);device['recommended_port']=(device['stable_ports'][0] if device['stable_ports'] else device.get('port'))
    device['confidence']=confidence(device);device['evidence']=[]
    if device.get('vendor_id'):device['evidence'].append(f"USB {device['vendor_id']}:{device['product_id']}")
    if device.get('port'):device['evidence'].append(f"Porta {device['port']}")
    if device['stable_ports']:device['evidence'].append(f"Porta estável {device['stable_ports'][0]}")
    if device.get('driver'):device['evidence'].append(f"Driver {device['driver']}")
    return device

def discover():
    ports=stable_ports();devices=[enrich(item,ports) for item in BASE_DISCOVER()];keys={(d.get('vendor_id'),d.get('product_id'),d.get('serial_number')) for d in devices if d.get('vendor_id')}
    for item in usb_inventory():
        key=(item.get('vendor_id'),item.get('product_id'),item.get('serial_number'))
        if key not in keys:devices.append(enrich(item,ports));keys.add(key)
    order={'pinpad':0,'scanner':1,'scale':2,'printer':3,'keyboard':4,'biometric':5,'touchscreen':6,'unknown':9};devices.sort(key=lambda d:(order.get(d['category'],9),d['name']))
    with core.REGISTRY_LOCK:core.REGISTRY.clear();core.REGISTRY.update({item['id']:item for item in devices})
    return devices

def environment():
    checks={name:core.run(['sh','-c',f'command -v {name}'])[0]==0 for name in ('udevadm','lpstat','lpinfo','lpadmin')}
    _,groups=core.run(['id','-nG']);_,cups=core.run(['systemctl','is-active','cups'])
    return {'hostname':socket.gethostname(),'os':platform.platform(),'kernel':platform.release(),'user':os.environ.get('USER',''),'groups':groups.split(),'cups':cups,'tools':checks,'generatedAt':int(time.time())}

def recommendations(devices,env):
    items=[]
    if 'dialout' not in env['groups']:items.append({'severity':'warning','text':'Usuário fora do grupo dialout; portas seriais podem negar acesso.'})
    if env['cups']!='active':items.append({'severity':'error','text':'Serviço CUPS não está ativo; impressoras não poderão ser configuradas.'})
    if any(not ok for ok in env['tools'].values()):items.append({'severity':'error','text':'Ubuntu não possui todas as ferramentas udev/CUPS necessárias.'})
    if not any(d['category']=='scale' for d in devices):items.append({'severity':'info','text':'Nenhuma balança detectada.'})
    if any(d['homologation']['status']=='not_homologated' for d in devices):items.append({'severity':'warning','text':'Há equipamento que não consta no catálogo Linux homologado.'})
    if not items:items.append({'severity':'ok','text':'Ambiente básico pronto para parametrização.'})
    return items

def full_report(run_tests=False):
    devices=discover();results={}
    if run_tests:
        for device in devices:
            try:results[device['id']]=core.test_device(device)
            except Exception as exc:results[device['id']]={'status':'error','detail':str(exc)}
            device.update(results[device['id']])
    env=environment();return {'schemaVersion':1,'appVersion':'5.0','environment':env,'devices':devices,'recommendations':recommendations(devices,env),'testResults':results}

class Handler(release.ReleaseHandler):
    def translate_path(self,path):
        if urlparse(path).path=='/':path='/index-v5.html'
        return super().translate_path(path)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/health':return self.json({'ok':True,'version':'5.0','platform':'Ubuntu Desktop'})
        if path=='/api/devices':return self.json({'devices':discover(),'environment':environment(),'scannedAt':int(time.time())})
        if path=='/api/report':return self.json(full_report(False))
        return super().do_GET()
    def do_POST(self):
        if urlparse(self.path).path=='/api/test-all':return self.json(full_report(True))
        return super().do_POST()

core.discover=discover;core.Handler=Handler
if __name__=='__main__':core.main()
