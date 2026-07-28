# Evolucao FD3D-like do HFSS Filter Studio

## 1. Objetivo

Evoluir o `hfss_filter_sym` de uma estacao de sintese e automacao para uma
plataforma completa de projetos de filtros baseada nos principios de trabalho do
CST Filter Designer 3D e do SymMatrix, sem copiar implementacoes proprietarias.

A plataforma deve manter rastreabilidade continua entre:

```text
especificacao eletrica
  -> funcao de transferencia
  -> matriz de acoplamento alvo
  -> topologia realizavel
  -> biblioteca de componentes
  -> caracterizacao Eigenmode
  -> curvas eletrico-geometricas
  -> montagem parametrica do filtro
  -> simulacao full-wave
  -> matriz equivalente extraida
  -> otimizacao e sintonia
  -> medicao VNA e liberacao de projeto
```

O nome interno desta evolucao e **FD3D Project Platform**.

## 2. Diagnostico da base atual

### Capacidades existentes que devem ser preservadas

- sintese BPF, BSF, LPF e multibanda;
- respostas Chebyshev, Butterworth, Bessel e Elliptic;
- matriz de acoplamento e resposta de matriz;
- geracao de planos parametricos cavity, combline, waveguide, planar e SIW;
- construcao PyAEDT de boxes, cylinders, subtract, unite e lumped ports;
- jobs serializados, progresso e cancelamento;
- persistencia JSON com revisoes;
- aquisicao VNA S11, S21, S12 e S22;
- comparacao Touchstone;
- tuning por sensibilidades e Monte Carlo;
- backends reais e simulados.

### Lacunas estruturais

1. O projeto persistente nao possui workflow de engenharia por etapas.
2. A geometria e gerada como um filtro inteiro, nao como componentes caracterizados.
3. Nao existe biblioteca versionada de ressonadores, acoplamentos e portas.
4. Nao existe estudo Eigenmode como entidade do dominio.
5. Nao existem curvas `f_r(x)`, `k_ij(x)` e `Q_e(x)` persistentes.
6. Nao existe tracking de modos entre variacoes parametricas.
7. Nao existe montagem por interfaces e anchors.
8. Nao existe mapeamento inverso de alvo eletrico para dimensao fisica.
9. Nao existe extracao de matriz equivalente a partir de S-parametros.
10. O tuning atual usa metricas globais, sem diagnostico por ressonador/acoplamento.
11. Nao existe separacao formal entre modelo coarse e modelo EM fine.
12. Nao existe ciclo Trust Region/space mapping baseado em matriz.

## 3. Principios arquiteturais

### 3.1 Dominio independente do solver

Modelos de projeto, componentes, estudos e curvas nao podem importar PyAEDT,
Flask ou PyVISA. O dominio deve executar e ser testado offline.

### 3.2 Planos antes de efeitos colaterais

Toda operacao AEDT deve receber um plano serializavel, validavel e exibivel antes
da construcao real.

### 3.3 Um resultado nunca perde a configuracao que o gerou

Cada solve, curva e matriz extraida deve guardar:

- snapshot da geometria;
- versao do componente;
- parametros;
- setup;
- solver;
- frequencias/modos;
- hash deterministico;
- data e estado.

### 3.4 Componentes reutilizaveis

O filtro deve ser montado com definicoes de componentes e instancias:

- resonator;
- internal coupling;
- external coupling;
- source/load transition;
- housing;
- tuning feature;
- non-resonating node;
- cross-coupling.

### 3.5 Nenhum algoritmo deve esconder hipoteses fisicas

O sinal de um acoplamento nao pode ser inferido apenas pela separacao modal.
Deve ser informado pela topologia ou determinado pela paridade/fase dos campos.

## 4. Workflow de projeto

Estados persistentes:

```text
SPECIFICATION
SYNTHESIS
TOPOLOGY
COMPONENT_LIBRARY
CHARACTERIZATION
ASSEMBLY
FULLWAVE_ANALYSIS
MATRIX_EXTRACTION
OPTIMIZATION
VNA_TUNING
RELEASED
```

Cada transicao deve possuir validacao e checklist.

## 5. Modelo de dados

### 5.1 Projeto

Schema inicial:

```text
hfss-filter-studio/fd3d-project/v1
```

