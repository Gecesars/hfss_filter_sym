# Workflows

Este documento descreve fluxos praticos para usar a ponte em desenvolvimento,
laboratorio e integracao com otimizadores.

## 1. Desenvolvimento Offline

Use este fluxo quando nao houver AEDT ou VNA disponivel.

```powershell
.\.venv\Scripts\python -m hfss_vna_bridge
```

Conectar AEDT simulado:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/session `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"simulated","design_name":"OfflineDesign"}'
```

Conectar VNA simulado:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/connect `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"simulated","resource":"SIM::VNA"}'
```

Esse fluxo deve ser usado por GUIs, scripts e testes de integracao leve.

## 2. AEDT/HFSS Real

1. Abra ou disponibilize a licenca AEDT/HFSS.
2. Inicie a API.
3. Chame `/aedt/session` com `backend=pyaedt`.
4. Confirme designs em `/aedt/designs`.
5. Leia variaveis em `/aedt/variables`.
6. Altere variaveis com `POST /aedt/variables`.
7. Execute `POST /aedt/analyze`.

Exemplo de sequencia:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/aedt/session `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"pyaedt","project_path":"D:\\simulation\\painel triband.aedt","design_name":"HFSSDesign1"}'

Invoke-RestMethod http://127.0.0.1:8765/aedt/designs
Invoke-RestMethod http://127.0.0.1:8765/aedt/variables
```

## 3. VNA Real

1. Confirme que o instrumento responde no VISA.
2. Inicie a API.
3. Chame `/vna/connect` com `backend=pyvisa`.
4. Configure sweep.
5. Execute sweep unico.
6. Salve Touchstone.

Exemplo:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/vna/connect `
  -Method Post -ContentType "application/json" `
  -Body '{"backend":"pyvisa","resource":"TCPIP0::192.168.0.50::inst0::INSTR"}'

Invoke-RestMethod http://127.0.0.1:8765/vna/configure-sweep `
  -Method Post -ContentType "application/json" `
  -Body '{"start_hz":600000000,"stop_hz":1100000000,"points":201,"ifbw_hz":1000,"power_dbm":-10}'

Invoke-RestMethod http://127.0.0.1:8765/vna/single-sweep -Method Post
```

## 4. Comparacao Simulacao x Medicao

Fluxo recomendado:

1. Enfileirar AEDT em `POST /api/jobs` e exportar `hfss_export.s2p`.
2. Rodar VNA e exportar `vna_measurement.s2p`.
3. Comparar os quatro parametros em `POST /api/analysis/compare`.
4. Calcular acoes em `POST /api/engineering/tuning`.
5. Ajustar variaveis via `/aedt/variables`.
6. Repetir analise e medicao mantendo o historico do projeto.

O otimizador analitico esta disponivel em `POST /api/engineering/optimize`. Ele
nao inicia HFSS automaticamente; solves eletromagneticos permanecem serializados
na fila de jobs.

## 5. Integracao com GUI ou Otimizador

Recomendacoes:

- use `/health` antes de qualquer fluxo;
- trate erros HTTP `409` como erro de estado ou configuracao;
- trate erros HTTP `502` como erro de backend externo;
- use a fila `/api/jobs` para solves longos e consulte o estado;
- salve Touchstone em pasta fora do repositorio, como `D:\simulation`;
- nao rode multiplas analises AEDT concorrentes no mesmo processo.
