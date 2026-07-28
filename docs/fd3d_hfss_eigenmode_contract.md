# Contrato obrigatorio de caracterizacao Eigenmode no HFSS

## Regra fundamental

Toda caracterizacao de frequencia de ressonancia, modos espurios, fator de
qualidade e acoplamento entre cavidades deve ser executada no **solver Eigenmode
do Ansys HFSS**.

A aplicacao nao pode produzir curvas de engenharia por formula sintetica,
emulacao ou backend simulado.

O backend simulado pode existir somente para testes de contrato de software e
nunca pode produzir um resultado elegivel para aprovacao.

## Backend aceito

```text
PyAedtAdapter conectado
state.backend == "pyaedt"
HFSS solution_type == "Eigenmode"
setup_type == "HFSSEigen"
```

Qualquer outro backend deve falhar explicitamente.

## Fluxo de um estudo

Para cada estudo de componente:

1. validar o plano e os limites da variavel;
2. criar um design HFSS Eigenmode separado;
3. criar variaveis de design com unidades;
4. gerar a geometria parametrica do componente;
5. confirmar ausencia de portas de excitacao;
6. configurar o setup `HFSSEigen`;
7. resolver cada variacao no HFSS;
8. extrair `Eigen Modes` e `Eigen Q`;
9. registrar frequencias, Q, variacao, design, setup e arquivos;
10. executar tracking modal;
11. gerar curva ainda nao aprovada;
12. exigir revisao de campos e aprovacao humana.

## Setup inicial

Propriedades controladas:

```text
MinimumFrequency
NumModes
ConvergeOnRealFreq = True
MaximumPasses
MinimumPasses
MaxDeltaFreq
```

O sistema deve registrar os valores reais usados em cada solve.

## Ressonador isolado

Resultado primario:

```text
f_r = F(x)
```

Resultados auxiliares:

- Q de cada modo;
- modos espurios;
- separacao do modo alvo;
- convergencia;
- identificacao modal;
- energia por regiao quando disponivel.

## Par de cavidades

Para os dois modos rastreados do par:

```text
k = s * (f_high^2 - f_low^2) / (f_high^2 + f_low^2)
```

O split modal fornece apenas a magnitude. O sinal `s` deve ser determinado por:

- topologia eletrica;
- paridade dos campos;
- fase relativa;
- revisao do engenheiro.

A aplicacao nao deve deduzir o sinal apenas pela ordem das frequencias.

## Perdas e Q

O padrao inicial usa metais com condutividade finita. `Perfect E` somente pode
ser ativado explicitamente para um estudo lossless.

Uma curva de Q obtida com PEC nao pode ser apresentada como Q fisico de
fabricacao.

## Tracking modal

Camadas previstas:

1. ordem inicial por frequencia;
2. continuidade de frequencia;
3. continuidade de Q;
4. energia por objeto/regiao;
5. correlacao de campos;
6. MAC;
7. classificacao de simetria/paridade.

Se houver mode crossing ambiguo, o estudo deve ser marcado como ambiguo e a
curva nao pode ser aprovada automaticamente.

## Aprovacao

Um resultado HFSS deve nascer com:

```text
eligible_for_approval = true
approved = false
```

A aprovacao exige:

- solve HFSS concluido;
- convergencia aceitavel;
- identificacao do modo alvo;
- ausencia de crossing nao resolvido;
- revisao de paridade para estudos de coupling;
- curva dentro do intervalo caracterizado;
- nenhuma extrapolacao;
- rastreabilidade ao projeto AEDT.

## Qe

O acoplamento externo `Q_e` nao deve ser extraido do estudo Eigenmode de forma
improvisada. Ele tera um estudo driven/modal proprio, com porta e metodologia
validada.

## Testes reais opt-in

```text
HFSS_FILTER_REAL_AEDT=1
HFSS_FILTER_REAL_SOLVE=1
```

Casos obrigatorios:

1. cavidade isolada em tres alturas;
2. repetibilidade da frequencia;
3. repetibilidade de Q;
4. par com tres aberturas;
5. monotonicidade de `|k|`;
6. campos par e impar;
7. modo espurio proximo;
8. mode crossing intencional;
9. cancelamento;
10. persistencia dos resultados.

Nenhuma documentacao deve declarar validacao Eigenmode real antes da execucao
desses testes em AEDT/HFSS licenciado.
