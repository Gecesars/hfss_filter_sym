# API Reference

Base URL padrao:

```text
http://127.0.0.1:8765
```

O servidor padrao e Flask. Ele expoe uma interface JS em `/`, a superficie
compativel com SymMatrix e aliases REST. A API FastAPI anterior continua
disponivel com `--server fastapi`.

Todas as rotas de comando usam JSON.

## Filter Synthesis

### `POST /api/synthesis/calculate`

Executa a sintese numerica de prototipo sem acessar AEDT ou VNA.

Payload:

```json
{
  "filter_type": "BPF",
  "response_family": "chebyshev",
  "order": 4,
  "return_loss_db": 25,
  "f0_ghz": 1.0,
  "bandwidth_ghz": 0.05,
  "start_ghz": 0.875,
  "stop_ghz": 1.125,
  "shift_mhz": 0,
  "delta_bandwidth_mhz": 0,
  "unloaded_q": null,
  "impedance_ohm": 50,
  "input_power_w": 0.1,
  "points": 401,
  "dispersion": "symmetric",
  "zeros": [
    {"frequency_ghz": 1.08, "depth_db": 60}
  ]
}
```

Campos obrigatorios na pratica sao normalizados com defaults. Limites:

- `filter_type`: `BPF`, `BSF`, `LPF` ou `MULTI`;
- `order`: 1 a 12;
- `points`: 101 a 2001;
- frequencias e largura de banda: positivas;
- `stop_ghz`: maior que `start_ghz`.

Resposta:

```json
{
  "status": 0,
  "ok": true,
  "engine": {
    "name": "coupled-resonator-prototype",
    "numerics": "NumPy/SciPy analog ZPK",
    "simulated": false
  },
  "specification": {
    "filter_type": "BPF",
    "order": 4,
    "effective_f0_ghz": 1.0,
    "effective_bandwidth_ghz": 0.05
  },
  "series": {
    "frequencies_ghz": [],
    "s11_db": [],
    "s21_db": [],
    "s22_db": [],
    "group_delay_ns": [],
    "power_w": []
  },
  "matrix": {
    "labels": ["S", "1", "2", "3", "4", "L"],
    "values": [],
    "unit": "normalized"
  },
  "prototype": {},
  "elements": [],
  "topology": {
    "nodes": [],
    "edges": []
  },
  "dispersion": {},
  "summary": {}
}
```

Payload invalido retorna HTTP 400 e:

```json
{"status": -400, "ok": false, "message": "validation message"}
```

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
  "version": "0.4.0",
  "aedt": {"connected": false, "backend": "simulated", "resource": null, "detail": null},
  "vna": {"connected": false, "backend": "simulated", "resource": "SIM::VNA", "detail": null}
}
```

## AEDT/HFSS

### `GET /api/aedt/installations`

Detecta versoes instaladas e sessoes `ansysedt.exe` com porta gRPC.

### `POST /api/aedt/sessioninfo`

Retorna versao, PID, porta, projeto, design, setups e sweeps da sessao ativa.

### `POST /api/aedt/release`

Libera a sessao. `close_projects` e `close_desktop` devem ser `false` para uma
sessao anexada e `true` para uma sessao criada pelo servidor.

### Superficie SymMatrix Flask

- `POST /aedt/openproject`
- `POST /aedt/getdesigns`
- `POST /aedt/setactivedesign`
- `POST /aedt/getvariables`
- `POST /aedt/getvariablesvalue`
- `POST /aedt/setvariablesvalue`
- `POST /aedt/evaluatedimension`
- `POST /aedt/evaluatedimensionnos2p`

Exemplo:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/openproject `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"simulated","design_name":"OfflineDesign"}'
```

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/setvariablesvalue `
  -Method Post -ContentType "application/json" `
  -Body '{"names":["arm_scale_a"],"values":[1.04]}'
```

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/evaluatedimension `
  -Method Post -ContentType "application/json" `
  -Body '{"names":["dist_refletor"],"dimension":["22mm"],"output_touchstone":"data\\hfss.s2p"}'
```

### Aliases REST

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
  "project_path": "D:\\dev\\HFSS_AUTO\\painel triBand.aedt",
  "version": "2026.1",
  "machine": "localhost",
  "port": 49152,
  "new_desktop": false,
  "non_graphical": false,
  "remove_lock": false
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
  "cores": 4,
  "blocking": true,
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

### Superficie SymMatrix Flask

- `POST /status`
- `POST /connect`
- `POST /close`
- `POST /reset`
- `POST /clearerrmsg`
- `POST /initialize2`
- `POST /loadpreset`
- `POST /setfrequency`
- `POST /setifbw`
- `POST /setpower`
- `POST /setsweeppoints`
- `POST /setsweeptype`
- `POST /setcontinoussweep`
- `POST /settrace`
- `POST /settracestatus`
- `POST /setmarkers`
- `POST /setautoscaletrace`
- `POST /getsweeptime`
- `POST /getmarkeryvalue`
- `POST /savetracedata`
- `POST /deleteallmarkers`
- `POST /deletetraces`
- `POST /singlesweep`
- `POST /beginbackgroundsweep`
- `POST /endbackgroundsweep`
- `POST /exports2p`

Exemplo:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/connect `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"simulated","brand":"SIM"}'
```

```powershell
Invoke-RestMethod http://127.0.0.1:8765/setfrequency `
  -Method Post -ContentType "application/json" `
  -Body '{"startFreq":0.6,"stopFreq":1.1}'
```

