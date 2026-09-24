#!/usr/bin/env python3
"""HIPAUTO V4 — diagnóstico consolidado para Ubuntu Desktop."""
from __future__ import annotations
import argparse, json, os, re, select, subprocess, sys, termios, threading, time, unicodedata, webbrowser
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent)); WEB=ROOT/"web"
CATALOG=json.loads((ROOT/"homologados-linux.json").read_text(encoding="utf-8"))["devices"]
USER_CONFIG=Path.home()/".config/hipauto/config.json"; BUNDLED_CONFIG=ROOT/"config.json"
REGISTRY={}; REGISTRY_LOCK=threading.Lock(); CUPS_LOCK=threading.Lock()
KNOWN={"05f9:4005":("scanner","Scanner fixo PSC/Datalogic"),"1753:c902":("pinpad","Pinpad Gertec PPC930")}

@dataclass
class Device:
    id:str; category:str; name:str; connection:str; port:str|None=None; vendor_id:str|None=None
    product_id:str|None=None; driver:str|None=None; path:str|None=None; serial_number:str|None=None
    status:str="detected"; detail:str="Aguardando teste"; weight:str|None=None; homologation:dict|None=None

def run(cmd,timeout=5):
    try:
        env=os.environ.copy(); env["LC_ALL"]="C"
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,check=False,env=env)
        return p.returncode,(p.stdout or p.stderr).strip()
    except (OSError,subprocess.TimeoutExpired) as exc:return 1,str(exc)

def read(path):
    try:return Path(path).read_text(errors="replace").strip()
    except OSError:return ""

def config():
    result={"serial":{"baudrate":9600,"timeout":1.2,"bytesize":8,"parity":"N","stopbits":1},"scale":{"request_hex":"05","weight_regex":r"[-+]?\d+(?:[.,]\d+)?","unit":"kg"},"pinpad":{"request_hex":"05"},"scanner":{"request_hex":""},"biometric":{"request_hex":""},"aliases":{}}
    for path in (BUNDLED_CONFIG,USER_CONFIG):
        try:
            supplied=json.loads(path.read_text(encoding="utf-8"))
            for key,value in supplied.items():
                if isinstance(value,dict) and isinstance(result.get(key),dict):result[key].update(value)
                else:result[key]=value
        except (OSError,json.JSONDecodeError):pass
    return result

def norm(value):return re.sub(r"[^a-z0-9]+","",unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode().lower())
def classify(name):
    text=norm(name)
    rules=[("scale",("scale","balanca","toledo","filizola","urano","prix")),("pinpad",("pinpad","ingenico","gertec","verifone")),("biometric",("biometric","fingerprint","ud4500","idbio")),("printer",("printer","epson","bematech","sweda","elgin","thermal")),("scanner",("scanner","barcode","datalogic","honeywell","metrologic","symbol")),("touchscreen",("touchscreen","touchscreen")),("keyboard",("keyboard","teclado"))]
    return next((category for category,words in rules if any(word in text for word in words)),"unknown")

def props(path):
    code,out=run(["udevadm","info","--query=property","--name",path])
    return {} if code else dict(line.split("=",1) for line in out.splitlines() if "=" in line)

def real_uarts():
    active=set()
    for line in read("/proc/tty/driver/serial").splitlines():
        match=re.match(r"(\d+):\s+uart:(\S+)",line)
        if match and match.group(2).lower()!="unknown":active.add(f"ttyS{match.group(1)}")
    return active

def serial_devices(cfg):
    result=[]; real=real_uarts(); dev=Path("/dev")
    if not dev.exists():return result
    for node in sorted(dev.iterdir()):
        if not re.match(r"^tty(?:ACM|USB|S)\d+$",node.name) or node.name.startswith("ttyS") and node.name not in real:continue
        p=props(str(node)); vid=p.get("ID_VENDOR_ID"); pid=p.get("ID_MODEL_ID"); key=f"{vid}:{pid}".lower(); known=KNOWN.get(key)
        label=known[1] if known else f"{p.get('ID_VENDOR_FROM_DATABASE') or p.get('ID_VENDOR','')} {p.get('ID_MODEL_FROM_DATABASE') or p.get('ID_MODEL','Porta serial')}".strip().replace("_"," ")
        category=cfg["aliases"].get(str(node)) or cfg["aliases"].get(node.name) or (known[0] if known else classify(label))
        result.append(Device(f"serial:{node.name}",category,label,"USB" if node.name.startswith(("ttyUSB","ttyACM")) else "Serial",str(node),vid,pid,p.get("ID_USB_DRIVER"),str(node),p.get("ID_SERIAL_SHORT")))
    return result

