# HFSS VNA Bridge

Aplicacao Python 3.14 original para automatizar AEDT/HFSS e aquisicao de VNA
por uma API HTTP local.

O objetivo do projeto e fornecer uma base propria, documentada e testavel para:

- abrir ou reutilizar projetos AEDT/HFSS;
- listar e alterar variaveis de projeto/design;
- executar analises HFSS e exportar dados Touchstone;
- controlar um VNA por SCPI via PyVISA;
- operar em modo simulado quando AEDT ou hardware nao estiverem disponiveis;
- integrar scripts, GUIs ou otimizadores sem acoplar a regra de negocio ao AEDT.

Este repositorio nao contem codigo fonte recuperado, nomes internos proprietarios,
patches, binarios, licencas, credenciais ou assets de terceiros. A implementacao foi
escrita do zero usando apenas requisitos tecnicos de interoperabilidade.

## Status

- Python: `>=3.14`
- API: FastAPI
- AEDT/HFSS: backend `pyaedt`
- VNA: backend `pyvisa`
- Testes offline: backends `simulated`
- Saida de rede: Touchstone `.s2p`

Validado localmente com:

```powershell
.\.venv\Scripts\python --version
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

## Requisitos

Obrigatorios para desenvolvimento:

- Windows
- `uv`
- Git
- Python 3.14 gerenciado pelo `uv`

Obrigatorios para uso com AEDT/HFSS real:

- Ansys Electronics Desktop instalado
- Licenca AEDT/HFSS valida
- Pacote `pyaedt`

Obrigatorios para uso com VNA real:

- VNA acessivel por LAN/USB/GPIB
- VISA runtime compatavel, como NI-VISA ou Keysight IO Libraries
- Pacote `pyvisa`

## Instalacao Rapida

Na pasta do projeto:

```powershell
uv python install 3.14
uv venv --python 3.14
.\.venv\Scripts\python -m pip install -e ".[dev,aedt,vna]"
```

Para instalar somente o modo simulado:

```powershell
uv python install 3.14
uv venv --python 3.14
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Tambem ha um script equivalente:

```powershell
.\scripts\setup.ps1 -WithHardware
```

## Executar

```powershell
.\.venv\Scripts\python -m hfss_vna_bridge --host 127.0.0.1 --port 8765
```

Ou:

```powershell
.\scripts\run.ps1 -HostName 127.0.0.1 -Port 8765
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Documentacao interativa da API:

- Swagger UI: `http://127.0.0.1:8765/docs`
- OpenAPI JSON: `http://127.0.0.1:8765/openapi.json`

## Estrutura

```text
hfss_vna_bridge/
  docs/
    aedt_contract.md
    api_reference.md
    architecture.md
    originalidade.md
    setup.md
    troubleshooting.md
    vna_contract.md
    workflows.md
  scripts/
    run.ps1
    setup.ps1
  src/hfss_vna_bridge/
    adapters/
      aedt/
      vna/
    api/
    core/
    cli.py
    settings.py
  tests/
  pyproject.toml
  uv.lock
```

## Endpoints Principais

AEDT/HFSS:

- `POST /aedt/session`
- `GET /aedt/designs`
- `GET /aedt/variables`
- `POST /aedt/variables`
- `POST /aedt/analyze`

VNA:

- `POST /vna/connect`
- `GET /vna/status`
- `POST /vna/reset`
- `POST /vna/configure-sweep`
- `POST /vna/single-sweep`
- `POST /vna/save-touchstone`

Aliases de compatibilidade:

- `POST /connect`
- `GET /status`
- `POST /reset`
- `POST /setfrequency`
- `POST /setifbw`
- `POST /setpower`
- `POST /singlesweep`
- `POST /savetracedata`

Veja [docs/api_reference.md](docs/api_reference.md) para payloads completos.

## Uso em Modo Simulado

Conectar VNA simulado:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/connect `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"simulated","resource":"SIM::VNA"}'
```

Configurar sweep:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/configure-sweep `
  -Method Post -ContentType "application/json" `
  -Body '{"start_hz":600000000,"stop_hz":1100000000,"points":101,"ifbw_hz":1000,"power_dbm":-10}'
```

Executar sweep unico:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/single-sweep -Method Post
```

Conectar AEDT simulado:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/session `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"simulated","design_name":"OfflineDesign"}'
```

## Uso com AEDT/HFSS Real

Exemplo para abrir o arquivo do painel triband:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/session `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"pyaedt","project_path":"D:\\simulation\\painel triband.aedt","design_name":"HFSSDesign1","new_desktop":false,"non_graphical":false}'
```

Listar variaveis:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/variables
```

Alterar variaveis:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/variables `
  -Method Post -ContentType "application/json" `
  -Body '{"variables":{"arm_scale_a":1.02,"dist_refletor":"21mm"}}'
```

Rodar analise e exportar Touchstone:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/analyze `
  -Method Post -ContentType "application/json" `
  -Body '{"setup_name":"Setup1","sweep_name":"Sweep1","output_touchstone":"D:\\simulation\\hfss_export.s2p"}'
```

## Uso com VNA Real

Exemplo LAN/VISA:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/connect `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"pyvisa","resource":"TCPIP0::192.168.0.50::inst0::INSTR","timeout_ms":30000}'
```

Configurar e medir:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/configure-sweep `
  -Method Post -ContentType "application/json" `
  -Body '{"start_hz":600000000,"stop_hz":1100000000,"points":201,"ifbw_hz":1000,"power_dbm":-10}'

Invoke-RestMethod http://127.0.0.1:8765/vna/single-sweep -Method Post
```

Salvar Touchstone:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/save-touchstone `
  -Method Post -ContentType "application/json" `
  -Body '{"path":"D:\\simulation\\vna_measurement.s2p"}'
```

## Variaveis de Ambiente

```powershell
$env:HFSS_BRIDGE_HOST = "127.0.0.1"
$env:HFSS_BRIDGE_PORT = "8765"
$env:HFSS_BRIDGE_AEDT_PROJECT = "D:\simulation\painel triband.aedt"
$env:HFSS_BRIDGE_AEDT_DESIGN = "HFSSDesign1"
$env:HFSS_BRIDGE_VNA_BACKEND = "simulated"
$env:HFSS_BRIDGE_VNA_RESOURCE = "SIM::VNA"
```

## Testes e Qualidade

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

Os testes atuais usam adaptadores simulados e nao exigem AEDT, licenca, VISA ou
hardware conectado.

## Documentacao

- [docs/setup.md](docs/setup.md): instalacao e ambiente.
- [docs/api_reference.md](docs/api_reference.md): referencia HTTP.
- [docs/architecture.md](docs/architecture.md): desenho da aplicacao.
- [docs/aedt_contract.md](docs/aedt_contract.md): contrato AEDT/HFSS.
- [docs/vna_contract.md](docs/vna_contract.md): contrato VNA/SCPI.
- [docs/workflows.md](docs/workflows.md): fluxos operacionais.
- [docs/troubleshooting.md](docs/troubleshooting.md): diagnostico de falhas comuns.
- [docs/originalidade.md](docs/originalidade.md): politica de originalidade.

## Publicacao no GitHub

Repositorio remoto:

```text
https://github.com/Gecesars/hfss_filter_sym.git
```

Configurar e enviar:

```powershell
git remote add origin https://github.com/Gecesars/hfss_filter_sym.git
git push -u origin main
```

