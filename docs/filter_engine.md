# Real Filter Engine

O motor introduzido em 0.3.0 e mantido em 0.4.0 substitui as curvas
demonstrativas por uma cadeia numerica
reprodutivel baseada em prototipos analogicos, transformacoes de frequencia,
rede de duas portas e escalamento fisico.

Implementacao:

- `src/hfss_vna_bridge/engines/filter_engine.py`
- `src/hfss_vna_bridge/services/synthesis.py`

Bibliotecas:

- NumPy para algebra vetorial e derivadas;
- SciPy Signal para polos, zeros, ganho e transformacoes analogicas.

Referencia oficial do SciPy:

- https://docs.scipy.org/doc/scipy/reference/signal.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.freqs_zpk.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.lp2bp_zpk.html

## Pipeline

```text
Specification
  -> normalized low-pass prototype
  -> frequency transformation
  -> optional finite-zero sections
  -> finite-Q loss
  -> reciprocal two-port S parameters
  -> group delay and power
  -> g values
  -> coupling matrix, Qe and physical coefficients
  -> scaled lumped elements
```

## Return Loss and Ripple

Para um prototipo Chebyshev, o ripple de insercao nao e igual ao return loss.
O motor converte:

```text
epsilon^2 = 1 / (10^(RL/10) - 1)
Rp_dB = 10 log10(1 + epsilon^2)
```

Exemplo:

```text
RL = 25 dB
Rp = 0.013755 dB
```

Esse ripple e fornecido a `scipy.signal.cheb1ap`.

## Familias

| Familia | SciPy | Uso |
| --- | --- | --- |
| Chebyshev I | `cheb1ap` | Ripple controlado por return loss |
| Butterworth | `buttap` | Magnitude maximamente plana |
| Bessel | `besselap(norm="mag")` | Fase/atraso mais regular |
| Elliptic | `ellipap` | Ripple e atenuacao de stopband |

## Transformacoes

Os prototipos normalizados sao transformados por:

- BPF: `lp2bp_zpk`;
- BSF: `lp2bs_zpk`;
- LPF: `lp2lp_zpk`;
- Multi: composicao normalizada de dois canais BPF.

As frequencias sao sempre convertidas de GHz para Hz e depois para rad/s.
`freqs_zpk` avalia a funcao:

```text
H(jw) = k product(jw - zi) / product(jw - pi)
```

## Parametros S

O prototipo fornece o `S21` complexo ideal. Para uma rede reciproca e lossless:

```text
|S11| = sqrt(1 - |S21|^2)
S22 = S11 com a fase reciproca correspondente
```

O motor limita ganho numerico acima de 1 antes dessa conversao. Sem Q finito,
o teste automatizado confirma:

```text
|S11|^2 + |S21|^2 = 1
```

## Group Delay

O atraso e calculado da fase complexa, nao de uma curva artificial:

```text
tau = -d unwrap(angle(S21)) / dw
```

O backend converte segundos para ns apenas no payload da UI.

## Q Descarregado

Quando `unloaded_q` e finito, a perda estimada do prototipo narrowband e:

```text
IL_dB = 4.343 sum(g1..gN) / (Qu * FBW)
FBW = bandwidth / f0
```

Essa perda reduz `S21`; a diferenca de potencia representa dissipacao e nao e
convertida artificialmente em reflexao.

## Valores g

Butterworth:

```text
gk = 2 sin((2k - 1) pi / (2N))
```

Chebyshev usa a recorrencia classica com `beta`, `gamma`, `ak` e `bk`. Para
ordem 4, RL 25 dB, o motor produz uma matriz normalizada com:

```text
MS1 ~= 1.1522
M12 ~= 1.0409
M23 ~= 0.7715
```

Esses valores sao calculados; nao sao constantes no frontend.

## Matriz de Acoplamento

Para a topologia inline:

```text
M(i,i+1) = 1 / sqrt(gi * g(i+1))
```

Parametros fisicos narrowband:

```text
Qe_input  = g0*g1 / FBW
Qe_output = gN*g(N+1) / FBW
K(i,i+1)  = FBW / sqrt(gi*g(i+1))
```

O payload retorna simultaneamente:

- matriz normalizada;
- Q externo;
- coeficientes entre ressonadores;
- topologia;
- valores g.

## Zeros Finitos

Cada zero solicitado adiciona uma secao notch analogica de segunda ordem:

```text
Htz(s) = (s^2 + wz/Qz*s + wz^2) / (s^2 + wz/Qp*s + wz^2)
Qz = Qp * 10^(depth/20)
```

Isso cria um zero finito, estavel e de profundidade controlada. A matriz recebe
uma estimativa inicial de acoplamento triplet:

```text
Mx ~= -(Mi,i+1 * Mi+1,i+2) / Omega_zero
```

Importante: essa estimativa e um ponto inicial fisico, nao uma sintese Cameron
completa para topologias arbitrarias. O payload identifica explicitamente
`triplet-initial-estimate`. Uma fase futura pode usar otimizacao de matriz ou
sintese polinomial generalizada sem alterar o contrato.

## Elementos L/C

O motor retorna uma realizacao lumped escalada para `impedance_ohm`.

Para BPF:

```text
series: L = R0*g/Dw
        C = Dw/(R0*g*w0^2)

shunt:  C = g/(R0*Dw)
        L = R0*Dw/(g*w0^2)
```

Transformacoes equivalentes sao usadas para LPF e BSF. `MULTI` nao retorna uma
rede lumped unica porque a composicao possui dois canais.

## Validacao Automatizada

`tests/test_filter_engine.py` verifica:

- RL Chebyshev de 25 dB;
- valores de acoplamento de quarta ordem;
- conservacao de potencia;
- perda maior com Q finito;
- BPF, BSF, LPF e MULTI;
- profundidade de zero finito;
- presenca de Qe, coeficientes e elementos.

## Limites

- os elementos lumped sao um prototipo, nao geometria HFSS;
- dispersao real de cavidades exige extracao EM;
- multi-banda ainda usa composicao de canais;
- matrizes com muitos zeros exigem sintese/otimizacao generalizada;
- tolerancias de fabricacao pertencem ao modulo Monte Carlo.
