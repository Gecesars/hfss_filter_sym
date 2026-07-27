# SymMatrix-style MVP

Este documento define o escopo funcional da implementacao original do HFSS
Filter Studio. A referencia de produto e uma estacao de trabalho para sintese,
modelagem, otimizacao e tuning de filtros. Nenhum codigo, asset ou algoritmo
proprietario foi incorporado.

## Objetivo do MVP

O MVP profissional entrega uma superficie unica para:

1. definir uma resposta de filtro;
2. gerar uma resposta analitica deterministica;
3. visualizar parametros S, atraso de grupo e potencia;
4. inspecionar e editar uma matriz de acoplamento;
5. representar a topologia fisica correspondente;
6. abrir uma sessao AEDT/HFSS;
7. configurar e adquirir dados de um VNA;
8. salvar e carregar o estado de projeto;
9. preservar os contratos HTTP necessarios para expansao.

O calculo atual e um modelo analitico original para desenvolvimento da interface
e dos fluxos. Ele nao substitui um solver eletromagnetico, uma sintese de
polinomios completa nem o resultado medido em bancada.

## Estado por Modulo

| Modulo | Estado 0.2.0 | Contrato atual | Proxima entrega |
| --- | --- | --- | --- |
| Synthesis / Single | Funcional | Entrada, zeros, dispersao, grafico, matriz e topologia | Prototipos polinomiais rigorosos |
| Synthesis / Dip-MUX | Planejado | Item de navegacao e tipo `MULTI` inicial | Canais, junction e composicao |
| 3D Modeling / Cavity | Parcial | Rotas HFSS reservadas e AEDT funcional | Gerador parametrico de cavidade |
| 3D Modeling / Planar | Parcial | Rotas HFSS reservadas e AEDT funcional | Microstrip, SIW e layout |
| Optimization / CAT | Planejado | Evento e endpoint reservados | Ciclo modelo-medicao-ajuste |
| Intelligent Optimization | Planejado | SocketIO reservado | Fila, objetivos e historico |
| Test & Tuning | Parcial | VNA, sweep e overlay de S11 | Algoritmo de tuning por portas |
| Monte Carlo | Planejado | Item de navegacao | Distribuicoes e yield |
| TL Calculator | Planejado | Item de navegacao | Modelos de linha |
| Project Management | Parcial | JSON local versionado | Persistencia no servidor |
| e-Library | Planejado | Item de navegacao | Biblioteca de topologias |

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
  "version": 1,
  "saved_at": "2026-07-27T12:00:00.000Z",
  "specification": {},
  "matrix": {}
}
```

`Load Data` aceita esse formato, restaura entradas, zeros, tipo, dispersao e
matriz, e recalcula as series. Formatos desconhecidos sao recusados.

## Integracao AEDT/HFSS

O dialogo de integracao permite:

- selecionar backend `simulated` ou `pyaedt`;
- informar projeto `.aedt` e design;
- abrir/reusar sessao;
- ler variaveis;
- aplicar variaveis por JSON;
- analisar e exportar Touchstone.

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
- `stop`

## Integracao VNA

O dialogo de integracao permite:

- selecionar backend `simulated` ou `pyvisa`;
- informar resource VISA e fabricante;
- configurar faixa a partir do projeto;
- configurar pontos, IFBW e potencia;
- executar sweep unico;
- adicionar a medicao ao grafico;
- salvar `.s2p`.

Rotas funcionais:

- `status`
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

## Endpoints Reservados

Endpoints presentes no contrato e ainda sem implementacao retornam:

```json
{
  "status": -501,
  "ok": false,
  "implemented": false
}
```

Familias reservadas:

- `aedt/createreport`
- `aedt/makelpfmodel`
- `aedt/callconvergence`
- `aedt/callkillmesh`
- `hfss/*simulation`
- `hfss/*modeling`
- `hfss/*couplingmodeling`
- `hfss/*iomodeling`
- `hfss/lpf_*_modeling`

## Criterios para a Proxima Fase

1. substituir a aproximacao analitica por sintese de prototipo validada;
2. importar Touchstone real no projeto;
3. comparar alvo, HFSS e VNA no mesmo grafico;
4. implementar fila de jobs AEDT com progresso e cancelamento;
5. persistir projetos no servidor com historico;
6. implementar tuning com objetivos, limites e rollback;
7. adicionar testes de integracao marcados para AEDT e instrumentos reais.
