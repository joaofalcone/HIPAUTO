#!/usr/bin/env python3
"""HIPAUTO V17 - fundo neutro; verde reservado para estados positivos."""
import sys
from urllib.parse import urlparse
import hipauto_v16 as v16

core=v16.core

class Handler(v16.Handler):
    def translate_path(self,path):
        if urlparse(path).path=='/':path='/index-v17.html'
        return super().translate_path(path)
    def do_GET(self):
        if urlparse(self.path).path=='/api/health':
            return self.json({'ok':True,'version':'17.0','platform':'Ubuntu Desktop','theme':'Neutral Glass','sidebar':False,'smakProbe':'isolated-read-only'})
        return super().do_GET()

core.Handler=Handler
if __name__=='__main__':
    if '--smak-probe' in sys.argv:v16.v15.v14.probe_smak_worker()
    else:core.main()
