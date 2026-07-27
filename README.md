# HFSS VNA Bridge

Aplicacao Python 3.14 original para integrar AEDT/HFSS e VNA por uma API local.

Este projeto nao copia codigo recuperado de terceiros. A arquitetura apenas replica
contratos tecnicos observados: um servico local, um modulo AEDT para abrir/procesar
projetos HFSS e um modulo VNA para comandos SCPI/pyvisa.

## Estrutura

- `src/hfss_vna_bridge/api`: API FastAPI e modelos HTTP.
- `src/hfss_vna_bridge/adapters/aedt`: adaptadores AEDT, incluindo PyAEDT e simulador.
- `src/hfss_vna_bridge/adapters/vna`: adaptadores VNA, incluindo PyVISA e simulador.
- `src/hfss_vna_bridge/core`: tipos compartilhados e escrita Touchstone.
- `docs`: contratos e arquitetura.
- `tests`: testes de API usando adaptadores simulados.

## Ambiente Python 3.14

```powershell
uv python install 3.14
uv venv --python 3.14
.\.venv\Scripts\python -m pip install -e ".[dev,aedt,vna]"
```

Para rodar somente em modo simulado, `aedt` e `vna` podem ser omitidos:

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## Executar

```powershell
.\.venv\Scripts\python -m hfss_vna_bridge --host 127.0.0.1 --port 8765
```

Endpoints principais:

- `GET /health`
- `POST /aedt/session`
- `GET /aedt/designs`
- `GET /aedt/variables`
- `POST /aedt/variables`
- `POST /aedt/analyze`
- `POST /vna/connect`
- `GET /vna/status`
- `POST /vna/configure-sweep`
- `POST /vna/single-sweep`
- `POST /vna/save-touchstone`

Tambem existem aliases de compatibilidade para integracoes locais simples:
`/connect`, `/reset`, `/setfrequency`, `/setifbw`, `/setpower`,
`/singlesweep`, `/savetracedata` e `/status`.

## Exemplo VNA simulado

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/connect `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"simulated","resource":"SIM::VNA"}'

Invoke-RestMethod http://127.0.0.1:8765/vna/configure-sweep `
  -Method Post -ContentType "application/json" `
  -Body '{"start_hz":600000000,"stop_hz":1100000000,"points":101,"ifbw_hz":1000,"power_dbm":-10}'

Invoke-RestMethod http://127.0.0.1:8765/vna/single-sweep -Method Post
```

## Exemplo AEDT/HFSS

Com AEDT instalado, licenca disponivel e o extra `aedt` instalado:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/session `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"pyaedt","project_path":"D:\\simulation\\painel triband.aedt","design_name":"HFSSDesign1"}'
```

Depois:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/variables
```

## Testes

```powershell
.\.venv\Scripts\python -m pytest
```

## GitHub

Depois de autenticar o GitHub CLI:

```powershell
gh auth login
gh repo create hfss-vna-bridge --private --source . --remote origin --push
```
