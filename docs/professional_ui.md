# Professional UI Contract

Este documento descreve a interface web do HFSS Filter Studio 0.2.0 como um
contrato de produto. Mudancas futuras devem preservar a densidade operacional,
a hierarquia e os fluxos descritos aqui.

## Principios

- a primeira tela e a ferramenta, nao uma landing page;
- dados de engenharia ocupam a maior parte do viewport;
- comandos globais ficam na barra superior;
- navegacao por dominio fica na lateral;
- definicao do filtro fica acima dos resultados;
- grafico e matriz permanecem visiveis ao mesmo tempo;
- integracoes externas ficam em um dialogo dedicado;
- estados simulado, conectado e offline devem ser distinguiveis;
- modulos planejados aparecem na navegacao, mas nao fingem estar implementados.

## Mapa do Viewport

```text
+-----------------------------------------------------------------------+
| Window title                                                          |
+--------+--------------------------------------------------------------+
| Save   | Project | Refresh | Start | Stop | Calculate | Filter type   |
+--------+--------------------------------------------------------------+
|        | Input | Transmission zeros | Topology controls | Topology    |
| Module +--------------------------------------------------------------+
| nav    | S parameter / delay / power | Coupling matrix / specification|
|        |                              |                                |
+--------+--------------------------------------------------------------+
| Status | calculation summary                    | AEDT/VNA integration|
+-----------------------------------------------------------------------+
```

## Dimensoes

- title bar: 25 px;
- command bar: 42 px;
- status bar: 24 px;
- sidebar desktop: 160 px;
- definition area desktop: 192 px;
- espacamento entre paineis: 5 px;
- bordas: 1 px;
- botoes operacionais: 25 a 32 px.

Nao usar cards flutuantes, sombras decorativas ou grandes espacos vazios na
workstation. O dialogo modal pode usar sombra por representar uma camada acima
da aplicacao.

## Barra Superior

### Save

Gera um arquivo de projeto JSON. `Ctrl+S` executa a mesma acao.

### Project Name

Mostra:

- `Unsaved Project *` quando ha alteracoes;
- `Filter Project` depois de salvar ou carregar.

### Frequency Span

Os campos de inicio e fim sao globais. Eles alimentam:

- a sintese;
- o eixo X;
- a configuracao VNA;
- o arquivo de projeto.

### Calculate All

Chama `POST /api/synthesis/calculate`, atualiza todas as visualizacoes e registra
o resultado no status inferior. `F5` executa o mesmo fluxo sem recarregar a
pagina.

### Filter Type

O controle segmentado seleciona:

- BPF;
- BSF;
- LPF;
- Multi.

A selecao dispara novo calculo e permanece no projeto.

## Navegacao Lateral

Secoes podem ser recolhidas. O MVP mantem `Synthesis / Single` ativo. Itens
planejados exibem um aviso curto e nao trocam o workspace por uma tela vazia.

Na base da lateral existem dois estados de integracao:

- AEDT;
- VNA.

Cada linha abre diretamente a aba correspondente no dialogo de integracao.

## Definition Area

### Input

Contem os parametros escalares. Os toggles `F0` e `BW` podem desabilitar seus
campos. `R` restaura o baseline BPF de quarta ordem.

### Transmission Zeros

`+` adiciona um zero. Cada linha possui:

- indice;
- frequencia em GHz;
- profundidade em dB;
- comando de remocao.

Alteracoes marcam o projeto como sujo. O calculo ocorre ao usar `Calculate All`.

### Physical Topology

O botao `Edit Topology` prepara o ponto de extensao para edicao grafica. Na fase
atual, a topologia e controlada por ordem, zeros e matriz.

### Filter Dispersion

O grupo segmentado seleciona `symmetric`, `input`, `output` ou `both`. `Apply
Dispersion` recalcula matriz e atraso.

### Topology Diagram

Nos vermelhos representam portas e ressonadores. Arestas cinza representam
acoplamentos principais. Arestas tracejadas representam acoplamentos cruzados.

## Result Area

### Chart

O canvas e recalculado quando:

- o backend retorna novas series;
- o viewport muda;
- uma curva e habilitada/desabilitada;
- o piso muda;
- o marcador muda;
- uma medicao VNA e adquirida.

Coordenadas de desenho usam pixels CSS e o canvas interno usa ate 2x device
pixel ratio para manter nitidez sem consumo excessivo.

### Matrix

As cores tem significado:

- branco: zero;
- laranja: acoplamento fora da diagonal;
- verde: diagonal;
- contorno azul: celula selecionada.

A aba `Specification` mostra valores derivados, sem esconder os controles
globais.

## Integration Dialog

O dialogo possui tres abas:

- AEDT/HFSS;
- VNA;
- Service Log.

O log registra metodo, rota, timestamp e JSON de resposta. O limite visual e
50.000 caracteres para evitar crescimento ilimitado da pagina.

Erros sao apresentados simultaneamente em:

- toast;
- status inferior;
- log tecnico.

## Responsividade

Acima de 1280 px:

- quatro paineis de definicao na mesma linha;
- grafico e matriz lado a lado.

Entre 901 e 1280 px:

- definicao em duas colunas;
- workspace passa a ter scroll vertical;
- grafico e matriz permanecem lado a lado quando houver largura.

Ate 900 px:

- navegacao vira faixa compacta;
- definicao usa uma coluna;
- grafico e matriz sao empilhados;
- o documento passa a rolar.

Ate 560 px:

- campos secundarios da barra superior sao ocultados;
- formularios de integracao usam uma coluna;
- matriz permanece rolavel.

## Estado no Navegador

O objeto `workspace` mantem:

- tipo de filtro;
- dispersao;
- zeros;
- ultimo resultado;
- ultima medicao VNA;
- modo do grafico;
- curvas visiveis;
- marcador;
- modo de edicao da matriz;
- celula selecionada;
- indicador de alteracao.

O estado de AEDT e VNA vem sempre de `GET /api/state`; o frontend nao assume que
uma conexao permaneceu ativa depois de reiniciar o servidor.

## Regras de Evolucao

- novos modulos devem usar o mesmo shell;
- novas paginas nao devem substituir a barra de status;
- operacoes longas devem publicar progresso;
- qualquer acao destrutiva precisa de confirmacao;
- dados reais e simulados devem ser rotulados;
- graficos devem preservar unidades;
- entradas numericas devem validar limites no cliente e no servidor;
- toda rota nova precisa de teste Flask e documentacao em `api_reference.md`.
