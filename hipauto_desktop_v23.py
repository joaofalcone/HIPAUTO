#!/usr/bin/env python3
"""HIPAUTO Desktop 23 - painel moderno de periféricos em cards."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import hipauto_v18 as engine


APP_VERSION = "23.0"
BG = "#f3f6f9"
SURFACE = "#ffffff"
INK = "#182b3a"
MUTED = "#667b8a"
BRAND = "#087f8c"
GREEN = "#18a875"
GREEN_SOFT = "#dff8ed"
RED = "#d94b55"
AMBER = "#d88916"
CATEGORIES = {"pinpad": "Pinpad", "scanner": "Scanner", "scale": "Balança",
              "printer": "Impressora", "keyboard": "Teclado", "biometric": "Biometria",
              "monitor": "Monitor", "unknown": "Outro"}
STATUS_LABELS = {"ok": "Ativo", "detected": "Ativo", "warning": "Atenção",
                 "error": "Falha", "testing": "Testando"}


def rounded_rect(canvas, x1, y1, x2, y2, radius=16, **kwargs):
    points = [x1+radius,y1, x2-radius,y1, x2,y1, x2,y1+radius, x2,y2-radius,
              x2,y2, x2-radius,y2, x1+radius,y2, x1,y2, x1,y2-radius,
              x1,y1+radius, x1,y1]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def draw_icon(canvas, category, color, x=34, y=43):
    """Draw small dependency-free vector icons that remain sharp at any scale."""
    opts = {"fill": "", "outline": color, "width": 2}
    if category == "scale":
        canvas.create_rectangle(x-14,y-12,x+14,y+12, **opts)
        canvas.create_arc(x-8,y-8,x+8,y+8, start=20, extent=140, style="arc", outline=color, width=2)
        canvas.create_line(x,y-1,x+5,y-6, fill=color, width=2)
    elif category == "printer":
        canvas.create_rectangle(x-12,y-16,x+12,y-5, **opts)
        canvas.create_rectangle(x-16,y-5,x+16,y+11, **opts)
        canvas.create_rectangle(x-10,y+5,x+10,y+17, fill=SURFACE, outline=color, width=2)
    elif category in {"pinpad", "keyboard"}:
        canvas.create_rectangle(x-14,y-17,x+14,y+17, **opts)
        canvas.create_rectangle(x-9,y-12,x+9,y-5, **opts)
        for row in range(3):
            for col in range(3): canvas.create_oval(x-8+col*8,y+row*7,x-5+col*8,y+3+row*7, fill=color, outline="")
    elif category == "monitor":
        canvas.create_rectangle(x-17,y-13,x+17,y+10, **opts)
        canvas.create_line(x,y+10,x,y+16,x-9,y+16,x+9,y+16, fill=color, width=2)
    elif category == "biometric":
        for inset in (0,5,10): canvas.create_arc(x-16+inset,y-18+inset,x+16-inset,y+18-inset,
                                                   start=25, extent=285, style="arc", outline=color, width=2)
    else:
        canvas.create_rectangle(x-16,y-10,x+10,y+10, **opts)
        canvas.create_line(x+10,y-5,x+17,y-5,x+17,y+5,x+10,y+5, fill=color, width=2)
        canvas.create_line(x-11,y-15,x-11,y-10,x+5,y-10,x+5,y-15, fill=color, width=2)


class HipautoDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HIPAUTO · Diagnóstico do PDV")
        self.geometry("1180x760"); self.minsize(920, 620); self.configure(bg=BG)
        self.devices, self.results, self.cards = [], {}, {}
        self.busy, self.pulse_on = False, False
        self.status_var = tk.StringVar(value="Preparando diagnóstico local…")
        self.summary_var = tk.StringVar(value="Nenhum periférico carregado")
        self._style(); self._build(); self.after(150, self.refresh_devices); self.after(650, self._pulse)

    def _style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names(): style.theme_use("clam")
        style.configure("Primary.TButton", background=BRAND, foreground="white",
                        font=("Segoe UI Semibold",10), padding=(16,10), borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#066b76"), ("disabled", "#9aadb5")])
        style.configure("Secondary.TButton", font=("Segoe UI",10), padding=(14,10))
        style.configure("Treeview", rowheight=38, font=("Segoe UI",10), background=SURFACE,
                        fieldbackground=SURFACE, borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold",10), padding=9,
                        background="#e7eef3", foreground=INK)

    def _build(self):
        header=tk.Frame(self,bg="#123044",padx=26,pady=17); header.pack(fill="x")
        logo=tk.Label(header,text="H",bg="#20b7aa",fg="white",font=("Segoe UI Semibold",20),width=3)
        logo.pack(side="left",padx=(0,14))
        heading=tk.Frame(header,bg="#123044"); heading.pack(side="left")
        tk.Label(heading,text="Diagnóstico do PDV",bg="#123044",fg="white",
                 font=("Segoe UI Semibold",19)).pack(anchor="w")
        tk.Label(heading,text="Visão local dos periféricos",bg="#123044",fg="#b9ceda",
                 font=("Segoe UI",9)).pack(anchor="w")
        tk.Label(header,text="●  OPERAÇÃO LOCAL",bg="#123044",fg="#6ee0b6",
                 font=("Segoe UI Semibold",9)).pack(side="right")

        top=tk.Frame(self,bg=BG,padx=26,pady=15); top.pack(fill="x")
        title=tk.Frame(top,bg=BG); title.pack(side="left")
        tk.Label(title,text="Periféricos",bg=BG,fg=INK,font=("Segoe UI Semibold",16)).pack(anchor="w")
        tk.Label(title,textvariable=self.status_var,bg=BG,fg=MUTED,font=("Segoe UI",9)).pack(anchor="w")
        self.test_all_button=ttk.Button(top,text="Testar todos",style="Primary.TButton",command=self.test_all)
        self.test_all_button.pack(side="right")
        self.refresh_button=ttk.Button(top,text="Atualizar",style="Secondary.TButton",command=self.refresh_devices)
        self.refresh_button.pack(side="right",padx=(0,9))

        self.card_area=tk.Frame(self,bg=BG,padx=22); self.card_area.pack(fill="x")
        self.card_area.bind("<Configure>", self._resize_cards)

        section=tk.Frame(self,bg=BG,padx=26,pady=(16,0)); section.pack(fill="both",expand=True)
        bar=tk.Frame(section,bg=SURFACE,padx=18,pady=11,highlightthickness=1,highlightbackground="#dce5eb")
        bar.pack(fill="x")
        tk.Label(bar,text="Resumo dos testes",bg=SURFACE,fg=INK,font=("Segoe UI Semibold",12)).pack(side="left")
        tk.Label(bar,textvariable=self.summary_var,bg=SURFACE,fg=MUTED,font=("Segoe UI",9)).pack(side="right")
        table_frame=tk.Frame(section,bg=SURFACE,highlightthickness=1,highlightbackground="#dce5eb")
        table_frame.pack(fill="both",expand=True)
        self.tree=ttk.Treeview(table_frame,columns=("device","port","test"),show="headings",selectmode="browse")
        for key,label,width in (("device","Periférico",370),("port","Porta",260),("test","Teste",390)):
            self.tree.heading(key,text=label); self.tree.column(key,width=width,minwidth=120,stretch=True)
        self.tree.tag_configure("ok",foreground="#087b56"); self.tree.tag_configure("error",foreground=RED)
        self.tree.tag_configure("warning",foreground="#a76300")
        scroll=ttk.Scrollbar(table_frame,orient="vertical",command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set); self.tree.pack(side="left",fill="both",expand=True)
        scroll.pack(side="right",fill="y")
        self.tree.bind("<Double-1>",lambda _e:self._open_selected())

        footer=tk.Frame(self,bg=BG,padx=26,pady=12); footer.pack(fill="x")
        tk.Label(footer,text=f" v{APP_VERSION} ",bg="#dfe7ec",fg="#41515c",
                 font=("Segoe UI Semibold",8),padx=5,pady=3).pack(side="left")
        tk.Label(footer,text="Selecione um card para ver todos os detalhes.",bg=BG,fg=MUTED,
                 font=("Segoe UI",9)).pack(side="left",padx=10)

    def _resize_cards(self,event):
        columns=max(2,min(4,event.width//265))
        if getattr(self,"_columns",None)==columns:return
        self._columns=columns; self._render_cards()

    def _render_cards(self):
        for child in self.card_area.winfo_children(): child.destroy()
        self.cards={}
        columns=getattr(self,"_columns",4)
        for col in range(columns): self.card_area.grid_columnconfigure(col,weight=1,uniform="cards")
        for index,device in enumerate(self.devices):
            result=self.results.get(device["id"],{}); status=result.get("status",device.get("status","detected"))
            active=status in {"ok","detected"}; border=GREEN if active else (RED if status=="error" else "#d5e0e7")
            card=tk.Canvas(self.card_area,height=126,bg=BG,highlightthickness=0,cursor="hand2")
            card.grid(row=index//columns,column=index%columns,sticky="nsew",padx=5,pady=5)
            shape=rounded_rect(card,3,3,252,121,17,fill=SURFACE,outline=border,width=2 if active else 1)
            card.create_oval(18,22,68,72,fill=GREEN_SOFT if active else "#edf2f5",outline="")
            draw_icon(card,device.get("category","unknown"),GREEN if active else MUTED,43,47)
            card.create_text(80,27,text=CATEGORIES.get(device.get("category"),"Outro").upper(),anchor="w",
                             fill=GREEN if active else MUTED,font=("Segoe UI Semibold",8))
            card.create_text(80,49,text=device.get("name") or "Equipamento sem nome",anchor="w",width=158,
                             fill=INK,font=("Segoe UI Semibold",11))
            card.create_text(20,94,text=device.get("port") or device.get("path") or "Sem porta",anchor="w",width=145,
                             fill=MUTED,font=("Segoe UI",9))
            card.create_text(232,94,text=STATUS_LABELS.get(status,str(status).title()),anchor="e",
                             fill=GREEN if active else (RED if status=="error" else AMBER),font=("Segoe UI Semibold",9))
            for item in (card,): item.bind("<Button-1>",lambda _e,d=device:self.open_details(d))
            self.cards[device["id"]]=(card,shape,active)

    def _pulse(self):
        self.pulse_on=not self.pulse_on
        for card,shape,active in list(self.cards.values()):
            if active and card.winfo_exists(): card.itemconfigure(shape,outline="#63e6b8" if self.pulse_on else GREEN,width=3 if self.pulse_on else 2)
        self.after(650,self._pulse)

    def _set_busy(self,value):
        self.busy=value
        for button in (self.refresh_button,self.test_all_button): button.state(["disabled" if value else "!disabled"])

    def _background(self,task,done):
        if self.busy:return
        self._set_busy(True)
        def worker():
            try: result,error=task(),None
            except Exception as exc: result,error=None,exc
            self.after(0,lambda:done(result,error))
        threading.Thread(target=worker,daemon=True).start()

    def refresh_devices(self):
        self.status_var.set("Procurando periféricos conectados…")
        def done(result,error):
            self._set_busy(False)
            if error: messagebox.showerror("Falha no diagnóstico",str(error),parent=self); return
            self.devices=result; known={d["id"] for d in result}
            self.results={k:v for k,v in self.results.items() if k in known}
            self._refresh_view(); self.status_var.set(time.strftime("Atualizado às %H:%M:%S"))
        self._background(engine.discover,done)

    def _refresh_view(self):
        self._render_cards()
        for item in self.tree.get_children(): self.tree.delete(item)
        for device in self.devices:
            result=self.results.get(device["id"],{}); status=result.get("status",device.get("status","detected"))
            detail=result.get("detail",device.get("detail","Aguardando teste"))
            if result.get("weight"): detail=f"{detail} · {result['weight']}"
            self.tree.insert("","end",iid=device["id"],values=(device.get("name") or CATEGORIES.get(device.get("category")),
                device.get("port") or device.get("path") or "—",f"{STATUS_LABELS.get(status,status.title())} · {detail}"),tags=(status,))
        active=sum((self.results.get(d["id"],{}).get("status",d.get("status")) in {"ok","detected"}) for d in self.devices)
        self.summary_var.set(f"{len(self.devices)} periférico(s) · {active} ativo(s)")

    def test_all(self):
        if not self.devices: messagebox.showinfo("Nenhum equipamento","Nenhum periférico foi encontrado.",parent=self); return
        self.status_var.set("Testando todos os periféricos…")
        def task():
            output={}
            for device in self.devices:
                try: output[device["id"]]=engine.test_device(device)
                except Exception as exc: output[device["id"]]={"status":"error","detail":str(exc)}
            return output
        def done(result,error):
            self._set_busy(False)
            if error: messagebox.showerror("Falha nos testes",str(error),parent=self); return
            self.results.update(result); self._refresh_view(); self.status_var.set("Testes concluídos")
        self._background(task,done)

    def _open_selected(self):
        selected=self.tree.selection()
        if selected:
            device=next((d for d in self.devices if d["id"]==selected[0]),None)
            if device:self.open_details(device)

    def open_details(self,device):
        modal=tk.Toplevel(self); modal.title("Detalhes do periférico"); modal.geometry("650x570")
        modal.minsize(560,480); modal.configure(bg=BG); modal.transient(self); modal.grab_set()
        head=tk.Frame(modal,bg="#123044",padx=22,pady=16); head.pack(fill="x")
        tk.Label(head,text=CATEGORIES.get(device.get("category"),"PERIFÉRICO").upper(),bg="#123044",fg="#6ee0b6",
                 font=("Segoe UI Semibold",8)).pack(anchor="w")
        tk.Label(head,text=device.get("name") or "Equipamento",bg="#123044",fg="white",
                 font=("Segoe UI Semibold",16)).pack(anchor="w")
        body=tk.Frame(modal,bg=SURFACE,padx=22,pady=16); body.pack(fill="both",expand=True,padx=18,pady=18)
        result=self.results.get(device["id"],{}); merged=dict(device); merged.update(result)
        hom=merged.get("homologation") or {}; conf=merged.get("confidence") or {}
        rows=[("Tipo",CATEGORIES.get(merged.get("category"),"Outro")),("Equipamento",merged.get("name")),
              ("Conexão",merged.get("connection")),("Porta",merged.get("port") or merged.get("path")),
              ("Estado",STATUS_LABELS.get(merged.get("status","detected"),merged.get("status","detected"))),
              ("Resultado",merged.get("detail")),("Peso",merged.get("weight")),
              ("Protocolo",merged.get("scale_protocol")),("Driver",merged.get("driver")),
              ("VID / PID"," / ".join(filter(None,[merged.get("vendor_id"),merged.get("product_id")]))),
              ("Homologação",hom.get("label") if isinstance(hom,dict) else hom),
              ("Confiança",conf.get("label") if isinstance(conf,dict) else conf)]
        for row,(label,value) in enumerate((item for item in rows if item[1])):
            bg="#f5f8fa" if row%2==0 else SURFACE
            left=tk.Label(body,text=label,bg=bg,fg=MUTED,font=("Segoe UI Semibold",9),anchor="w",padx=10,pady=8)
            right=tk.Label(body,text=str(value),bg=bg,fg=INK,font=("Segoe UI",9),anchor="w",justify="left",wraplength=390,padx=10,pady=8)
            left.grid(row=row,column=0,sticky="nsew"); right.grid(row=row,column=1,sticky="nsew")
        body.grid_columnconfigure(0,weight=1); body.grid_columnconfigure(1,weight=3)
        actions=tk.Frame(modal,bg=BG,padx=18,pady=(0,16)); actions.pack(fill="x")
        ttk.Button(actions,text="Fechar",style="Secondary.TButton",command=modal.destroy).pack(side="right")
        def test_one():
            modal.destroy(); self.status_var.set(f"Testando {device.get('name','equipamento')}…")
            def done(result,error):
                self._set_busy(False); self.results[device["id"]]={"status":"error","detail":str(error)} if error else result
                self._refresh_view(); self.open_details(device)
            self._background(lambda:engine.test_device(device),done)
        ttk.Button(actions,text="Testar comunicação",style="Primary.TButton",command=test_one).pack(side="right",padx=8)


if __name__ == "__main__": HipautoDesktop().mainloop()
