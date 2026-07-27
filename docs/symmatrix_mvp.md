# SymMatrix-style MVP

Este documento define o escopo funcional da implementacao original do HFSS
Filter Studio. A referencia de produto e uma estacao de trabalho para sintese,
modelagem, otimizacao e tuning de filtros. Nenhum codigo, asset ou algoritmo
proprietario foi incorporado.

## Objetivo do MVP

O MVP profissional entrega uma superficie unica para:

1. definir uma resposta de filtro;
2. sintetizar uma rede analogica deterministica;
3. visualizar parametros S, atraso de grupo e potencia;
4. inspecionar e editar uma matriz de acoplamento;
5. representar a topologia fisica correspondente;
6. abrir uma sessao AEDT/HFSS;
7. configurar e adquirir dados de um VNA;
8. salvar e carregar o estado de projeto;
9. preservar os contratos HTTP necessarios para expansao.

O calculo atual usa prototipos analogicos SciPy, transformacao de frequencia,
parametros S complexos, valores g e escalamento fisico. Ele nao substitui o
solver eletromagnetico nem o resultado medido em bancada.

## Estado por Modulo

| Modulo | Estado 0.4.0 | Contrato atual |
| --- | --- | --- |
| Synthesis / Single | Funcional | Prototipos reais, zeros, grafico, matriz, Qe e elementos |
| Synthesis / Dip-MUX | Funcional | Dois a dezesseis canais, resposta composta e topologia de junction |
| 3D Modeling / Cavity | Funcional | Preview e construcao de cavity, combline e waveguide |
| 3D Modeling / Planar | Funcional | Microstrip, SIW e quatro receitas de LPF |
| Optimization / CAT | Funcional | Comparacao Touchstone e recomendacoes por sensibilidade |
| Intelligent Optimization | Funcional | Differential evolution com limites, seed e historico |
| Test & Tuning | Funcional | S11/S21 HFSS/VNA e acoes de sintonia |
| Monte Carlo | Funcional | Tolerancias, limites, estatisticas e yield |
| TL Calculator | Funcional | Microstrip, stripline, waveguide e SIW |
| Project Management | Funcional | Persistencia atomica, revisoes e restauracao |
| e-Library | Funcional | Templates de sintese e modelagem |

## Synthesis / Single

### Entradas

- tipo: `BPF`, `BSF`, `LPF` ou `MULTI`;
- ordem: inteiro de 1 a 12;
- return loss em dB;
- frequencia central em GHz;
- largura de banda em GHz;
- frequencia inicial e final em GHz;
- shift de frequencia em MHz;
- delta de largura de banda em MHz;
- Q descarregado finito ou infinito;
- familia de resposta registrada no projeto;
- lista de zeros de transmissao;
- modo e valor de dispersao.

### Saidas

- vetor de frequencias;
- `S11`, `S21` e `S22` em dB;
- atraso de grupo em ns;
- potencia entregue em W;
- matriz de acoplamento normalizada;
- topologia de nos e arestas;
- resumo de insertion loss e minimos de retorno.

### Regras de Validacao

- `stop_ghz` deve ser maior que `start_ghz`;
- frequencias e largura de banda devem ser positivas;
- ordem deve permanecer entre 1 e 12;
- pontos devem permanecer entre 101 e 2001;
- zeros devem ser objetos com frequencia positiva;
- tipos desconhecidos retornam HTTP 400;
- falhas de validacao nunca iniciam AEDT ou VNA.

## Matriz de Acoplamento

A matriz usa rotulos `S`, ressonadores `1..N` e `L`. O backend gera:

- acoplamentos principais simetricos;
- diagonal para termos de dispersao;
- acoplamentos cruzados derivados dos zeros finitos;
- unidade normalizada.

No frontend:

- `Edit Matrix` converte celulas em campos numericos;
- toda alteracao `M[i,j]` atualiza `M[j,i]`;
- `Edit Sign` inverte a celula selecionada e seu par simetrico;
- `Export` gera CSV com cabecalhos;
- diagonal, acoplamentos e zeros usam cores distintas;
- o arquivo de projeto preserva a matriz editada.

## Topologia

A topologia e derivada da mesma ordem e lista de zeros usadas pela matriz:

