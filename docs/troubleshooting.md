# Troubleshooting

## Python 3.14 nao encontrado

Instale com:

```powershell
uv python install 3.14
uv venv --python 3.14
```

Confirme:

```powershell
.\.venv\Scripts\python --version
```

## Porta 8765 ocupada

Use outra porta:

```powershell
.\.venv\Scripts\python -m hfss_vna_bridge --port 8766
```

## PyAEDT nao instalado

Instale o extra:

```powershell
.\.venv\Scripts\python -m pip install -e ".[aedt]"
```

## AEDT nao abre

Verifique:

- Ansys Electronics Desktop instalado;
- licenca disponivel;
- caminho do `.aedt` correto;
- `design_name` existente;
- permissao de escrita na pasta do projeto;
- se ja existe uma sessao AEDT travada.

## Variavel HFSS nao altera

Verifique:

- nome exato retornado por `/aedt/variables`;
- unidade exigida pelo projeto, como `mm`, `GHz` ou `deg`;
- se a variavel e de projeto ou de design;
- se a expressao e valida no AEDT.

## PyVISA nao instalado

Instale:

```powershell
.\.venv\Scripts\python -m pip install -e ".[vna]"
```

## VNA nao conecta

Verifique:

- VISA runtime instalado;
- IP ou resource string correto;
- instrumento na mesma rede;
- firewall local;
- timeout maior;
- resposta a `*IDN?` em um utilitario VISA.

Exemplos de resource:

```text
TCPIP0::192.168.0.50::inst0::INSTR
USB0::0x2A8D::0x5C18::MY00000000::INSTR
GPIB0::16::INSTR
```

## Sweep retorna formato inesperado

O backend `pyvisa` espera `CALC1:DATA? SDATA` em ASCII com pares real/imaginario.
Se o VNA retornar outro formato, crie um adaptador especifico por fabricante.

## GitHub push falha

Confirme remoto:

```powershell
git remote -v
```

Configure:

```powershell
git remote add origin https://github.com/Gecesars/hfss_filter_sym.git
```

Autentique:

```powershell
gh auth login
```

Envie:

```powershell
git push -u origin main
```

