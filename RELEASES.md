# Histórico de versões

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