def input_devices():
    result=[]
    for index,block in enumerate(read("/proc/bus/input/devices").split("\n\n")):
        name_m=re.search(r'N: Name="([^"]+)"',block); handlers_m=re.search(r"H: Handlers=(.+)",block)
        if not name_m or not handlers_m:continue
        name=name_m.group(1); handlers=handlers_m.group(1).split()
        if any(value in name.lower() for value in ("power button","sleep button","video bus")):continue
        identity=re.search(r"I: Bus=([0-9a-fA-F]+) Vendor=([0-9a-fA-F]+) Product=([0-9a-fA-F]+)",block)
        bus,vid,pid=identity.groups() if identity else ("",None,None); known=KNOWN.get(f"{vid}:{pid}".lower()); category=known[0] if known else classify(name)
        if category=="unknown" and "kbd" in handlers:category="keyboard"
        if category not in {"keyboard","scanner","touchscreen","biometric"}:continue
        event=next((item for item in handlers if item.startswith("event")),None)
        result.append(Device(f"input:{event or index}",category,known[1] if known else name,"PS/2" if bus.lower() in {"0011","0005"} or "i8042" in block.lower() else "USB",path=f"/dev/input/{event}" if event else None,vendor_id=vid,product_id=pid,detail="Dispositivo de entrada detectado"))
    return result

def cups_queues():
    _,uris=run(["lpstat","-v"]); uri_by_name={m.group(1):m.group(2) for line in uris.splitlines() if (m:=re.match(r"device for (\S+):\s+(.+)",line))}
    code,states=run(["lpstat","-p"]); result=[]
    if code:return result
    for line in states.splitlines():
        match=re.match(r"printer\s+(\S+)\s+(.+)",line)
        if not match:continue
        name,state=match.groups(); uri=uri_by_name.get(name,name)
        result.append(Device(f"printer:{name}","printer",name,"USB" if uri.startswith("usb://") else "Rede",path=name,status="error" if "disabled" in state.lower() else "ok",detail=state))
    return result

def setup_usb_printers():
    with CUPS_LOCK:
        _,configured=run(["lpstat","-v"]); configured_uris={m.group(1) for line in configured.splitlines() if (m:=re.search(r":\s+(usb://.+)$",line))}
        code,available=run(["lpinfo","-v"])
        if code:return
        for line in available.splitlines():
            parts=line.split(maxsplit=1)
            if len(parts)!=2 or parts[0]!="direct" or not parts[1].startswith("usb://") or parts[1] in configured_uris:continue
            uri=parts[1]; model=uri.split("?",1)[0].rstrip("/").rsplit("/",1)[-1]; queue=re.sub(r"[^A-Za-z0-9_-]","_",f"AUTO_{model}")[:100]
            status,_=run(["lpadmin","-p",queue,"-E","-v",uri,"-m","raw"],8)
            if status==0:run(["lpoptions","-d",queue])

def homologation(device):
    usb=f"{device.vendor_id}:{device.product_id}".lower(); name=norm(device.name)
    candidates=sorted((item for item in CATALOG if item["category"]==device.category),key=lambda item:len(norm(item["model"])),reverse=True)
    for item in candidates:
        ids=[value.lower() for value in item.get("usbIds",[])]
        model=norm(item["model"]); maker=norm(item["manufacturer"])
        if usb in ids or model and model in name and (not maker or maker in name):return {"status":"homologated","label":"Homologado Linux","manufacturer":item["manufacturer"],"model":item["model"],"notes":item.get("notes")}
    return {"status":"not_homologated","label":"Não consta na lista Linux"} if device.category!="unknown" else {"status":"unknown","label":"Homologação não aplicável"}

def discover():
    setup_usb_printers(); found=serial_devices(config())+input_devices()+cups_queues(); unique={}; interfaces={}
    for device in found:
        key=f"{device.vendor_id}:{device.product_id}:{device.serial_number or ''}" if device.vendor_id and device.product_id else ""
        if key and key in interfaces:
            current=unique[interfaces[key]]
            if device.port and not current.port:del unique[current.id];unique[device.id]=device;interfaces[key]=device.id
            continue
        device.homologation=homologation(device);unique[device.id]=device
        if key:interfaces[key]=device.id
    data=[asdict(item) for item in unique.values()]
    with REGISTRY_LOCK:REGISTRY.clear();REGISTRY.update({item["id"]:item for item in data})
    return data