```powershell
Invoke-RestMethod http://127.0.0.1:8765/singlesweep -Method Post
```

### Aliases REST

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

## Multiplexer

### `POST /api/synthesis/multiplexer`

```json
{
  "start_ghz": 0.8,
  "stop_ghz": 1.3,
  "points": 801,
  "channels": [
    {"name": "Low", "f0_ghz": 0.95, "bandwidth_ghz": 0.05, "order": 4},
    {"name": "High", "f0_ghz": 1.15, "bandwidth_ghz": 0.05, "order": 4}
  ]
}
```

Retorna resposta agregada, series por canal, matrizes e topologia de junction.

## Coupling Matrix

### `POST /api/synthesis/matrix-response`

Avalia diretamente uma matriz de acoplamento real editada:

```json
{
  "specification": {
    "filter_type": "BPF",
    "order": 4,
    "return_loss_db": 25,
    "f0_ghz": 1.0,
    "bandwidth_ghz": 0.05,
    "start_ghz": 0.875,
    "stop_ghz": 1.125,
    "points": 401
  },
  "matrix": {
    "labels": ["S", "1", "2", "3", "4", "L"],
    "values": [
      [0, 1.1522, 0, 0, 0, 0],
      [1.1522, 0, 1.0409, 0, 0, 0],
      [0, 1.0409, 0, 0.7715, 0, 0],
      [0, 0, 0.7715, 0, 1.0409, 0],
      [0, 0, 0, 1.0409, 0, 1.1522],
      [0, 0, 0, 0, 1.1522, 0]
    ]
  }
}
```

Retorna as series `s11`, `s21`, `s12` e `s22`, alem das metricas no centro.
O motor usa a formulacao de matriz carregada normalizada. A matriz deve ser
quadrada, simetrica e compatível com `order + 2`.

## Modelagem

### `POST /api/modeling/plan`

Gera preview sem alterar AEDT:

```json
{
  "method": "buildcavityfull3d",
  "recipe": "cavity",
  "name": "FilterA",
  "order": 4,
  "length_mm": 120,
  "width_mm": 50,
  "height_mm": 25,
  "dry_run": true,
  "assign_ports": true,
  "setup_name": "FilterSetup",
  "sweep_name": "FilterSweep",
  "f0_ghz": 1,
  "start_ghz": 0.875,
  "stop_ghz": 1.125
}
```

O mesmo payload pode ser enviado para a rota HFSS correspondente com
`dry_run=false`. Familias: cavity, combline, waveguide, planar, SIW e LPF.

### AEDT operacional

- `POST /api/aedt/configureanalysis`
- `POST /api/aedt/validatedesign`
- `POST /api/aedt/exportresults`
- `POST /api/aedt/stopanalysis`

## Jobs AEDT

### `POST /api/jobs`

```json
{
  "setup_name": "Setup1",
  "sweep_name": "Sweep1",
  "output_touchstone": "D:\\simulation\\hfss.s2p",
  "cores": 8
}
```

### Consulta e cancelamento

- `GET /api/jobs`
- `GET /api/jobs/<id>`
- `POST /api/jobs/<id>/cancel`

Estados: `queued`, `running`, `cancelling`, `completed`, `failed`, `cancelled`.

## Touchstone

### `POST /api/touchstone/import`

```json
{"path": "D:\\simulation\\measurement.s2p"}
```

Aceita RI, MA e DB com unidade Hz/kHz/MHz/GHz.

### `POST /api/analysis/compare`

```json
{
  "reference_path": "D:\\simulation\\hfss.s2p",
  "candidate_path": "D:\\simulation\\vna.s2p"
}
```

Tambem aceita objetos `reference` e `candidate` com `points`.

## Engenharia

### `POST /api/engineering/tuning`

Recebe metricas `target`, `measured` e sensibilidades em Hz/turn ou dB/turn.

### `POST /api/engineering/optimize`

Recebe `specification`, `targets`, `variables`, `max_iterations`, `population`
e `seed`.

### `POST /api/engineering/monte-carlo`

Recebe `specification`, `samples`, `seed`, `tolerances` e `limits`.

### `POST /api/engineering/transmission-line`

`kind` pode ser `microstrip`, `stripline`, `rectangular_waveguide` ou `siw`.

## Projetos

- `GET|POST /api/projects`
- `GET|PUT|DELETE /api/projects/<id>`
- `GET /api/projects/<id>/versions`
- `POST /api/projects/<id>/restore/<revision>`

O formato atual e `hfss-filter-studio-project`, versao 2.

## Biblioteca

- `GET /api/library`
- `GET /api/library/<id>`

O filtro opcional `category` aceita `synthesis`, `cavity` ou `planar`.

## Diagnostico VNA

- `GET /api/vna/resources`
- `GET /api/vna/capabilities`
- `GET /api/vna/errors`
- `POST /api/vna/close`

`POST /api/vna/single-sweep` retorna os quatro parametros complexos de duas
portas.
