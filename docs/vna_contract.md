# Contrato VNA

O VNA e controlado por uma interface comum. O backend real usa PyVISA, um
contrato SCPI comum e perfis por fabricante.

## Interface

```python
connect()
close()
reset()
capabilities()
query_errors()
configure_sweep(config)
set_sweep_type(type)
set_continuous(enabled)
configure_marker(marker, frequency_hz)
marker_value(marker)
single_sweep()
save_touchstone(path)
```

## Configuracao de Sweep

```json
{
  "start_hz": 600000000,
  "stop_hz": 1100000000,
  "points": 201,
  "ifbw_hz": 1000,
  "power_dbm": -10
}
```

Regras:

- `start_hz` deve ser positivo.
- `stop_hz` deve ser maior que `start_hz`.
- `points` deve ser maior ou igual a 2.
- `ifbw_hz` deve ser positivo.

## Backends

### `simulated`

Gera uma resposta deterministica com um notch sintetico na banda configurada.
Serve para desenvolver clientes, validar a API e testar escrita Touchstone.

### `pyvisa`

Enumera ou abre um recurso VISA, identifica o instrumento e seleciona o perfil
SCPI.

Exemplo:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/connect `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"pyvisa","brand":"KEYSIGHT","resource":"TCPIP0::192.168.0.50::inst0::INSTR","timeout_ms":30000,"channel":1}'
```

Descoberta:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/vna/resources
```

## Comandos SCPI Genericos

O adaptador atual usa os comandos abaixo, substituindo `<ch>` pelo canal
selecionado:

- `*IDN?`
- `*RST`
- `*CLS`
- `SENS<ch>:FREQ:STAR`
- `SENS<ch>:FREQ:STOP`
- `SENS<ch>:SWE:POIN`
- `SENS<ch>:SWE:TYPE`
- `SENS<ch>:BAND`
- `SOUR<ch>:POW`
- `INIT<ch>:CONT OFF`
- `FORM:DATA ASCII`
- `INIT<ch>:IMM`
- `*OPC?`
- `SENS<ch>:FREQ:DATA?`
- `CALC<ch>:DATA? SDATA`
- `CALC<ch>:MARK<n>:X`
- `CALC<ch>:MARK<n>:Y?`
- `SENS<ch>:SWE:TIME?`
- `SYST:ERR?`

Para cada aquisicao, o adaptador define e seleciona quatro medicoes:

```text
S11, S21, S12, S22
```

Cada resposta SDATA contem pares real/imaginario corrigidos. O eixo de estimulo
e lido do equipamento; se o comando nao estiver disponivel, o adaptador
reconstroi o eixo linear ou logaritmico pela configuracao conhecida.

## Adaptadores por Fabricante

`adapters/vna/profiles.py` contem:

- `KEYSIGHT`: `CALC:PAR:DEF:EXT`;
- `ROHDE_SCHWARZ`: `CALC:PAR:SDEF`;
- `COPPER_MOUNTAIN`: `CALC:PAR:DEF`;
- `GENERIC`: fallback SCPI.

O perfil e escolhido pela opcao `brand` ou por `*IDN?`. Se a definicao inicial
falhar, os demais formatos conhecidos sao tentados de forma controlada. Novos
fabricantes devem adicionar um `ScpiProfile`; nao e necessario duplicar o
adaptador inteiro.

## Estado e Erros

`GET /api/vna/capabilities` retorna identidade, perfil, canal e operacoes.
`GET /api/vna/errors` drena `SYST:ERR?` ate `0,"No error"` ou 32 registros.
`POST /api/vna/close` fecha instrumento e ResourceManager.

`connect()` nao liga RF, nao executa preset e nao inicia sweep. Essas operacoes
permanecem explicitas.

## Touchstone

`save_touchstone(path)` escreve `.s2p` em:

```text
# Hz S RI R 50
```

Se nao houver sweep anterior, o adaptador executa `single_sweep()` antes de
salvar.

O writer local preserva a ordem Touchstone de duas portas:

```text
frequency S11 S21 S12 S22
```

## Validacao

O teste `tests/test_vna_pyvisa.py` usa um ResourceManager e instrumento mockados.
Ele verifica identidade Keysight, comandos de definicao, eixo, sweep time, fila
de erros, fechamento e valores distintos para os quatro parametros.

Hardware real nao e acessado pelos testes automatizados. A validacao em bancada
deve usar carga ou DUT adequado e limites seguros de potencia.
