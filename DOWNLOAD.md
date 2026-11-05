# HIPAUTO Desktop

Aplicativo local de diagnóstico de periféricos para PDV Ubuntu, sem servidor web e sem navegador.

## Baixar e executar

```bash
curl -fL https://raw.githubusercontent.com/joaofalcone/HIPAUTO/main/dist/HIPAUTO-Desktop -o /tmp/HIPAUTO-Desktop && chmod +x /tmp/HIPAUTO-Desktop && /tmp/HIPAUTO-Desktop
```

Compatível com Ubuntu Desktop 22.04 ou superior em computadores x86-64.

SHA-256 do executável:

```text
B8721454C0622C2E7076479E41611D0EB2D2493BAA6674D66CBF05F2AA0A757F
```

## Relatório para suporte

```bash
/tmp/HIPAUTO-Desktop --report --test > hipauto-relatorio.json
```

## Desenvolvimento

- Código: pacote `hipauto/` (descoberta, protocolos, testes, interface) e entrada `hipauto_desktop.py`.
- Testes: `xvfb-run -a python3 -m unittest discover -s tests` (com `USB_IDS=caminho/usb.ids` confere a base contra a fonte oficial).
- Simulação de PDV completo (requer Docker e a imagem de build): `tests/e2e/run.sh`, que testa motor, interface e executável.
- Base de periféricos: `python3 tools/gerar_base_perifericos.py caminho/usb.ids` regenera `perifericos-br.json`.
- Build (Ubuntu 22.04 via Docker): `./build-desktop.sh`, que roda os testes e gera `dist/HIPAUTO-Desktop`.
