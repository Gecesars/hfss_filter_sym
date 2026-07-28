# FD3D Project Platform — Protocolo de validação real no HFSS 2026.1

## Objetivo

Validar progressivamente a plataforma FD3D do `hfss_filter_sym` utilizando o solver real do Ansys HFSS. Nenhuma curva de caracterização, dimensão mapeada ou montagem completa deve ser aprovada apenas por testes offline.

A ordem deste protocolo é obrigatória:

1. ambiente AEDT/PyAEDT;
2. ressonador isolado em Eigenmode;
3. par de ressonadores em Eigenmode;
4. acoplamento externo em Driven Modal;
5. aprovação das curvas;
6. mapping elétrico para físico;
7. assembly do filtro em partes;
8. solve Driven Modal do filtro completo;
9. extração da matriz equivalente;
10. tuning com HFSS e VNA.

## 1. Preparação do ambiente

Requisitos:

- Windows;
- Python 3.14;
- AEDT 2026 R1;
- licença HFSS válida;
- PyAEDT compatível com Python 3.14 e AEDT 2026 R1;
- branch `feature/fd3d-project-platform`;
- instalação com extras AEDT.

```powershell
uv python install 3.14
uv venv --python 3.14
.\.venv\Scripts\python -m pip install -e ".[dev,aedt]"
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check src tests --select E9,F63,F7,F82
```

Confirmar:

- AEDT detectado;
- versão `2026.1`;
- conexão gRPC válida;
- projeto de saída gravável;
- sessão reutilizada sem processo órfão;
- backend reportado como `pyaedt`.

## 2. Caracterização do ressonador isolado

### 2.1 Plano

Gerar um plano `combline_resonator_eigenmode` para variar inicialmente:

```text
resonator_height_mm
```

Usar no mínimo sete pontos. Para a primeira validação recomenda-se nove pontos distribuídos dentro dos limites do componente.

O plano não pode conter portas.

### 2.2 Execução

```powershell
hfss-fd3d eigenmode `
  --plan data\fd3d\resonator_height_plan.json `
  --output data\fd3d\resonator_height_result.json `
  --version 2026.1 `
  --new-desktop
```

Também é possível anexar a uma sessão gRPC já aberta usando `--port` ou `--pid`.

### 2.3 Verificações geométricas antes do solve

- somente uma cavidade;
- somente um ressonador;
- distância capacitiva superior positiva;
- materiais corretos;
- ausência de porta;
- solution type `Eigenmode`;
- setup `HFSSEigen`;
- frequência mínima coerente;
- número de modos maior que um;
- objetos metálicos separados e rastreáveis.

### 2.4 Verificações do resultado

Para cada variação registrar:

- frequência de cada modo;
- Q de cada modo;
- convergência;
- número de passes;
- variável geométrica;
- projeto, design e setup;
- distribuição de campo do modo selecionado;
- primeiro modo espúrio relevante.

A frequência fundamental deve variar fisicamente de forma consistente com a altura do ressonador. Uma curva não monotônica não pode ser invertida sem segmentação e revisão.

## 3. Caracterização do acoplamento interno

### 3.1 Plano

Usar `combline_pair_eigenmode` e variar:

```text
iris_width_mm
```

Os dois ressonadores devem ser geometricamente idênticos. Alterar somente a dimensão de acoplamento em cada estudo.

### 3.2 Execução

```powershell
hfss-fd3d eigenmode `
  --plan data\fd3d\iris_width_plan.json `
  --output data\fd3d\iris_width_result.json `
  --version 2026.1 `
  --new-desktop `
  --lower-mode-index 0 `
  --upper-mode-index 1 `
  --coupling-sign 1
```

### 3.3 Fórmula

A magnitude inicial é calculada por:

\[
|k|=\frac{f_+^2-f_-^2}{f_+^2+f_-^2}
\]

O split modal não determina o sinal. O sinal somente pode ser aprovado após inspeção dos campos par e ímpar e coerência com a topologia física.

### 3.4 Verificações

- identificar corretamente o par de modos acoplados;
- conferir campos nos dois ressonadores;
- detectar mode crossing;
- não confundir modo espúrio com o par fundamental;
- verificar continuidade modal entre variações;
- confirmar monotonicidade local de `k(iris_width)`;
- registrar o sinal aprovado e sua evidência.

## 4. Caracterização do acoplamento externo

O acoplamento externo não é extraído por Eigenmode. Ele utiliza um design separado HFSS Driven Modal com uma porta.

### 4.1 Plano

Variar:

```text
probe_depth_mm
```

O plano deve conter:

- cavidade;
- ressonador;
- probe;
- dielétrico coaxial;
- passagem pela parede;
- uma porta;
- sweep discreto suficientemente denso ao redor da ressonância.

### 4.2 Execução

```powershell
hfss-fd3d external-q `
  --plan data\fd3d\external_q_plan.json `
  --output data\fd3d\external_q_result.json `
  --version 2026.1 `
  --new-desktop
