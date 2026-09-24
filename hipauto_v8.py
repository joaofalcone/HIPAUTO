#!/usr/bin/env python3
"""HIPAUTO V8 — lista compacta, detalhes de porta e deduplicação de interfaces."""
from pathlib import Path
from urllib.parse import urlparse
import hipauto_v7 as v7

core=v7.core;BASE_DISCOVER=v7.v6.v5.discover

def discover():
    devices=BASE_DISCOVER();serial_vidpid={(d.get('vendor_id'),d.get('product_id')) for d in devices if d.get('port') and d.get('vendor_id')}
    # Interface HID do mesmo VID/PID não vira segundo periférico quando existe porta serial.
    devices=[d for d in devices if not (str(d.get('path','')).startswith('/dev/input/') and (d.get('vendor_id'),d.get('product_id')) in serial_vidpid)]
    cfg=core.config()
    for device in devices:
        port=device.get('port');category=device.get('category');settings=cfg['serial']|cfg.get(category,{}) if port else {}
        device['port_name']=Path(port).name if port else (device.get('path') or 'Não se aplica')
        device['port_details']={
            'device':port,
            'stable':(device.get('stable_ports') or [None])[0],
            'description':f"{device.get('name')} - {Path(port).name}" if port else device.get('name'),
            'baudrate':settings.get('baudrate'),
            'data_bits':settings.get('bytesize'),
            'stop_bits':settings.get('stopbits'),
            'parity':settings.get('parity'),
            'access':'OK' if device.get('status')=='ok' else ('NÃO OK' if device.get('status')=='error' else 'Não testado')
        }
    with core.REGISTRY_LOCK:core.REGISTRY.clear();core.REGISTRY.update({item['id']:item for item in devices})
    return devices

core.discover=discover
class Handler(v7.Handler):
    def translate_path(self,path):
        if urlparse(path).path=='/':path='/index-v8.html'
        return super().translate_path(path)
    def do_GET(self):
        if urlparse(self.path).path=='/api/health':return self.json({'ok':True,'version':'8.0','platform':'Ubuntu Desktop','testScope':'PC-interface; scale=real-weight'})
        return super().do_GET()
core.Handler=Handler
if __name__=='__main__':core.main()
