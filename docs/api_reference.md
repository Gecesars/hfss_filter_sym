# API Reference

Base URL padrao:

```text
http://127.0.0.1:8765
```

Todas as rotas usam JSON, exceto `GET /health`, `GET /aedt/designs`,
`GET /aedt/variables`, `GET /vna/status` e os documentos automaticos do FastAPI.

## Health

### `GET /health`

Retorna versao e estado dos adaptadores.

Exemplo:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Resposta:

```json
{
  "ok": true,
  "version": "0.1.0",
  "aedt": {"connected": false, "backend": "simulated", "resource": null, "detail": null},
  "vna": {"connected": false, "backend": "simulated", "resource": "SIM::VNA", "detail": null}
}
```

## AEDT/HFSS

### `POST /aedt/session`

Cria ou troca o adaptador AEDT.

Payload simulado:

```json
{
  "backend": "simulated",
  "project_path": null,
  "design_name": "OfflineDesign",
  "new_desktop": false,
  "non_graphical": false
}
```

Payload PyAEDT:

```json
{
  "backend": "pyaedt",
  "project_path": "D:\\simulation\\painel triband.aedt",
  "design_name": "HFSSDesign1",
  "new_desktop": false,
  "non_graphical": false
}
```

### `GET /aedt/designs`

Lista designs encontrados na sessao AEDT ativa.

### `GET /aedt/variables`

Retorna variaveis de projeto/design como mapa `nome -> valor`.

### `POST /aedt/variables`

Atualiza variaveis.

Payload:

```json
{
  "variables": {
    "arm_scale_a": 1.02,
    "dist_refletor": "21mm"
  }
}
```

### `POST /aedt/analyze`

Executa analise e opcionalmente exporta Touchstone.

Payload:

```json
{
  "setup_name": "Setup1",
  "sweep_name": "Sweep1",
  "output_touchstone": "D:\\simulation\\hfss_export.s2p"
}
```

Resposta:

```json
{
  "project": "D:\\simulation\\painel triband.aedt",
  "design": "HFSSDesign1",
  "setup": "Setup1",
  "sweep": "Sweep1",
  "touchstone": "D:\\simulation\\hfss_export.s2p"
}
```

## VNA

### `POST /vna/connect`

Conecta ou troca o adaptador VNA.

Payload simulado:

```json
{
  "backend": "simulated",
  "resource": "SIM::VNA",
  "timeout_ms": 30000
}
```

Payload PyVISA:

```json
{
  "backend": "pyvisa",
  "resource": "TCPIP0::192.168.0.50::inst0::INSTR",
  "timeout_ms": 30000
}
```

### `GET /vna/status`

Retorna estado do VNA ativo.

### `POST /vna/reset`

Envia reset ao VNA ativo e restaura a configuracao de sweep padrao.

### `POST /vna/configure-sweep`

Configura faixa, numero de pontos, IFBW e potencia.

Payload:

```json
{
  "start_hz": 600000000,
  "stop_hz": 1100000000,
  "points": 201,
  "ifbw_hz": 1000,
  "power_dbm": -10
}
```

### `POST /vna/single-sweep`

Executa um sweep unico e retorna pontos de rede.

Cada ponto contem:

- `freq_hz`
- `s11_real`, `s11_imag`
- `s21_real`, `s21_imag`
- `s12_real`, `s12_imag`
- `s22_real`, `s22_imag`

### `POST /vna/save-touchstone`

Salva a ultima medicao em `.s2p`. Se ainda nao houve medicao, executa uma antes.

Payload:

```json
{
  "path": "D:\\simulation\\vna_measurement.s2p"
}
```

## Aliases de Compatibilidade

Aliases para integracoes simples:

- `POST /connect` -> `POST /vna/connect`
- `GET /status` -> `GET /vna/status`
- `POST /reset` -> `POST /vna/reset`
- `POST /singlesweep` -> `POST /vna/single-sweep`
- `POST /savetracedata` -> `POST /vna/save-touchstone`
- `POST /setfrequency`
- `POST /setifbw`
- `POST /setpower`

### `POST /setfrequency`

Aceita `start_hz`/`stop_hz` ou `center_hz`/`span_hz`.

```json
{
  "center_hz": 850000000,
  "span_hz": 500000000
}
```

### `POST /setifbw`

```json
{"value": 1000}
```

### `POST /setpower`

```json
{"value": -10}
```

