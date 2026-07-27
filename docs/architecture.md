# Arquitetura

O projeto e dividido em quatro camadas:

1. API HTTP (`api`): recebe comandos locais e valida payloads.
2. Registro de runtime (`core.registry`): guarda os adaptadores ativos.
3. Adaptadores AEDT/VNA (`adapters`): isolam dependencias externas como PyAEDT e PyVISA.
4. Tipos compartilhados (`core.models`): estados, configuracao de sweep e pontos de rede.

O fluxo normal e:

1. Um cliente abre uma sessao em `/aedt/session` e conecta o VNA em `/vna/connect`.
2. O cliente configura parametros HFSS em `/aedt/variables`.
3. O cliente roda uma analise AEDT em `/aedt/analyze` e exporta Touchstone quando necessario.
4. O cliente configura o VNA em `/vna/configure-sweep`, executa `/vna/single-sweep` e salva `/vna/save-touchstone`.
5. Uma aplicacao de calibracao/otimizacao externa compara os dados HFSS e VNA.

O modo simulado permite validar a API, GUI e automacoes sem AEDT ou hardware.

