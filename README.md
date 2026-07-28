# HFSS VNA Bridge

Aplicacao Python 3.14 original para automatizar AEDT/HFSS e aquisicao de VNA
por uma API HTTP local.

O objetivo do projeto e fornecer uma base propria, documentada e testavel para:

- abrir ou reutilizar projetos AEDT/HFSS;
- listar e alterar variaveis de projeto/design;
- executar analises HFSS e exportar dados Touchstone;
- controlar um VNA por SCPI via PyVISA;
- operar em modo simulado quando AEDT ou hardware nao estiverem disponiveis;
- integrar scripts, GUIs ou otimizadores sem acoplar a regra de negocio ao AEDT;
- sintetizar respostas BPF, BSF, LPF e multi-banda com NumPy/SciPy;
- visualizar parametros S, atraso de grupo, potencia, matriz e topologia;
- editar/exportar matriz e salvar/carregar projetos JSON;
- sintetizar diplexers/multiplexers por canais;
- gerar modelos parametricos de cavidade, combline, waveguide, planar, SIW e LPF;
- executar jobs HFSS em fila com progresso e cancelamento;
- adquirir `S11`, `S21`, `S12` e `S22` de VNAs reais;
- comparar Touchstone de alvo, HFSS e VNA;
- executar tuning, otimizacao, Monte Carlo e calculos de linhas;
- persistir projetos com revisoes e reutilizar modelos da biblioteca;
- criar projetos FD3D-like com componentes, caracterizacoes e assembly rastreaveis;
- executar caracterizacao real de ressonadores e pares no HFSS Eigenmode;
- executar caracterizacao real de `Qe` no HFSS Driven Modal;
- montar filtros combline em partes com dimensoes derivadas de curvas aprovadas.

Este repositorio nao contem codigo fonte recuperado, nomes internos proprietarios,
patches, binarios, licencas, credenciais ou assets de terceiros. A implementacao foi
escrita do zero usando apenas requisitos tecnicos de interoperabilidade.

![HFSS Filter Studio workbench](docs/assets/filter-studio-workbench.png)

## Status

- Versao da aplicacao: `0.4.0`;
- Python: `>=3.14`;
- servidor padrao: Flask + JavaScript local;
- API tecnica opcional: FastAPI;
- AEDT/HFSS: backend `pyaedt`, validado contratualmente com AEDT 2026.1;
- sintese: prototipos Chebyshev, Butterworth, Bessel e Elliptic;
- VNA: backend `pyvisa`, duas portas completas e perfis Keysight/R&S/CMT;
- superficie SymMatrix: `/aedt/<method>`, `/hfss/<method>` e `POST /<method>`;
- modelagem: planos parametricos e execucao pelo Modeler PyAEDT;
- analise: jobs HFSS serializados, consultaveis e cancelaveis;
- projetos: armazenamento JSON atomico e historico de revisoes;
- testes offline: backends `simulated`;
- saida de rede: Touchstone `.s2p`;
- UI: workstation desktop responsiva, sem dependencias frontend externas;
- FD3D: branch experimental com projetos, Eigenmode real, external Q, mapping, assembly e gates.

Nenhum solve FD3D real foi executado pelo CI. A validacao final requer AEDT 2026.1 e licenca HFSS local.

Validado localmente/CI com:

```powershell
.\.venv\Scripts\python --version
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
npm run test:ui
```

## Requisitos

Obrigatorios para desenvolvimento:

- Windows;
- `uv`;
- Git;
- Python 3.14 gerenciado pelo `uv`;
- Node.js somente para executar os testes Playwright.

Obrigatorios para uso com AEDT/HFSS real:

- Ansys Electronics Desktop instalado;
- licenca AEDT/HFSS valida;
- pacote `pyaedt`.

Obrigatorios para uso com VNA real:

- VNA acessivel por LAN/USB/GPIB;
- VISA runtime compativel, como NI-VISA ou Keysight IO Libraries;
- pacote `pyvisa`.

## Instalacao rapida

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

Para os testes visuais:

```powershell
npm install
npx playwright install chromium
```

## Executar

```powershell
.\.venv\Scripts\python -m hfss_vna_bridge --host 127.0.0.1 --port 8765
```

O servidor padrao e Flask. A interface local fica em:

```text
http://127.0.0.1:8765/
```

Ou:

```powershell
.\scripts\run.ps1 -HostName 127.0.0.1 -Port 8765
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Para executar a API FastAPI anterior:

```powershell
.\.venv\Scripts\python -m hfss_vna_bridge --server fastapi --host 127.0.0.1 --port 8765
```

## Ferramentas FD3D

A branch `feature/fd3d-project-platform` adiciona o executavel:

```powershell
hfss-fd3d --help
```

### Eigenmode real

```powershell
hfss-fd3d eigenmode `
  --plan data\fd3d\resonator_plan.json `
  --output data\fd3d\resonator_result.json `
  --version 2026.1 `
  --new-desktop