Campos principais:

- identidade e revisao;
- etapa do workflow;
- especificacao;
- resultado da sintese;
- matriz alvo;
- topologia;
- definicoes e instancias de componentes;
- estudos de caracterizacao;
- curvas aprovadas;
- assembly;
- solves full-wave;
- matrizes extraidas;
- campanhas de otimizacao;
- sessoes VNA/tuning;
- artefatos e auditoria.

### 5.2 Definicao de componente

Cada componente deve declarar:

- `component_id` estavel;
- nome e versao;
- tecnologia;
- categoria;
- recipe geometrica;
- parametros tipados;
- interfaces de montagem;
- anchors;
- materiais;
- limites de fabricacao;
- estudo padrao;
- observaveis esperados;
- validacoes.

### 5.3 Parametros

Tipos:

```text
length
angle
ratio
integer
boolean
material
expression
```

Cada parametro possui unidade, nominal, minimo, maximo, passo de estudo e papel:

```text
tuning
manufacturing
fixed
assembly
solver
```

### 5.4 Estudos de caracterizacao

Tipos iniciais:

```text
RESONANCE
COUPLING
EXTERNAL_Q
SPURIOUS_MODES
LOSS_Q
```

Cada estudo registra eixo parametrico, variacoes, modos, campos, metricas e curva
aprovada.

## 6. Caracterizacao Eigenmode

### 6.1 Ressonador isolado

Para cada valor do parametro geometrico `x`:

1. construir a geometria do componente;
2. executar Eigenmode;
3. extrair frequencias modais e Q;
4. identificar o modo desejado;
5. rastrear o modo entre variacoes;
6. salvar a amostra;
7. ajustar curva monotona ou por trechos:

```text
f_r = F(x)
```

A inversa fornece a dimensao inicial:

```text
x = F^-1(f_target)
```

### 6.2 Par de ressonadores

Para dois ressonadores identicos acoplados:

```text
k = sign * (f_high^2 - f_low^2) / (f_high^2 + f_low^2)
```

O estudo deve registrar:

- frequencias dos dois modos;
- magnitude de `k`;
- sinal informado ou confirmado por campo;
- paridade dos modos;
- identificador do acoplamento;
- risco de mode crossing;
- modos espurios proximos.

A curva final:

```text
k_ij = K(x_coupling)
```

### 6.3 Acoplamento externo

O primeiro incremento deve aceitar valores `Q_e` calculados ou importados. A
fase seguinte extraira `Q_e` de modelos driven/modal e de curvas de fase ou
energia armazenada.

Curva:

```text
Q_e = Q(x_port)
```

## 7. Tracking de modos

Nunca assumir que o modo `1` do solver continua sendo o mesmo modo na proxima
variacao.

Estrategia em fases:

1. proximidade de frequencia;
2. continuidade de Q;
3. correlacao de energia por regiao;
4. correlacao de campos exportados;
5. MAC/modal assurance criterion;
6. classificacao por simetria/paridade.

O sistema deve marcar estudos ambiguos em vez de suavizar silenciosamente um
mode crossing.

## 8. Biblioteca de componentes

Estrutura conceitual:

```text
component-library/
  combline/
    resonator/
    magnetic-iris/
    electric-window/
    coaxial-probe/
    housing/
  interdigital/
  rectangular-waveguide/
  siw/
  dielectric-resonator/
  planar/
```

Primeira tecnologia de referencia: **combline coaxial**.

Componentes iniciais:

1. cavidade/resonador combline isolado;
2. par combline com abertura de acoplamento;
3. probe coaxial de entrada/saida;
4. housing linear;
5. tuning screw opcional.

## 9. Assembly

A montagem sera um grafo:

- nodes: instancias de componentes;
- edges: interfaces conectadas;
- electrical targets: `M_ij`, `Q_e`, detuning;
- physical variables: iris, gap, probe, rod length;
- transforms: translacao, rotacao e espelhamento.

Cada interface deve declarar:

- frame local;
- normal;
- plano de contato;
- clearance;
- tipo eletrico;
- compatibilidade mecanica.

Antes do AEDT, validar:

- interfaces abertas;
- sobreposicao;
- gaps;
- materiais incompatíveis;
- dimensoes fora da curva caracterizada;
- acoplamento alvo fora do envelope fisico;
- sinais nao realizaveis.

