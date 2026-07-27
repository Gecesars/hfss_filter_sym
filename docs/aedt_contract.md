# Contrato AEDT/HFSS

O adaptador AEDT define uma interface pequena e estavel:

- `connect(project_path, design_name, new_desktop, non_graphical)`
- `list_designs()`
- `get_variables()`
- `set_variables(variables)`
- `analyze(setup_name, sweep_name, output_touchstone)`

O backend `pyaedt` usa `ansys.aedt.core.Hfss` com importacao tardia. Assim, a API inicia em
modo simulado mesmo em maquinas sem AEDT.

Os nomes de setup, sweep, projeto e design ficam nos payloads HTTP. Isso evita
acoplar a aplicacao a um arquivo `.aedt` especifico.

Exemplo:

```json
{
  "backend": "pyaedt",
  "project_path": "D:\\simulation\\painel triband.aedt",
  "design_name": "HFSSDesign1",
  "new_desktop": false,
  "non_graphical": false
}
```