```

O comando rejeita backend simulado. Cada amostra e resolvida no HFSS Eigenmode real.

### External Q real

```powershell
hfss-fd3d external-q `
  --plan data\fd3d\external_q_plan.json `
  --output data\fd3d\external_q_result.json `
  --version 2026.1 `
  --new-desktop
```

Cada profundidade de probe e resolvida no HFSS Driven Modal. O `S11` complexo e ajustado para extrair `f0`, `QL`, `Qe`, `Qi`, beta, fase e atraso.

### Assembly em partes

```powershell
hfss-fd3d assembly-plan `
  --project data\fd3d\project.json `
  --mapping data\fd3d\mapping.json `
  --output data\fd3d\assembly_plan.json `
  --require-characterized-external-q
```

O assembly inclui housing, cavidades, ressonadores, iris, probes e parafusos de sintonia como partes rastreaveis. Cross couplings sem realizacao fisica bloqueiam o build.

Documentacao:

```text
docs/fd3d_project_platform_plan.md
docs/fd3d_hfss_eigenmode_contract.md
docs/fd3d_real_hfss_validation_protocol.md
```

## Estrutura

```text
hfss_vna_bridge/
  docs/
  scripts/
  src/hfss_vna_bridge/
    adapters/
      aedt/
      vna/
    api/
    core/
    engines/
    fd3d/
    services/
    web/
    cli.py
    fd3d_cli.py
    settings.py
  tests/
  package.json
  playwright.config.js
  pyproject.toml
  uv.lock
```

## Endpoints principais Flask/SymMatrix

Sintese:

- `POST /api/synthesis/calculate`;
- `POST /api/synthesis/matrix-response`;
- `POST /api/synthesis/multiplexer`;
- `POST /api/engineering/optimize`;
- `POST /api/engineering/monte-carlo`;
- `POST /api/engineering/tuning`;
- `POST /api/engineering/transmission-line`;
- `POST /api/modeling/plan`.

VNA local:

- `GET /api/vna/resources`;
- `GET /api/vna/capabilities`;
- `GET /api/vna/errors`;
- `POST /connect`;
- `POST /close`;
- `POST /reset`;
- `POST /setfrequency`;
- `POST /setifbw`;
- `POST /setpower`;
- `POST /setsweeppoints`;
- `POST /singlesweep`;
- `POST /savetracedata`;
- `POST /exports2p`.

AEDT/HFSS local:

- `POST /aedt/openproject`;
- `POST /aedt/getdesigns`;
- `POST /aedt/getvariables`;
- `POST /aedt/getvariablesvalue`;
- `POST /aedt/setvariablesvalue`;
- `POST /aedt/evaluatedimension`;
- `POST /aedt/evaluatedimensionnos2p`;
- `POST /api/aedt/configureanalysis`;
- `POST /api/aedt/validatedesign`;
- `POST /api/aedt/exportresults`;
- `POST /api/aedt/stopanalysis`;
- `POST /hfss/openproject`;
- `POST /hfss/updatevalues`;
- `POST /hfss/analyzeall`;
- `POST /hfss/buildcavityfull3d`;
- `POST /hfss/ccsinglemodeling`;
- `POST /hfss/wgrsinglemodeling`;
- `POST /hfss/siwfull3d`;
- `POST /hfss/lpf_step_modeling`.

Dados e operacao:

- `POST /api/touchstone/import`;
- `POST /api/analysis/compare`;
- `GET|POST /api/projects`;
- `GET|PUT|DELETE /api/projects/<id>`;
- `GET /api/projects/<id>/versions`;
- `POST /api/projects/<id>/restore/<revision>`;
- `GET /api/library`;
- `GET|POST /api/jobs`;
- `GET /api/jobs/<id>`;
- `POST /api/jobs/<id>/cancel`.

Os metodos publicados em `/health` possuem implementacao. Metodos desconhecidos retornam `status=-404`.

## Uso em modo simulado

Conectar VNA simulado:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/connect `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"simulated","resource":"SIM::VNA"}'
```

Conectar AEDT simulado:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/session `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"simulated","design_name":"OfflineDesign"}'
```

O modo simulado nao pode executar nem aprovar caracterizacoes FD3D.

## Uso com AEDT/HFSS real

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/session `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"pyaedt","project_path":"D:\\simulation\\filter.aedt","version":"2026.1","new_desktop":false,"machine":"localhost","port":49152}'
```

Detectar instalacoes e sessoes gRPC:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/aedt/installations
```

## Uso com VNA real

Exemplo LAN/VISA:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/connect `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"pyvisa","brand":"KEYSIGHT","resource":"TCPIP0::192.168.0.50::inst0::INSTR","timeout_ms":30000,"channel":1}'
```

## Testes

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
npm run test:ui
```

Testes reais dependentes de AEDT, licenca e VNA devem permanecer opt-in e separados dos testes offline.
