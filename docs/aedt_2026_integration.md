# AEDT/HFSS 2026 Integration

Esta integracao usa a API publica PyAEDT e o transporte gRPC do AEDT 2026 R1.
Nao usa automacao de tela, injecao em processo ou chamadas privadas.

## Referencias Oficiais

- Desktop sessions:
  https://aedt.docs.pyansys.com/version/stable/User_guide/desktop_sessions.html
- Classe `Hfss`:
  https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.hfss.Hfss.html
- Classe `Desktop`:
  https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.desktop.Desktop.html
- `analyze_setup`:
  https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.hfss.Hfss.analyze_setup.html
- `export_touchstone`:
  https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.hfss.Hfss.export_touchstone.html
- Variaveis:
  https://aedt.docs.pyansys.com/version/stable/API/Variables.html
- Post-processing:
  https://aedt.docs.pyansys.com/version/stable/User_guide/postprocessing.html
- Setup e sweep:
  https://aedt.docs.pyansys.com/version/stable/API/Setup.html

## Ambiente Verificado

Validacao local em 2026-07-27:

```text
Windows 11
Python 3.14.3
PyAEDT 1.3.0
AEDT 2026.1.0
Install: C:\Program Files\ANSYS Inc\v261\AnsysEM
Transport: gRPC
```

Instalacoes detectadas:

```text
2026.1 -> C:\Program Files\ANSYS Inc\v261\AnsysEM
2024.2 -> C:\Program Files\AnsysEM\v242\Win64
2022.1 -> C:\Program Files\AnsysEM22\v221\Win64
```

## Projeto Verificado

```text
D:\dev\HFSS_AUTO\painel triBand.aedt
```

Sessao anexada:

```text
PID: 2228
gRPC: localhost:49152
Project: painel triBand
Active design: Banda 2A8+2B12+2C12
Second design: Banda_baixa_698_960
Setup: Setup1
Sweep: Sweep1
Variables read: 40
```

Nenhuma solucao foi executada durante a validacao de conexao.

## Descoberta

`adapters.aedt.installations` consulta:

- variaveis `ANSYSEM_ROOT*`;
- pastas conhecidas em `Program Files`;
- processos `ansysedt.exe`;
- argumentos `-grpcsrv`;
- flag `-ng`.

Endpoint:

```text
GET /api/aedt/installations
```

Retorna instalacoes, sessoes ativas, PID, porta, versao, executavel e modo
grafico.

## Modos de Conexao

### Anexar por gRPC

Modo preferencial quando o projeto ja esta aberto:

```json
{
  "backend": "pyaedt",
  "project_path": "D:\\dev\\HFSS_AUTO\\painel triBand.aedt",
  "version": "2026.1",
  "new_desktop": false,
  "machine": "localhost",
  "port": 49152
}
```

A porta tem prioridade sobre PID. Isso evita uma incompatibilidade observada no
PyAEDT 1.3.0 ao validar somente `aedt_process_id`.

### Nova Sessao

```json
{
  "backend": "pyaedt",
  "project_path": "D:\\projects\\filter.aedt",
  "version": "2026.1",
  "new_desktop": true,
  "non_graphical": true,
  "close_on_exit": false
}
```

Se o construtor falhar depois de criar um novo AEDT, o adaptador identifica
somente processos novos, da mesma versao e criados durante a tentativa, e os
encerra para evitar uma sessao orfa.

### PID

`aedt_process_id` permanece disponivel como fallback. Quando `port` e informado,
o PID e omitido do construtor PyAEDT.

## Locks

O backend nao remove lock por padrao.

```json
{"remove_lock": false}
```

Use `remove_lock=true` apenas depois de confirmar que:

- nenhum AEDT possui o projeto aberto;
- o lock pertence a uma sessao encerrada;
- nao ha processo de solve ativo.

Quando o projeto esta aberto, anexar pela porta gRPC e a operacao correta.

## Informacoes de Sessao

```text
POST /api/aedt/sessioninfo
```

Retorna:

- versao curta e completa;
- PID e porta;
- diretorio de instalacao;
- projeto e design;
- tipo de design e solution type;
- setups e sweeps;
- propriedade da sessao pelo servidor.

## Variaveis

Leitura:

```text
POST /aedt/getvariables
```

Escrita:

```json
{
  "variables": {
    "dist_refletor": "21mm",
    "comp_refletor": "82mm"
  }
}
```

Variaveis mantem unidades como expressoes AEDT.

## Analise

```json
{
  "setup_name": "Setup1",
  "sweep_name": "Sweep1",
  "cores": 4,
  "tasks": null,
  "gpus": null,
  "blocking": true,
  "revert_to_initial_mesh": false,
  "output_touchstone": "D:\\simulation\\results\\panel.s2p"
}
```

Fluxo:

1. validar setup;
2. executar `Hfss.analyze_setup`;
3. validar sweep;
4. criar pasta de saida;
5. chamar `export_touchstone(setup, sweep, output_file)`;
6. confirmar que o arquivo foi criado.

O adaptador usa o argumento oficial `output_file`. Os nomes legados
`file_name`, `solution_name` e `sweep_name` foram removidos.

## Operacoes Adicionais

- `POST /aedt/createreport`: cria relatorio S no AEDT;
- `POST /aedt/callconvergence`: exporta convergencia;
- `POST /aedt/callkillmesh`: remove somente dados selecionados;
- `POST /hfss/saveproject`: salva ou faz Save As;
- `POST /hfss/removemesh`: alias de limpeza controlada;
- `POST /aedt/release`: libera sessao.

## Liberacao

Para uma sessao anexada:

```json
{
  "close_projects": false,
  "close_desktop": false
}
```

Para uma sessao criada pelo servidor:

```json
{
  "close_projects": true,
  "close_desktop": true
}
```

A interface seleciona esses valores de acordo com o modo `Attach` ou `Start new
desktop`.

## Utilitario de Validacao

Somente diagnostico:

```powershell
.\.venv\Scripts\python scripts\validate_aedt_2026.py `
  --project "D:\dev\HFSS_AUTO\painel triBand.aedt" `
  --attach --machine localhost --port 49152
```

Nova sessao non-graphical:

```powershell
.\.venv\Scripts\python scripts\validate_aedt_2026.py `
  --project "D:\projects\filter.aedt"
```

Analise e exportacao so ocorrem com `--analyze`.

## Recursos 0.4.0

A integracao tambem implementa:

- criacao/atualizacao de setup e linear-count sweep;
- validacao completa com numero esperado de portas;
- geracao parametrica de cavity, combline, waveguide, planar, SIW e LPF;
- exportacao agregada de resultados;
- interrupcao por `stop_simulations(clean_stop=True)`;
- fila serializada com progresso e cancelamento.

Preview de modelagem usa `POST /api/modeling/plan` e nao acessa o desktop. A
construcao real ocorre somente quando `dry_run=false`.

Solves longos devem usar:

```text
POST /api/jobs
GET  /api/jobs/<id>
POST /api/jobs/<id>/cancel
```

A fila possui um worker para impedir mutacoes concorrentes no mesmo objeto
PyAEDT/design.

## Seguranca Operacional

- servidor limitado a `127.0.0.1`;
- nenhum lock removido automaticamente;
- nenhum solve executado na descoberta;
- nenhum projeto fechado ao liberar uma sessao anexada;
- caminhos de saida sao absolutos antes da exportacao;
- falha de exportacao e confirmada pela existencia do arquivo;
- limpeza de mesh exige chamada HTTP explicita.
