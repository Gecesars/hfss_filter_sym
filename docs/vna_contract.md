# Contrato VNA

O VNA e tratado como instrumento SCPI:

- `connect()`
- `reset()`
- `configure_sweep(config)`
- `single_sweep()`
- `save_touchstone(path)`

Configuracao de sweep:

```json
{
  "start_hz": 600000000,
  "stop_hz": 1100000000,
  "points": 201,
  "ifbw_hz": 1000,
  "power_dbm": -10
}
```

O backend `pyvisa` usa comandos SCPI genericos:

- `SENS1:FREQ:STAR`
- `SENS1:FREQ:STOP`
- `SENS1:SWE:POIN`
- `SENS1:BAND`
- `SOUR1:POW`
- `INIT1:IMM;*WAI`
- `CALC1:DATA? SDATA`

Se um modelo especifico exigir comandos diferentes, crie uma subclasse de
`PyVisaVnaAdapter` e sobrescreva apenas os metodos de comando.

