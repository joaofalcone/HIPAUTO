# Histórico de versões

## 28.0

Identificação das portas seriais "Outro" e refinamento visual.

**Identificação**
- As portas `ttyS` são identificadas pelo `/sys`, sem precisar abrir a porta:
  - COM da placa-mãe (ex.: "Porta COM1 (placa-mãe)");
  - placa serial PCI, com o fabricante (WCH, MosChip, Oxford e outros);
  - porta virtual Intel AMT (Serial-over-LAN), marcada como "Sistema", sem sondagem e fora dos testes.
- Portas sem periférico reconhecido viram "Porta serial", com o motivo:
  - sem permissão (grupo dialout), em "Atenção";
  - em uso por outro programa;
  - aparelho ligado (sinais CTS/DSR/DCD) que não respondeu;
  - "Sem resposta", quando a porta provavelmente está livre.
- Nova escuta passiva identifica balanças que transmitem o peso sozinhas.
- Leitores SuperMax Imaging e outros que se apresentam como teclado são reconhecidos como leitor de código (Zebex, Opticon, CipherLab e outros).
- Filas CUPS aparecem com nome legível ("EPSON L1250 Series").

**Visual**
- O cabeçalho é animado: pacotes de luz percorrem as trilhas do circuito, os nós pulsam e um anel de radar se expande. A animação pausa com a janela minimizada.
- Cards com borda fina, sombra, faixa lateral na cor do estado (é ela que pulsa) e elevação no hover. O estado fica na linha de baixo, então a categoria aparece inteira e o peso ocupa o canto superior.
- "Conectado" (detectado) usa o teal da marca e "OK" (testado) usa verde, para separar visualmente as duas situações.
- Botões com sombra e brilho superior, seletor Cards/Lista com destaque e hover, indicadores com sombra e marcador lateral do filtro ativo.
- Lista com hover de linha, cabeçalho refinado e linhas mais altas.

## 27.0

Simulação e teste de ponta a ponta de todas as opções.

- Novo PDV simulado (`tests/e2e/`). Um container Ubuntu 22.04 recebe `/sys`, `/proc` e `/dev` falsos, comandos `udevadm`, `lpstat` e `systemctl` simulados e periféricos virtuais que respondem de verdade pelas portas seriais: balança P05, impressora ESC/POS, pinpad Gertec, leitor Honeywell, Epson USB com fila CUPS, SAT Elgin, gaveta Posiflex, impressora de rede, monitor Samsung e adaptador PL2303.
- 35 testes de ponta a ponta acionam cada opção como usuário comum: Testar todos, Atualizar, filtros, Cards/Lista, detalhes (testar, copiar, fechar, Esc), atalhos, navegação pelas setas, dicas, notificações, modo compacto, conexão e desconexão a quente, porta ocupada, sem papel, offline, balança instável, fila desativada e falta de permissão. Também cobrem as opções de linha de comando no código-fonte e no executável.
- Corrigido: o `config.json` publicado marcava qualquer `/dev/ttyUSB0` como balança, o que rotulava errado pinpads e impressoras em adaptadores USB-serial. A balança P05 já é identificada automaticamente.
- Corrigido: a fila CUPS de uma impressora USB perdia o modelo, a linguagem (ESC/POS) e as evidências do IEEE 1284.
- Corrigido: a porta estável (`/dev/serial/by-id`) não era encontrada quando o nó da porta era um link.
- Adaptadores USB-serial aparecem com nome curto (PL2303, CH340, FT232R, CP210x).

## 26.0

Revisão e refinamento do front.

- A janela se ajusta à tela do PDV (1024×768, 1366×768) em vez de abrir com 1240×840, maior que a tela.
- Modo compacto automático para janelas baixas, como as de 800×600: cabeçalho e indicadores mais baixos e rodapé sem a lista de atalhos.
- Nova alternância Cards | Lista (Ctrl+1 / Ctrl+2). A vista escolhida ocupa toda a área, em vez de dividir espaço com a outra.
- Contraste de acessibilidade (WCAG AA, mínimo 4,5:1) em todos os textos de status, no texto secundário e no botão principal. Antes, o "OK" verde tinha 3:1.
- Nomes, portas e resultados longos são cortados com "…", sem sobreposição. Ao passar o mouse, uma dica mostra o conteúdo completo, e os botões e indicadores também têm dicas.
- Navegação pelas setas entre os cards. Os indicadores mostram anel de foco.
- Em telas estreitas, os controles da barra têm prioridade sobre o texto de status, e os selos do cabeçalho somem em vez de cobrir o título.
- A janela de detalhes abre centralizada e o texto acompanha o redimensionamento.
- A notificação fecha ao ser clicada, a tabela não tem mais a moldura preta de foco e a animação pausa com a janela minimizada.
- Testes novos de contraste, corte de texto, troca de vista, navegação e tamanho da janela. A suíte roda em resoluções de 640×480 a 1920×1080.

