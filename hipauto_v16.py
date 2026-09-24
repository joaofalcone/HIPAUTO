#!/usr/bin/env python3
"""HIPAUTO V16 - layout amplo sem sidebar e verde luminoso."""
import sys
from urllib.parse import urlparse
import hipauto_v15 as v15

core=v15.core

class Handler(v15.Handler):
    def translate_path(self,path):
        if urlparse(path).path=='/':path='/index-v16.html'
        return super().translate_path(path)
    def do_GET(self):
        if urlparse(self.path).path=='/api/health':
            return self.json({'ok':True,'version':'16.0','platform':'Ubuntu Desktop','theme':'Light Green Glass','sidebar':False,'smakProbe':'isolated-read-only'})
        return super().do_GET()

core.Handler=Handler
if __name__=='__main__':
    if '--smak-probe' in sys.argv:v15.v14.probe_smak_worker()
    else:core.main()
