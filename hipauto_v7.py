#!/usr/bin/env python3
"""HIPAUTO V7 — balança exige leitura real de peso, inclusive zero."""
from __future__ import annotations
import os,re,select,termios,time
from pathlib import Path
from urllib.parse import urlparse
import hipauto_v6 as v6

core=v6.core

def parse_weight(raw,cfg):
    match=re.search(cfg['weight_regex'],raw)
    if not match:return None
    value=match.group(0).replace(',','.')
    try:number=float(value)
    except ValueError:return None
    shown=f'{number:g}'
    return f"{shown} {cfg.get('unit','kg')}"

def scale_weight_test(device):
    port=device.get('port');fd=None
    if not port or not Path(port).exists():return {'status':'error','detail':'NÃO OK: porta da balança não existe','test_scope':'weight-reading'}
    cfg=core.config();settings=cfg['serial']|cfg['scale']
    try:
        fd=os.open(port,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK);attrs=termios.tcgetattr(fd);attrs[0]=attrs[1]=attrs[3]=0;attrs[2]=termios.CREAD|termios.CLOCAL|{7:termios.CS7,8:termios.CS8}.get(int(settings.get('bytesize',8)),termios.CS8)
        parity=str(settings.get('parity','N')).upper()
        if parity!='N':attrs[2]|=termios.PARENB
        if parity=='O':attrs[2]|=termios.PARODD
        if int(settings.get('stopbits',1))==2:attrs[2]|=termios.CSTOPB
        speed=core.BAUD.get(int(settings.get('baudrate',9600)),termios.B9600);attrs[4]=attrs[5]=speed;termios.tcsetattr(fd,termios.TCSANOW,attrs);termios.tcflush(fd,termios.TCIOFLUSH)
        request=str(settings.get('request_hex','')).replace(' ','')
        if request:os.write(fd,bytes.fromhex(request))
        end=time.monotonic()+float(settings.get('timeout',1.2));data=bytearray()
        while time.monotonic()<end:
            ready,_,_=select.select([fd],[],[],min(.15,max(0,end-time.monotonic())))
            if ready:data.extend(os.read(fd,4096))
            elif data:break
        if not data:return {'status':'error','detail':'NÃO OK: porta abriu, mas nenhum peso foi recebido','test_scope':'weight-reading'}
        raw=data.decode('ascii',errors='replace').strip();weight=parse_weight(raw,settings)
        if weight is None:return {'status':'error','detail':'NÃO OK: balança respondeu, mas peso não pôde ser interpretado','raw':raw,'hex':data.hex(' '),'test_scope':'weight-reading'}
        return {'status':'ok','detail':'Peso real recebido da balança','weight':weight,'raw':raw,'hex':data.hex(' '),'test_scope':'weight-reading'}
    except PermissionError:return {'status':'error','detail':'NÃO OK: Ubuntu negou acesso à porta da balança','test_scope':'weight-reading'}
    except (OSError,ValueError) as exc:return {'status':'error','detail':f'NÃO OK: falha ao ler balança ({exc})','test_scope':'weight-reading'}
    finally:
        if fd is not None:os.close(fd)

def device_test(device):
    return scale_weight_test(device) if device.get('category')=='scale' else v6.link_test(device)

core.test_serial=lambda device:scale_weight_test(device) if device.get('category')=='scale' else v6.serial_link_test(device)
core.test_device=device_test

class Handler(v6.Handler):
    def do_GET(self):
        if urlparse(self.path).path=='/api/health':return self.json({'ok':True,'version':'7.0','platform':'Ubuntu Desktop','testScope':'PC-interface; scale=real-weight'})
        return super().do_GET()

core.Handler=Handler
if __name__=='__main__':core.main()
