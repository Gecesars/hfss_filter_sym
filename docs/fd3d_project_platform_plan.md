# HFSS Filter Studio — Plano de evolução para plataforma FD3D/SymMatrix

> Documento mestre da branch `feature/fd3d-project-platform`.
>
> A implementação é original e inspirada nos conceitos públicos de síntese por matriz de acoplamento, caracterização eletromagnética de componentes, assembly paramétrico, space mapping e tuning assistido. Não contém código, formatos internos ou ativos proprietários do CST FD3D ou do SymMatrix.

## 1. Objetivo

Evoluir o `hfss_filter_sym` para uma plataforma completa de projetos de filtros, cobrindo:

1. especificação;
2. síntese da resposta;
3. matriz de acoplamento;
4. escolha da topologia;
5. biblioteca de componentes físicos;
6. caracterização real no HFSS;
7. mapping elétrico para dimensões;
8. assembly geométrico em partes;
9. análise full-wave;
10. extração de matriz equivalente;
11. otimização e space mapping;
12. fabricação e tolerâncias;
13. medição e tuning por VNA;
14. liberação versionada do projeto.

## 2. Diretrizes físicas obrigatórias

### 2.1 Eigenmode

A caracterização de frequência de ressonância, Q modal, modos espúrios e split de modos acoplados é executada no HFSS Eigenmode real.

Backends simulados e mocks existem somente para testes de contrato, interface, persistência e tratamento de erros. Eles nunca produzem curvas aprováveis.

### 2.2 External Q

A caracterização de acoplamento externo é executada no HFSS Driven Modal com uma porta. A plataforma ajusta o `S11` complexo e extrai `f0`, `QL`, `Qe`, `Qi`, beta, fase e atraso elétrico.

### 2.3 Filtro completo

O filtro montado é analisado em um design HFSS Driven Modal separado dos designs Eigenmode de componentes.

### 2.4 Aprovação

Nenhuma curva é liberada automaticamente. Aprovação exige evidência, rastreabilidade, revisão técnica e digest SHA-256.

## 3. Estado implementado nesta branch

### 3.1 Domínio e projetos

Implementado:

- schema FD3D versionado;
- estágios de `SPECIFICATION` até `RELEASED`;
- definições tipadas de componentes e parâmetros;
- amostras e curvas de caracterização;
- persistência compatível com projetos legados;
- gates formais de workflow;
- anexação e substituição de curvas;
- mapping e assembly anexados ao projeto;
- proibição de saltos indevidos entre fases.

### 3.2 Blueprint combline

Implementado:

- criação a partir da síntese existente;
- matriz alvo;
- grafo de nós e ligações;
- alvos de ressonância, `Mij` e `Qe`;
- componentes de ressonador, íris, probe e housing;
- dimensões seed marcadas como heurísticas e não validadas.

### 3.3 Eigenmode real no HFSS

Implementado:

- plano de ressonador isolado;
- plano de par acoplado;
- design HFSS Eigenmode separado;
- setup `HFSSEigen`;
- varredura geométrica sequencial;
- solve real por `analyze_setup`;
- extração de `Eigen Modes` e `Eigen Q`;
- tracking inicial por deslocamento mínimo de frequência;
- sinalização de tracking ambíguo;
- cálculo de acoplamento por split modal;
- proibição de aprovação automática.

Pendente de validação real:

- execução no AEDT 2026.1 com licença;
- classificação por campos;
- correlação modal por campos/MAC;
- exportação automática completa das evidências de campo por modo.

### 3.4 Curvas e mapping

Implementado:

- curvas PCHIP;
- detecção de monotonicidade;
- avaliação e inversão;
- extrapolação proibida por padrão;
- mapping de frequência, `Mij` e `Qe` para dimensões;
- preservação de sensibilidade e curva de origem;
- bloqueio de curva não aprovada no assembly de engenharia.

### 3.5 External Q real no HFSS

Implementado:

- plano Driven Modal de uma cavidade e um probe;
- coaxial/probe parametrizado;
- uma porta;
- sweep discreto denso;
- solve real para cada profundidade;
- extração do `S11` complexo;
- ajuste não linear robusto;
- cálculo de `f0`, `QL`, `Qe`, `Qi`, beta, fase, atraso e resíduo;
- curva `Qe(probe_depth)`;
- gate de aprovação específico para Driven Modal.

Pendente de validação real:

