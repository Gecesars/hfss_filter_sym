# SymMatrix MVP

Este MVP implementa o modelo operacional observado no SymMatrix de forma
original: servidor local Flask, frontend JavaScript, rotas AEDT/HFSS e rotas VNA
genericas.

## Escopo Funcional Atual

### VNA funcional

- `status`
- `connect`
- `close`
- `reset`
- `clearerrmsg`
- `initialize2`
- `loadpreset`
- `setfrequency`
- `setifbw`
- `setpower`
- `setsweeppoints`
- `setsweeptype`
- `setcontinoussweep`
- `settrace`
- `settracestatus`
- `setmarkers`
- `setautoscaletrace`
- `getsweeptime`
- `getmarkeryvalue`
- `savetracedata`
- `deleteallmarkers`
- `deletetraces`
- `singlesweep`
- `beginbackgroundsweep`
- `endbackgroundsweep`
- `exports2p`

### AEDT funcional

- `openproject`
- `getdesigns`
- `setactivedesign`
- `getvariables`
- `getvariablesvalue`
- `setvariablesvalue`
- `setsettings`
- `evaluatedimension`
- `evaluatedimensionnos2p`
- `stop`

### HFSS funcional

- `ping`
- `openproject`
- `closeproject`
- `updatevalues`
- `analyzeall`

## Endpoints Reservados

Os endpoints abaixo existem no contrato e retornam `status=-501` ate que a
modelagem especifica seja implementada:

- `aedt/createreport`
- `aedt/makelpfmodel`
- `aedt/callconvergence`
- `aedt/callkillmesh`
- familias `hfss/*simulation`
- familias `hfss/*modeling`
- familias `hfss/*couplingmodeling`
- familias `hfss/*iomodeling`
- familias `hfss/lpf_*_modeling`

## Proximas Fases

1. Adicionar adaptadores VNA por fabricante quando houver equipamento em bancada.
2. Implementar parser Touchstone e comparacao simulacao x medicao.
3. Implementar fila de jobs AEDT para analises longas.
4. Implementar otimizador externo baseado em `.s2p`.
5. Implementar eventos SocketIO reais para `deepOptimization` e `portTuning`.