## 25.0

Identificação de precisão para o mercado brasileiro e nova interface.

**Identificação**
- Nova base `perifericos-br.json`, gerada do banco oficial `usb.ids` (versão 2026.06.26) por `tools/gerar_base_perifericos.py`: 52 fabricantes e 870 produtos de PDV, entre eles Elgin, Gertec, SMAK, Control iD, Epson, Bixolon, Honeywell, Datalogic, Zebra, Newland, Ingenico, Verifone, Posiflex, Nitgen e Mettler Toledo.
- Novas categorias: SAT/MF-e, gaveta, display de cliente e leitor de cartão.
- Marcas e modelos brasileiros sem VID próprio são reconhecidos pelo nome informado pelo aparelho: Bematech, Daruma, Sweda, Tanca, Dimep, Toledo, Filizola, Urano, Ramuza, entre outras.
- Impressoras USB informam fabricante, modelo e linguagem pelo IEEE 1284, e monitores informam resolução e tamanho.
- Impressoras seriais são identificadas pelo status ESC/POS. O teste delas passa a acusar falta de papel, papel perto do fim e modo offline.
- Adaptadores USB-serial (FTDI, Prolific, CH340, CP210x) não são mais confundidos com o fabricante do periférico.
- Aparelhos idênticos em portas USB diferentes deixam de ser fundidos em um só.

**Desempenho e confiabilidade**
- As fontes de descoberta e as sondas seriais rodam em paralelo, e uma fonte com falha não esconde as demais.
- O tempo de cada varredura aparece na interface.

**Interface**
- Hero com wallpaper técnico e indicadores clicáveis que filtram por status (Esc limpa o filtro).
- Botões com ícone e estados de hover, pressão e foco, além de barra de progresso durante os testes.
- Cards com elevação no hover, selo de status, glifo do tipo de conexão, spinner durante o teste e pulso suave. Cada tipo de periférico tem um ícone próprio.
- Notificações dos resultados e estado vazio ilustrado.
- Janela de detalhes em seções (Identificação, Conexão, Resultado e Rastreabilidade), com botão "Copiar dados".

**Qualidade**
- Dupla camada de revisão: revisão de código e suíte de precisão com cerca de 70 nomes reais do mercado, casos negativos e conferência contra a fonte oficial. São 64 testes automatizados no total.

## 24.0

Consolidação completa do identificador de periféricos.

- Unificamos o código em um único pacote `hipauto/`, que substitui a cadeia de versões v4 a v23. O repositório voltou a gerar o executável: antes faltava o módulo `hipauto_release`.
- Corrigimos a sonda do teclado SMAK. No executável ela abria outra janela do aplicativo em vez de identificar o teclado PS/2.
- A descoberta agora apenas lê o sistema. Ela não cria filas CUPS nem troca a impressora padrão.
- Impressoras de rede offline e filas USB sem impressora passam a aparecer como falha, em vez de sumir da lista.
- Portas `ttyS` são detectadas sem root, e dispositivos Bluetooth não são mais rotulados como PS/2.
- Cada equipamento aparece uma única vez: as interfaces serial, HID e USB são unificadas pelo caminho físico no barramento.
- Identificamos impressoras pela classe USB e monitores pelo EDID (fabricante e modelo). Leitores, pinpads e impressoras também são identificados pelo fabricante USB.
- A homologação é calculada depois da identificação, então o SMAK SKO-44 passa a constar como homologado.
- Ferramentas do sistema rodam sem as bibliotecas embutidas no executável.
- A comunicação serial restaura a configuração original da porta e não sonda portas em uso por outro programa.
- A interface mostra o progresso do teste de cada periférico e avisa sobre pendências do Ubuntu, como o grupo dialout e o CUPS. Os cards têm rolagem e podem ser acessados pelo teclado, e a janela de detalhes se atualiza após cada teste. Atalhos: F5 atualiza e Ctrl+T testa todos.
- Adicionamos o modo `--report` para suporte e uma suíte de testes automatizados.

## 23.0

- Reformulamos a interface com cards clicáveis e ícones vetoriais para cada periférico.
- Destacamos periféricos ativos com borda verde pulsante.
- Criamos uma lista resumida com periférico, porta e resultado do teste.
- Movemos os detalhes técnicos para uma janela em duas colunas aberta pelo card.

## 22.0

- Mantivemos um link permanente para baixar sempre a versão mais recente.
- Movemos a identificação da versão para uma etiqueta no canto inferior esquerdo do rodapé.
- Registramos a regra de incremento de versão para as próximas atualizações.

## 21.0

- Removemos a busca e a exportação de relatório da interface.

## 20.0

- Corrigimos o empacotamento do teste serial e simplificamos a interface desktop.
