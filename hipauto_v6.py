#!/usr/bin/env python3
"""HIPAUTO V6 — teste de comunicação entre periférico e Ubuntu, sem teste funcional."""
from __future__ import annotations
import os, re, select, termios, time
from pathlib import Path
from urllib.parse import urlparse
import hipauto_v5 as v5

core=v5.core

def serial_link_test(device):
    port=device.get('port');fd=None
    if not port or not Path(port).exists():return {'status':'error','detail':'NÃO OK: porta não existe no Ubuntu','test_scope':'pc-interface'}
    try:
        fd=os.open(port,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
        termios.tcgetattr(fd)
        result={'status':'ok','detail':'Comunicação com PC OK: porta serial abriu e respondeu ao sistema','test_scope':'pc-interface'}
        # Balança pode transmitir continuamente. Peso é informação adicional, não requisito do OK.
        if device.get('category')=='scale':
            ready,_,_=select.select([fd],[],[],0.6)
            if ready:
                raw=os.read(fd,4096).decode('ascii',errors='replace').strip();cfg=core.config();match=re.search(cfg['scale']['weight_regex'],raw)
                if match:result.update(weight=f"{match.group(0).replace(',','.')} {cfg['scale']['unit']}",raw=raw,detail='Comunicação com PC OK; peso recebido passivamente')
        return result
    except PermissionError:return {'status':'error','detail':'NÃO OK: Ubuntu detectou a porta, mas negou acesso; falta grupo dialout','test_scope':'pc-interface'}
    except OSError as exc:return {'status':'error','detail':f'NÃO OK: Ubuntu não conseguiu abrir a porta ({exc})','test_scope':'pc-interface'}
    finally:
        if fd is not None:os.close(fd)

def printer_link_test(device):
    queue=device.get('path');code,state=core.run(['lpstat','-p',queue])
    if code:return {'status':'error','detail':'NÃO OK: fila não está acessível no CUPS','test_scope':'pc-interface'}
    _,uri_text=core.run(['lpstat','-v',queue]);match=re.search(r':\s+(.+)$',uri_text);uri=match.group(1) if match else ''
    if uri.startswith('usb://'):
        _,available=core.run(['lpinfo','-v'])
        if uri not in available:return {'status':'error','detail':'NÃO OK: fila existe, mas impressora USB não está conectada','test_scope':'pc-interface'}
    if 'disabled' in state.lower():return {'status':'warning','detail':'CUPS reconhece impressora, mas fila está desabilitada','test_scope':'pc-interface'}
    return {'status':'ok','detail':'Comunicação com PC OK: dispositivo e fila CUPS estão disponíveis','test_scope':'pc-interface'}

def input_link_test(device):
    path=device.get('path')
    if not path or not Path(path).exists():return {'status':'error','detail':'NÃO OK: interface de entrada desapareceu','test_scope':'pc-interface'}
    fd=None
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK)
        return {'status':'ok','detail':'Comunicação com PC OK: interface de entrada abriu no Ubuntu','test_scope':'pc-interface'}
    except PermissionError:return {'status':'error','detail':'NÃO OK: detectado, mas Ubuntu negou acesso à interface','test_scope':'pc-interface'}
    except OSError as exc:return {'status':'error','detail':f'NÃO OK: falha ao abrir interface ({exc})','test_scope':'pc-interface'}
    finally:
        if fd is not None:os.close(fd)

def usb_link_test(device):
    path=Path(device.get('path') or '')
    if not path.exists():return {'status':'error','detail':'NÃO OK: dispositivo saiu do barramento USB','test_scope':'pc-interface'}
    authorized=core.read(path/'authorized')
    if authorized and authorized!='1':return {'status':'error','detail':'NÃO OK: dispositivo USB não autorizado pelo Ubuntu','test_scope':'pc-interface'}
    return {'status':'ok','detail':'Comunicação com PC OK: dispositivo ativo no barramento USB','test_scope':'pc-interface'}

def link_test(device):
    if device.get('port'):return serial_link_test(device)
    if device.get('category')=='printer':return printer_link_test(device)
    if str(device.get('path','')).startswith('/dev/input/'):return input_link_test(device)
    if str(device.get('path','')).startswith('/sys/bus/usb/'):return usb_link_test(device)
    return {'status':'warning','detail':'Detectado pelo Ubuntu; interface não possui teste de abertura','test_scope':'pc-interface'}

core.test_serial=serial_link_test;core.test_device=link_test

class Handler(v5.Handler):
    def do_GET(self):
        if urlparse(self.path).path=='/api/health':return self.json({'ok':True,'version':'6.0','platform':'Ubuntu Desktop','testScope':'PC-interface'})
        return super().do_GET()

core.Handler=Handler
if __name__=='__main__':core.main()