BAUD={1200:termios.B1200,2400:termios.B2400,4800:termios.B4800,9600:termios.B9600,19200:termios.B19200,38400:termios.B38400,57600:termios.B57600,115200:termios.B115200}
def test_serial(device):
    cfg=config(); settings=cfg["serial"]|cfg.get(device["category"],{}); port=device["port"]; fd=None
    try:
        fd=os.open(port,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK); attrs=termios.tcgetattr(fd); attrs[0]=attrs[1]=attrs[3]=0; attrs[2]=termios.CREAD|termios.CLOCAL|{7:termios.CS7,8:termios.CS8}.get(int(settings.get("bytesize",8)),termios.CS8)
        if settings.get("parity","N").upper()!="N":attrs[2]|=termios.PARENB
        if settings.get("parity","N").upper()=="O":attrs[2]|=termios.PARODD
        if int(settings.get("stopbits",1))==2:attrs[2]|=termios.CSTOPB
        speed=BAUD.get(int(settings.get("baudrate",9600)),termios.B9600);attrs[4]=attrs[5]=speed;termios.tcsetattr(fd,termios.TCSANOW,attrs);termios.tcflush(fd,termios.TCIOFLUSH)
        request=str(settings.get("request_hex","")).replace(" ","");
        if request:os.write(fd,bytes.fromhex(request))
        timeout=float(settings.get("timeout",1.2));end=time.monotonic()+timeout;data=bytearray()
        while time.monotonic()<end:
            ready,_,_=select.select([fd],[],[],min(.15,max(0,end-time.monotonic())))
            if ready:data.extend(os.read(fd,4096))
            elif data:break
        if not data:return {"status":"warning","detail":"Porta abriu; protocolo não respondeu"}
        raw=data.decode("ascii",errors="replace").strip();result={"status":"ok","detail":f"Resposta recebida ({len(data)} bytes)","raw":raw,"hex":data.hex(" ")}
        if device["category"]=="scale":
            match=re.search(cfg["scale"]["weight_regex"],raw)
            if match:result.update(weight=f"{match.group(0).replace(',','.')} {cfg['scale']['unit']}",detail="Peso recebido da balança")
        return result
    except PermissionError:return {"status":"error","detail":"Sem permissão na porta; usuário precisa do grupo dialout"}
    except (OSError,ValueError) as exc:return {"status":"error","detail":f"Falha de comunicação: {exc}"}
    finally:
        if fd is not None:os.close(fd)

def test_device(device):
    if device.get("port"):return test_serial(device)
    if device["category"]=="printer":
        code,out=run(["lpstat","-p",device["path"]]);return {"status":"ok" if code==0 and "disabled" not in out.lower() else "error","detail":out or "Impressora não respondeu pelo CUPS"}
    path=device.get("path")
    return {"status":"ok" if path and os.access(path,os.R_OK) else "warning","detail":"Dispositivo acessível" if path and os.access(path,os.R_OK) else "Detectado; sem permissão de leitura"}

class Handler(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        relative=unquote(urlparse(path).path).lstrip("/") or "index.html"; target=(WEB/relative).resolve()
        return str(target if target==WEB.resolve() or WEB.resolve() in target.parents else WEB/"__not_found__")
    def end_headers(self):
        self.send_header("X-Content-Type-Options","nosniff");self.send_header("X-Frame-Options","DENY");self.send_header("Referrer-Policy","no-referrer");super().end_headers()
    def json(self,payload,status=200):
        data=json.dumps(payload,ensure_ascii=False).encode();self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(data)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(data)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/api/health":self.json({"ok":True,"version":"4.0","platform":"Ubuntu"})
        elif path=="/api/devices":self.json({"devices":discover(),"scannedAt":int(time.time())})
        else:super().do_GET()
    def do_POST(self):
        if urlparse(self.path).path!="/api/test":return self.json({"error":"Rota não encontrada"},HTTPStatus.NOT_FOUND)
        try:
            length=int(self.headers.get("Content-Length","0"))
            if length>4096:raise ValueError("Requisição muito grande")
            device_id=json.loads(self.rfile.read(length) or b"{}").get("id")
            with REGISTRY_LOCK:device=REGISTRY.get(device_id)
            if not device:return self.json({"status":"error","detail":"Dispositivo não encontrado; atualize a lista"},HTTPStatus.NOT_FOUND)
            self.json(test_device(device))
        except (ValueError,json.JSONDecodeError) as exc:self.json({"status":"error","detail":str(exc)},HTTPStatus.BAD_REQUEST)
    def log_message(self,fmt,*args):print(f"[{self.log_date_time_string()}] {fmt%args}")

def open_browser(url):
    try:webbrowser.open(url,new=1)
    except Exception:pass
def main():
    parser=argparse.ArgumentParser(description="HIPAUTO V4 para Ubuntu Desktop");parser.add_argument("--host",default="127.0.0.1");parser.add_argument("--port",type=int,default=8787);parser.add_argument("--no-browser",action="store_true");args=parser.parse_args();url=f"http://127.0.0.1:{args.port}"
    try:server=ThreadingHTTPServer((args.host,args.port),Handler)
    except OSError as exc:raise SystemExit(f"Não foi possível iniciar na porta {args.port}: {exc}")
    if not args.no_browser and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):threading.Timer(1,open_browser,args=(url,)).start()
    print(f"HIPAUTO V4 disponível em {url}")
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
if __name__=="__main__":main()