- portas `S` e `L`;
- um no por ressonador;
- arestas principais entre elementos adjacentes;
- arestas cruzadas para zeros finitos;
- coordenadas normalizadas para manter o desenho responsivo.

O SVG e apenas uma visualizacao funcional de dados do projeto. A fase de
modelagem 3D deve trocar cada no por uma entidade geometrica AEDT.

## Graficos

O canvas possui tres modos:

- `S Parameter`: curvas `S11`, `S21`, `S22` e overlay VNA;
- `Group Delay`: atraso de grupo calculado;
- `Power Analysis`: potencia entregue estimada.

Controles:

- piso de amplitude configuravel;
- reset de escala;
- curvas habilitadas individualmente;
- tooltip por frequencia;
- marcador vertical movido por clique;
- redimensionamento com compensacao de densidade de pixels.

## Projeto Local

`Save` baixa um JSON versionado com:

```json
{
  "format": "hfss-filter-studio-project",
  "version": 2,
  "saved_at": "2026-07-27T12:00:00.000Z",
  "specification": {},
  "matrix": {},
  "measurements": {"hfss": [], "vna": []}
}
```

`Load Data` aceita esse formato, restaura entradas, zeros, tipo, dispersao e
matriz, e recalcula as series. Formatos desconhecidos sao recusados.

`Project Management` persiste o mesmo dominio no servidor, atribui um ID,
incrementa revisoes e permite restaurar qualquer versao anterior.

## Integracao AEDT/HFSS

O dialogo de integracao permite:

- selecionar backend `simulated` ou `pyaedt`;
- informar projeto `.aedt` e design;
- abrir/reusar sessao;
- ler variaveis;
- aplicar variaveis por JSON;
- configurar setup e sweep;
- validar o design;
- enfileirar/cancelar analises;
- criar modelos parametricos;
- exportar Touchstone, convergencia e resultados.

Rotas funcionais:

- `openproject`
- `getdesigns`
- `setactivedesign`
- `getvariables`
- `getvariablesvalue`
- `setvariablesvalue`
- `setsettings`
- `evaluatedimension`
- `evaluatedimensionnos2p`
- `configureanalysis`
- `validatedesign`
- `exportresults`
- `stopanalysis`
- `stop`

## Integracao VNA

O dialogo de integracao permite:

- selecionar backend `simulated` ou `pyvisa`;
- informar resource VISA e fabricante;
- descobrir resources VISA;
- configurar faixa a partir do projeto;
- configurar pontos, IFBW, potencia e tipo de sweep;
- executar sweep unico;
- adquirir `S11`, `S21`, `S12` e `S22`;
- adicionar overlays S11/S21 ao grafico;
- salvar `.s2p`.

Rotas funcionais:

- `status`
- `resources`
- `capabilities`
- `errors`
- `connect`
- `close`
- `reset`
- `clearerrmsg`
- `initialize2`
- `loadpreset`
- `setfrequency`
- `setifbw`
- `setpower`
- `setsweeppoints`
- `setsweeptype`
- `setcontinoussweep`
- `settrace`
- `settracestatus`
- `setmarkers`
- `setautoscaletrace`
- `getsweeptime`
- `getmarkeryvalue`
- `savetracedata`
- `deleteallmarkers`
- `deletetraces`
- `singlesweep`
- `beginbackgroundsweep`
- `endbackgroundsweep`
- `exports2p`

## Superficie Implementada

Todos os metodos publicados por `GET /health` possuem handler. A superficie
inclui report, convergencia, limpeza de malha, configuracao de setup, validacao,
exportacao de resultados, simulacao em fila e todas as familias de modelagem
listadas no contrato. Metodos desconhecidos retornam `status=-404`.

A documentacao detalhada de cada modulo, limites e validacao esta em
[`full_functionality.md`](full_functionality.md).

## Limites de Engenharia

1. zeros cruzados usam estimativa inicial de triplet; uma sintese Cameron
   generalizada continua sendo um motor avancado separado;
2. a composicao Dip/MUX fornece o ponto inicial dos canais e junction, enquanto
   isolamento final depende do solve eletromagnetico;
3. modelos de cavidade e planar sao parametricos, mas dimensoes e materiais
   devem ser validados para o processo de fabricacao;
4. tuning depende de sensibilidades mecanicas ou eletromagneticas fornecidas;
5. testes automatizados nao consomem licenca AEDT nem conectam RF ao hardware.