## 10. Geracao de dimensoes iniciais

Para cada alvo:

```text
M_ij alvo -> curva K_ij(x) -> x inicial
f_ri alvo -> curva F_i(x) -> x inicial
Q_e alvo -> curva Q(x) -> x inicial
```

O mapeamento deve retornar:

- dimensao;
- alvo;
- valor previsto;
- erro de interpolacao;
- extrapolacao usada ou nao;
- intervalo de validade;
- sensibilidade local `dy/dx`;
- versao da curva.

Extrapolacao deve ser proibida por padrao.

## 11. Modelo full-wave

Depois da montagem:

1. gerar um plano deterministico;
2. construir o design driven/modal;
3. criar portas e boundaries;
4. criar setup/sweep;
5. validar;
6. resolver;
7. exportar S-parametros complexos;
8. armazenar convergencia e mesh statistics;
9. associar ao snapshot do assembly.

## 12. Extracao de matriz equivalente

Arquitetura prevista:

```text
Touchstone/S complexos
  -> pre-processamento
  -> identificacao de polos/zeros
  -> ajuste racional
  -> modelo coarse
  -> matriz equivalente
  -> alinhamento topologico
  -> delta M
```

Primeira implementacao deve suportar matriz real simetrica de filtros de duas
portas sem perdas ou com perdas diagonais simples.

Evolucoes:

- matrizes complexas;
- source-load coupling;
- non-resonating nodes;
- topologias assimetricas;
- frequencia dependente;
- multiplexers.

## 13. Otimizacao FD3D-like

### Fase 1: correcao por curvas

Atualizar dimensoes usando inversas caracterizadas.

### Fase 2: sensitivities

Construir Jacobiano:

```text
J = d(M_extracted) / d(x)
```

Resolver passo regularizado.

### Fase 3: Trust Region

- limitar passo;
- predizer reducao;
- executar solve fino;
- calcular razao real/predita;
- aceitar/rejeitar;
- ajustar raio.

### Fase 4: space mapping

Atualizar o mapeamento entre matriz coarse e modelo EM fine.

Cache obrigatorio por hash da configuracao.

## 14. Sintonia VNA

O tuning deve deixar de produzir apenas recomendacoes globais.

Fluxo alvo:

```text
VNA -> S complexos -> matriz equivalente medida -> delta M -> ajustes fisicos
```

Recomendacoes:

- resonator i: frequencia alta/baixa;
- coupling i-j: forte/fraco;
- source/load: Qe alto/baixo;
- cross-coupling: zero deslocado;
- ordem de ajuste sugerida;
- confianca e sensibilidade.

Registrar cada iteracao de hardware.

## 15. API planejada

Primeiro conjunto:

```text
POST /api/fd3d/projects/blueprint
POST /api/fd3d/characterization/curve
POST /api/fd3d/characterization/invert
POST /api/fd3d/components/plan
POST /api/fd3d/projects/validate
```

Evolucao:

```text
POST /api/fd3d/studies
POST /api/fd3d/studies/<id>/run
GET  /api/fd3d/studies/<id>
POST /api/fd3d/assembly/build
POST /api/fd3d/fullwave/run
POST /api/fd3d/matrix/extract
POST /api/fd3d/optimize
POST /api/fd3d/tuning/session
```

## 16. Interface planejada

A workstation tera uma area de projeto com etapas:

1. Specification;
2. Synthesis;
3. Topology;
4. Components;
5. Characterization;
6. Assembly;
7. Full-wave;
8. Matrix extraction;
9. Optimization;
10. VNA tuning;
11. Release.

Views essenciais:

- grafo de matriz/topologia;
- biblioteca de componentes;
- tabela de variacoes Eigenmode;
- curvas `f_r`, `k`, `Q_e`;
- inspetor de modos;
- assembly 2D/3D;
- target matrix versus extracted matrix;
- heatmap de `Delta M`;
- historico de iteracoes;
- painel de tuning VNA.

## 17. Persistencia e artefatos

O ProjectStore sera ampliado sem quebrar projetos v2. Novos campos opcionais:

```text
workflow
fd3d
components
characterizations
assembly
analyses
optimizations
tuning_sessions
artifacts
```

