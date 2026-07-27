# Contrato VNA

O VNA e controlado por uma interface comum. O backend real usa PyVISA e comandos
SCPI genericos.

## Interface

```python
connect()
reset()
configure_sweep(config)
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

Abre um recurso VISA e envia comandos SCPI.

Exemplo:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/connect `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"pyvisa","resource":"TCPIP0::192.168.0.50::inst0::INSTR","timeout_ms":30000}'
```

## Comandos SCPI Genericos

O adaptador atual usa:

- `*IDN?`
- `*RST`
- `*CLS`
- `SENS1:FREQ:STAR`
- `SENS1:FREQ:STOP`
- `SENS1:SWE:POIN`
- `SENS1:BAND`
- `SOUR1:POW`
- `FORM:DATA ASCII`
- `INIT1:IMM;*WAI`
- `CALC1:DATA? SDATA`

Esse conjunto cobre muitos VNAs, mas pode exigir ajustes por fabricante.

## Adaptadores por Fabricante

Quando um VNA exigir dialeto SCPI especifico, crie uma subclasse de
`PyVisaVnaAdapter` e sobrescreva os metodos necessarios:

- `configure_sweep`
- `single_sweep`
- `_parse_sdata`

Mantenha o contrato de saida como `list[NetworkPoint]`.

## Touchstone

`save_touchstone(path)` escreve `.s2p` em:

```text
# Hz S RI R 50
```

Se nao houver sweep anterior, o adaptador executa `single_sweep()` antes de
salvar.

