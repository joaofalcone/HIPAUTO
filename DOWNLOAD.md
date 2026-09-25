# HIPAUTO Desktop

Aplicativo local de diagnóstico de periféricos para PDV Ubuntu, sem servidor web e sem navegador.

## Baixar e executar

```bash
curl -fL https://raw.githubusercontent.com/joaofalcone/HIPAUTO/main/dist/HIPAUTO-Desktop -o /tmp/HIPAUTO-Desktop && chmod +x /tmp/HIPAUTO-Desktop && /tmp/HIPAUTO-Desktop
```

Compatível com Ubuntu Desktop 22.04 ou superior em computadores x86-64.

SHA-256 do executável:

```text
48D6639C3FAD25DC7EBC0FF4A4E782A8AFB1F76911EC2740689E7F65E3274723
```

## Relatório para suporte

```bash
/tmp/HIPAUTO-Desktop --report --test > hipauto-relatorio.json
```

## Desenvolvimento

- Código: pacote `hipauto/` (descoberta, protocolos, testes, interface) e entrada `hipauto_desktop.py`.
- Testes: `xvfb-run -a python3 -m unittest discover -s tests`.
- Build (Ubuntu 22.04 via Docker): `./build-desktop.sh`, que roda os testes e gera `dist/HIPAUTO-Desktop`.