Artefatos grandes permanecem fora de `project.json`; o JSON armazena caminho,
hash e metadata.

## 18. Fases de desenvolvimento

### Fase 0 - Fundacao

- novo dominio FD3D;
- schema de projeto;
- formulas Eigenmode;
- curvas e inversao;
- blueprint a partir da sintese atual;
- planos de componentes combline;
- endpoints offline;
- testes.

### Fase 1 - Eigenmode real

- contrato AEDT Eigenmode;
- criacao de design separado;
- setup Eigenmode;
- sweep parametrico;
- extracao de frequencias e Q;
- persistencia das amostras;
- worker/job especializado.

### Fase 2 - Mode tracking

- tracking por frequencia/Q;
- exportacao e correlacao de campos;
- detector de crossing;
- aprovacao manual de modo.

### Fase 3 - Component library

- versao de componentes;
- anchors/interfaces;
- combline completo;
- importacao/exportacao;
- validacao de envelope.

### Fase 4 - Assembly

- grafo de montagem;
- mapeamento eletrico-geometrico;
- geracao parametrica em partes;
- full-wave driven modal.

### Fase 5 - Matrix extraction

- fitting racional;
- polos e residuos;
- matriz equivalente;
- alinhamento com topologia;
- diagnostico `Delta M`.

### Fase 6 - Optimization

- sensitivities;
- Jacobiano;
- Trust Region;
- cache;
- moving/deformation strategy quando suportada.

### Fase 7 - VNA tuning

- matriz medida;
- de-embedding;
- recomendacoes por elemento;
- historico de ajuste;
- modo operador.

### Fase 8 - Tecnologias adicionais

- waveguide;
- SIW/ESIW;
- interdigital;
- dielectric resonator;
- planar;
- dual-mode;
- non-resonating nodes;
- diplexers/multiplexers.

## 19. Testes

### Unitarios

- formula de acoplamento;
- sinal;
- tracking simples;
- monotonicidade;
- interpolacao e inversao;
- sensibilidade;
- hash;
- validacao do projeto;
- grafo de assembly.

### Contrato AEDT fake

- ordem de construcao;
- design Eigenmode sem portas;
- setup e numero de modos;
- variacoes;
- extracao de frequencias;
- falhas explicitas.

### AEDT real opt-in

Variaveis:

```text
HFSS_FILTER_REAL_AEDT=1
HFSS_FILTER_REAL_SOLVE=1
```

Casos:

1. resonator combline isolado;
2. par com abertura pequena/media/grande;
3. monotonicidade de `f_r(x)`;
4. monotonicidade de `|k(x)|`;
5. repetibilidade;
6. modos espurios.

## 20. Criterios de aceite da primeira tecnologia

Combline de quatro polos:

- blueprint derivado da matriz alvo;
- componentes individuais identificaveis;
- curva de resonancia aprovada;
- curva de coupling aprovada;
- dimensoes iniciais sem extrapolacao;
- assembly completo;
- duas portas;
- full-wave resolvido;
- matriz equivalente extraida;
- diagnostico por `Delta M`;
- pelo menos uma iteracao de correcao;
- comparacao target/HFSS/VNA persistida.

## 21. Riscos e controles

| Risco | Controle |
| --- | --- |
| mode crossing | tracking e estado ambiguo |
| curvas nao monotonas | segmentacao e bloqueio de inversao |
| extrapolacao perigosa | proibida por padrao |
| API PyAEDT instavel | adapter e contrato fake |
| projetos grandes | artefatos externos com hash |
| solves duplicados | cache por hash |
| matriz nao realizavel | validador topologico/fisico |
| sinal de coupling errado | metadata de paridade e aprovacao |
| acoplamento parasita | full-wave e matriz extraida |
| tuning incorreto | sensitivities com confianca |

## 22. Entrega inicial desta branch

A branch inicia a Fase 0 com:

- modelos de dominio;
- formulas de caracterizacao;
- curvas interpolaveis e inversiveis;
- blueprint de projeto a partir da sintese atual;
- planos Eigenmode de componentes combline;
- endpoints REST offline;
- persistencia ampliada;
- testes unitarios.

Nenhuma alegacao de validacao AEDT real sera feita antes dos testes opt-in.
