# HIPAUTO Desktop

Aplicativo local de diagnóstico de periféricos para PDV Ubuntu, sem servidor web e sem navegador.

## Baixar e executar

```bash
curl -fL https://raw.githubusercontent.com/joaofalcone/HIPAUTO/main/dist/HIPAUTO-Desktop -o /tmp/HIPAUTO-Desktop && chmod +x /tmp/HIPAUTO-Desktop && /tmp/HIPAUTO-Desktop
```

Compatível com Ubuntu Desktop 22.04 ou superior em computadores x86-64.

SHA-256 do executável:

```text
6368DF5BAE24ABE33D857DA8383E88F68E3C00476D5228CC6379DBD42611B420
```

## Relatório para suporte

```bash
/tmp/HIPAUTO-Desktop --report --test > hipauto-relatorio.json
```

## Desenvolvimento

- Código: pacote `hipauto/` (descoberta, protocolos, testes, interface) e entrada `hipauto_desktop.py`.
- Testes: `xvfb-run -a python3 -m unittest discover -s tests` (com `USB_IDS=caminho/usb.ids` confere a base contra a fonte oficial).
- Base de periféricos: `python3 tools/gerar_base_perifericos.py caminho/usb.ids` regenera `perifericos-br.json`.
- Build (Ubuntu 22.04 via Docker): `./build-desktop.sh`, que roda os testes e gera `dist/HIPAUTO-Desktop`.