```

### 4.3 Ajuste complexo

A plataforma ajusta o modelo:

\[
S_{11}(f)=e^{j[\phi+2\pi(f-f_0)\tau]}
\left[
1-\frac{d}{1+2jQ_L(f-f_0)/f_0}
\right]
\]

com:

\[
d=\frac{2Q_L}{Q_e}
\]

portanto:

\[
Q_e=\frac{2Q_L}{d}
\]

Também é calculado:

\[
\frac{1}{Q_L}=\frac{1}{Q_i}+\frac{1}{Q_e}
\]

O resultado não deve ser aprovado quando:

- a ressonância estiver fora do sweep;
- o ajuste complexo apresentar resíduo excessivo;
- a referência da porta não tiver sido conferida;
- o sweep não cobrir adequadamente a ressonância;
- houver mais de uma ressonância dominante no intervalo;
- a curva `Qe(probe_depth)` não for invertível no ramo selecionado.

## 5. Aprovação das curvas

### 5.1 Eigenmode

Exige:

- identidade modal revisada;
- campo revisado;
- mode crossing revisado quando sinalizado;
- paridade revisada nos acoplamentos;
- sinal físico ±1;
- evidências anexadas;
- Q mínimo aceitável;
- digest SHA-256 da curva.

### 5.2 External Q

Exige:

- ajuste complexo revisado;
- plano de referência da porta revisado;
- cobertura do sweep revisada;
- resíduo máximo definido;
- Q positivo;
- evidências anexadas;
- digest SHA-256 da curva.

Curvas não aprovadas podem ser visualizadas e comparadas, mas não devem liberar um assembly de engenharia quando `require_approved_curves=true`.

## 6. Mapping elétrico para físico

Mapear:

```text
frequência de cada ressonador -> resonator_height_mm
Mij de cada acoplamento principal -> iris_width_mm
Qe de entrada/saída -> probe_depth_mm
```

Regras:

- extrapolação proibida por padrão;
- usar apenas o ramo monotônico aprovado;
- manter curva e sensibilidade associadas à dimensão;
- preservar sinal elétrico e realização física;
- não mapear cross coupling para uma íris inline automaticamente.

## 7. Assembly do filtro em partes

```powershell
hfss-fd3d assembly-plan `
  --project data\fd3d\project.json `
  --mapping data\fd3d\mapping.json `
  --output data\fd3d\assembly_plan.json `
  --require-characterized-external-q
```

Conferir no plano:

- um housing;
- uma região de ar por cavidade;
- um ressonador por polo;
- uma íris por acoplamento principal;
- dois probes;
- dois ports;
- parafusos de sintonia separados;
- origem de cada dimensão;
- curva usada;
- sensibilidade local;
- ausência de extrapolação;
- lista explícita de acoplamentos ainda não realizados.

O assembly deve permanecer bloqueado quando existir cross coupling sem geometria física definida.

## 8. Build e solve do filtro completo

Criar um design HFSS Driven Modal separado do Eigenmode.

Antes do solve:

- validar duas portas;
- validar objetos e operações booleanas;
- verificar contato e referência dos probes;
- conferir íris;
- conferir materiais e perdas;
- verificar frequência do setup;
- salvar o projeto.

Depois do solve:

- exportar Touchstone;
- registrar `S11`, `S21`, `S12`, `S22` complexos;
- registrar convergência;
- comparar com a resposta da matriz alvo;
- identificar deslocamento dos polos e zeros;
- registrar tempo e recursos de solução.

## 9. Critérios mínimos de aceite da fase inicial

### Ressonância

- curva física consistente;
- sem troca modal não explicada;
- erro de repetibilidade documentado;
- campos e Q revisados.

### Acoplamento interno

- split modal corretamente identificado;
- sinal revisado;
- curva monotônica ou ramo segmentado;
- zero uso de extrapolação no assembly.

### External Q

- fit complexo convergente;
- resíduo abaixo do limite definido;
- referência de porta validada;
- `Qe(probe_depth)` invertível.

### Filtro completo

- geometria criada em partes;
- duas portas válidas;
- solve concluído;
- Touchstone exportado;
- diferenças em relação à matriz alvo quantificadas;
- nenhuma dimensão sem origem rastreável, exceto itens explicitamente marcados como seed provisório.

## 10. Evidências a arquivar

Para cada execução real guardar:

```text
project.aedt
plan.json
result.json
curve.json
approval.json
mapping.json
assembly_plan.json
Touchstone
convergence
capturas de campo
capturas da geometria
logs PyAEDT
versão AEDT
versão PyAEDT
commit Git
```

Nenhuma execução real foi realizada pelo CI. O CI valida contratos, matemática, serialização e chamadas mockadas; a licença e o solver HFSS são necessários para concluir este protocolo.
