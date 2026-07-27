# Contrato AEDT/HFSS

O adaptador AEDT/HFSS oferece uma interface pequena para manter o restante da
aplicacao independente da API exata do PyAEDT.

## Interface

```python
connect(project_path, design_name, new_desktop=False, non_graphical=False)
list_designs()
get_variables()
set_variables(variables)
analyze(setup_name=None, sweep_name=None, output_touchstone=None)
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
  -Body '{"backend":"pyaedt","project_path":"D:\\simulation\\painel triband.aedt","design_name":"HFSSDesign1","new_desktop":false,"non_graphical":false}'
```

Campos:

- `backend`: `pyaedt` ou `simulated`.
- `project_path`: caminho do `.aedt`; opcional no modo simulado.
- `design_name`: design HFSS a ativar; opcional.
- `new_desktop`: inicia nova sessao AEDT quando `true`.
- `non_graphical`: tenta usar AEDT sem GUI quando `true`.

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
  -Body '{"setup_name":"Setup1","sweep_name":"Sweep1","output_touchstone":"D:\\simulation\\hfss_export.s2p"}'
```

Notas:

- `setup_name` e recomendado para evitar ambiguidade.
- `sweep_name` e usado na exportacao quando suportado pelo PyAEDT instalado.
- `output_touchstone` e opcional.

## Erros Esperados

- PyAEDT nao instalado: instale `.[aedt]`.
- AEDT nao instalado: instale Ansys Electronics Desktop.
- Licenca indisponivel: libere ou configure a licenca HFSS.
- Design inexistente: revise `design_name`.
- Variavel inexistente: confirme nomes em `/aedt/variables`.

