# Histórico de versões

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
