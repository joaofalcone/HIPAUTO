#!/usr/bin/env python3
"""HIPAUTO V13 — release visual revisada."""
from urllib.parse import urlparse
import hipauto_v12 as v12
core=v12.core
class Handler(v12.Handler):
    def translate_path(self,path):
        if urlparse(path).path=='/':path='/index-v13.html'
        return super().translate_path(path)
    def do_GET(self):
        if urlparse(self.path).path=='/api/health':return self.json({'ok':True,'version':'13.0','platform':'Ubuntu Desktop','theme':'Glass Operations'})
        return super().do_GET()
core.Handler=Handler
if __name__=='__main__':core.main()