- confirmar a criação física da porta e o plano de referência;
- validar o fit contra um caso conhecido;
- determinar a tolerância final de resíduo;
- validar influência de sweep, malha e perdas.

### 3.6 Assembly em partes

Implementado:

- housing;
- regiões de ar separadas;
- um ressonador por polo;
- íris separadas;
- input/output probes;
- parafusos de sintonia separados;
- origem rastreável de cada dimensão;
- plano HFSS Driven Modal;
- validação de duas portas;
- serviço para criar e salvar o design real.

Cross couplings não são aproximados silenciosamente por íris inline. O assembly é bloqueado até que exista uma realização física explícita.

### 3.7 CLI e CI

Implementado:

```text
hfss-fd3d eigenmode
hfss-fd3d external-q
hfss-fd3d assembly-plan
```

CI:

- Windows;
- Python 3.14;
- PyAEDT instalado;
- compileall;
- pytest;
- Ruff crítico;
- artefato de log do pytest.

## 4. Arquitetura alvo

```text
web / CLI / futuro workspace de projetos
            |
            v
services.fd3d*
            |
            +-- project_factory
            +-- workflow gates
            +-- component study plans
            +-- real HFSS runners
            +-- approval
            +-- mapping
            +-- assembly
            +-- future matrix extraction
            +-- future optimizer
            |
            v
PyAedtAdapter / HFSS 2026.1
```

## 5. Próximas fases

### Fase A — Validação real dos componentes

1. executar ressonador isolado;
2. revisar campos e Q;
3. executar par acoplado;
4. revisar paridade e sinal;
5. executar external Q;
6. revisar referência de porta e fit;
7. aprovar curvas;
8. armazenar artefatos.

Critério de saída: três famílias de curva aprovadas e reproduzíveis.

### Fase B — Realizações físicas adicionais

Implementar bibliotecas para:

- cross coupling elétrico;
- cross coupling magnético;
- source-load coupling;
- triplets;
- quadruplets;
- folded topology;
- non-resonating nodes;
- waveguide;
- SIW;
- planar;
- dielectric resonator.

Cada componente deve possuir receita paramétrica, interfaces, limites, plano de estudo, campos esperados, validação e curva aprovada.

### Fase C — Matriz equivalente full-wave

Implementar extração real a partir de dados complexos:

- importação Touchstone HFSS/VNA;
- remoção de atraso e plano de referência;
- identificação de polos e zeros;
- fitting racional;
- matriz equivalente;
- alinhamento de topologia;
- comparação com matriz alvo;
- incerteza e resíduos.

O método atual de inicialização por características da resposta não será tratado como extração final.

### Fase D — Otimização dirigida pela matriz

Implementar:

- vetor de erro da matriz;
- Jacobiano dimensão-acoplamento;
- perturbações HFSS;
- trust-region;
- space mapping;
- moving mesh quando disponível;
- cache por hash;
- rollback;
- limites físicos;
- análise de convergência.

### Fase E — VNA e tuning físico

Implementar:

- aquisição calibrada;
- de-embedding;
- matriz extraída de medição;
- sensitividades de parafusos;
- ordem de ajuste;
- histórico de movimentos;
- validação após cada passo;
- comparação HFSS/VNA;
- assinatura de liberação.

### Fase F — Interface de projetos

Criar workspace dedicado com árvore do projeto, specification editor, matriz/topologia, component library, study manager, curvas, approval review, assembly viewer, jobs HFSS, comparison, optimizer, VNA tuning, artifacts e revisions.

A interface não deve concentrar lógica física. Ela consome serviços testáveis.

## 6. Critérios globais de qualidade

- nenhum solve longo na thread HTTP principal;
- um desktop AEDT controlado por processo;
- jobs serializados por sessão;
- resultados imutáveis e versionados;
- nenhum dado sintético promovido a engenharia;
- nenhuma extrapolação silenciosa;
- nenhuma troca modal silenciosa;
- nenhum cross coupling sem realização física;
- nenhum projeto liberado sem evidência;
- compatibilidade de projetos antigos;
- testes offline e testes reais opt-in separados.

## 7. Protocolo real

O roteiro detalhado está em:

```text
docs/fd3d_real_hfss_validation_protocol.md
```

## 8. Estado de validação

A branch possui validação automatizada de contratos e matemática. Nenhum solve real do AEDT/HFSS foi executado nesta sessão. O PR deve permanecer draft até que os estudos reais previstos no protocolo sejam concluídos e as primeiras curvas sejam aprovadas.
