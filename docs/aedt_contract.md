# Contrato AEDT/HFSS

O adaptador AEDT/HFSS oferece uma interface pequena para manter o restante da
aplicacao independente da API exata do PyAEDT.

## Interface

```python
connect(
    project_path,
    design_name,
    version="2026.1",
    new_desktop=False,
    non_graphical=False,
    machine=None,
    port=None,
    aedt_process_id=None,
)
list_designs()
set_active_design(design_name)
get_variables()
set_variables(variables)
analyze(setup_name=None, sweep_name=None, output_touchstone=None)
session_info()
save_project()
create_sparameter_report()
export_convergence()
remove_solution_data()
release()
```

## Backends

### `simulated`

Backend offline para testes e desenvolvimento. Ele:

- cria uma sessao ficticia;
- expoe variaveis geometricas de exemplo;
- permite alterar variaveis;
- gera um Touchstone sintetico quando solicitado.

### `pyaedt`

Backend real baseado em:

```python
from ansys.aedt.core import Hfss
```

O import acontece dentro do adaptador. A aplicacao consegue iniciar sem PyAEDT,
desde que o cliente use o backend `simulated`.

## Abrir Projeto

Exemplo HTTP:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/session `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"pyaedt","project_path":"D:\\dev\\HFSS_AUTO\\painel triBand.aedt","version":"2026.1","new_desktop":false,"machine":"localhost","port":49152}'
```

Campos:

- `backend`: `pyaedt` ou `simulated`.
- `project_path`: caminho do `.aedt`; opcional no modo simulado.
- `design_name`: design HFSS a ativar; opcional.
- `version`: `2026.1` para AEDT 2026 R1.
- `new_desktop`: inicia nova sessao AEDT quando `true`.
- `non_graphical`: tenta usar AEDT sem GUI quando `true`.
- `machine` e `port`: anexam a uma sessao gRPC existente.
- `aedt_process_id`: fallback quando nao houver porta.
- `remove_lock`: somente para lock comprovadamente obsoleto.

## Variaveis

Ler:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/variables
```

Escrever:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/variables `
  -Method Post -ContentType "application/json" `
  -Body '{"variables":{"arm_scale_a":1.02,"dist_refletor":"21mm"}}'
```

Valores numericos sao convertidos para texto antes de chegar ao PyAEDT. Quando a
variavel precisa de unidade, envie a unidade no texto, por exemplo `21mm`.

## Analise

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/analyze `
  -Method Post -ContentType "application/json" `
  -Body '{"setup_name":"Setup1","sweep_name":"Sweep1","cores":4,"blocking":true,"output_touchstone":"D:\\simulation\\hfss_export.s2p"}'
```

Notas:

- `setup_name` e recomendado para evitar ambiguidade.
- `sweep_name` e usado na exportacao quando suportado pelo PyAEDT instalado.
- `output_touchstone` e opcional.
- exportacao usa o argumento PyAEDT oficial `output_file`.

Detalhes verificados em [aedt_2026_integration.md](aedt_2026_integration.md).

## Setup, Modelo e Jobs

Configuracao:

```text
POST /api/aedt/configureanalysis
```

O payload define `setup_name`, `sweep_name`, `f0_ghz`, `start_ghz`, `stop_ghz`,
`points`, `maximum_passes`, `max_delta_s` e `sweep_type`.

Modelos devem ser visualizados primeiro em `POST /api/modeling/plan`. A execucao
usa as rotas `/api/hfss/<method>` documentadas em
[full_functionality.md](full_functionality.md).

Analises longas usam a fila:

```text
POST /api/jobs
GET  /api/jobs
GET  /api/jobs/<id>
POST /api/jobs/<id>/cancel
```

Operacoes adicionais:

- `POST /api/aedt/validatedesign`;
- `POST /api/aedt/exportresults`;
- `POST /api/aedt/stopanalysis`;
- `POST /api/aedt/createreport`;
- `POST /api/aedt/callconvergence`;
- `POST /api/aedt/callkillmesh`.

## Erros Esperados

- PyAEDT nao instalado: instale `.[aedt]`.
- AEDT nao instalado: instale Ansys Electronics Desktop.
- Licenca indisponivel: libere ou configure a licenca HFSS.
- Design inexistente: revise `design_name`.
- Variavel inexistente: confirme nomes em `/aedt/variables`.
