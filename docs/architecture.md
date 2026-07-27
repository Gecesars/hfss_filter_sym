# Arquitetura

O HFSS Filter Studio e uma aplicacao local em camadas para sintese de filtros,
automacao AEDT/HFSS e aquisicao VNA. Dependencias de solver e hardware ficam
isoladas para que interface, contratos e testes funcionem offline.

## Visao Geral

```text
Browser
  |
  +-- POST /api/synthesis/calculate
  |     -> services.synthesis
  |          -> engines.filter_engine
  |               -> SciPy ZPK + g values + physical scaling
  |                    -> series + matrix + topology + elements
  |
  +-- /api/aedt/*, /aedt/*, /hfss/*
  |     -> SymMatrixDispatcher
  |          -> JobManager -> RuntimeRegistry
  |               -> SimulatedAedtAdapter ou PyAedtAdapter
  |
  +-- /api/vna/*, /vna/*, /*
  |     -> SymMatrixDispatcher
  |          -> RuntimeRegistry
  |               -> SimulatedVnaAdapter ou PyVisaVnaAdapter
  |
  +-- /api/projects, /api/library, /api/engineering/*
        -> ProjectStore + engineering services
```

O caminho de sintese nao acessa AEDT ou VNA. O caminho de integracao nao depende
do DOM ou de estado do navegador.

## Pacotes

### `web`

Responsabilidades:

- criar o servidor Flask;
- servir HTML, CSS e JavaScript;
- validar o envelope HTTP;
- expor aliases REST e de compatibilidade;
- hospedar eventos SocketIO;
- transformar excecoes conhecidas em resposta JSON.

Nao deve:

- conter comandos SCPI;
- importar PyAEDT diretamente;
- implementar formulas de sintese;
- escrever Touchstone manualmente.

### `engines.filter_engine`

Implementa o dominio numerico:

- prototipos analogicos SciPy;
- transformacoes BPF, BSF e LPF;
- rede reciproca de duas portas;
- Q finito;
- atraso pela derivada da fase;
- valores g e matriz de acoplamento;
- Q externo e acoplamentos fisicos;
- escalamento L/C.

### `services.synthesis`

Valida unidades e orquestra o motor sem estado. Retorna:

- especificacao normalizada;
- vetores de resposta;
- matriz;
- topologia;
- dispersao;
- resumo.

A funcao e deterministica: o mesmo payload produz o mesmo resultado.

### `engines.engineering`

Implementa otimizacao global, Monte Carlo, tuning por sensibilidades e
calculadoras de linhas. Nao acessa AEDT nem VISA.

### Servicos Operacionais

- `services.modeling`: gera planos parametricos HFSS sem efeitos colaterais;
- `services.jobs`: serializa solves e registra progresso/cancelamento;
- `services.project_store`: persiste JSON atomico e revisoes;
- `services.multiplexer`: compoe canais em um grid comum;
- `services.library`: entrega templates versionados.

### `services.symmatrix`

Traduz nomes e formatos de interoperabilidade para os contratos internos.
Mantem:

- estado complementar da sessao AEDT;
- ultima medicao VNA;
- configuracoes que nao pertencem ao adaptador;
- lista de metodos implementados.

Metodos sao normalizados removendo `-` e `_` e convertendo para minusculas.

### `core`

Contem tipos estaveis:

- `AdapterState`;
- `SweepConfig`;
- `NetworkPoint`;
- `RuntimeRegistry`;
- leitura/escrita Touchstone e comparacao de redes.

### `adapters.aedt`

Contrato:

- abrir sessao;
- listar e selecionar design;
- ler e escrever variaveis;
- analisar;
- exportar Touchstone.

Backends:

- `SimulatedAedtAdapter`;
- `PyAedtAdapter`.

O import de PyAEDT e tardio. A aplicacao pode iniciar sem AEDT instalado.
`installations.py` detecta versoes e sessoes gRPC. O backend 2026.1 suporta
attach por porta, attach por PID, nova sessao, setup/sweep, HPC, Touchstone,
relatorios, convergencia, save, modelagem parametrica, validacao, exportacao,
cancelamento e limpeza seletiva.

### `adapters.vna`

Contrato:

- conectar;
- consultar estado;
- resetar;
- configurar sweep;
- medir `S11`, `S21`, `S12` e `S22`;
- controlar markers, sweep continuo e fila de erros;
- salvar Touchstone.

Backends:

- `SimulatedVnaAdapter`;
- `PyVisaVnaAdapter`.

O adaptador real concentra comandos SCPI e a sessao VISA.
`profiles.py` isola os dialetos Keysight, Rohde & Schwarz, Copper Mountain e
generic SCPI.

### `api`

FastAPI permanece como servidor tecnico opcional. Ele e util para Swagger e
clientes REST modernos, mas nao serve o cockpit Flask.

## Estado

### Servidor

Uma instancia Flask possui um `RuntimeRegistry`:

- um adaptador AEDT ativo;
- um adaptador VNA ativo;
- uma configuracao de sweep;
- uma ultima medicao;
- uma fila AEDT;
- um armazenamento de projetos.

Trocar backend substitui o adaptador do dominio correspondente.

### Navegador

O frontend possui estado efemero para:

- especificacao em edicao;
- resposta calculada;
- matriz editada;
- projeto sujo;
- medicao VNA para overlay;
- resultado HFSS para overlay;
- modulo, projeto, biblioteca e job selecionados;
- marcador e visibilidade de curvas.

Esse estado e serializado pelo formato de projeto JSON. Estado de conexao nunca
e restaurado do arquivo.

## Contratos de Erro

| Status interno | HTTP | Significado |
| --- | --- | --- |
| `0` | 200 | Operacao concluida |
| `-400` | 400 | Payload de sintese invalido |
| `-404` | 200 | Metodo fora da superficie conhecida |
| `-500` | 500 | Falha de backend ou conversao |

Os metodos publicados em `/health` possuem handler. `-404` permanece apenas
para chamadas fora da superficie conhecida.

## Concorrencia

A versao atual garante:

- uma sessao AEDT por processo;
- um VNA por processo;
- jobs AEDT serializados por um `ThreadPoolExecutor` de um worker;
- progresso e cancelamento consultaveis;
- calculos numericos curtos executados na thread Flask.

Para multiplos usuarios, ainda seriam necessarios autenticacao, isolamento de
sessao e locks distribuidos.

## Seguranca

O servidor usa `127.0.0.1` por padrao. Nao expor em `0.0.0.0` sem:

- autenticacao;
- validacao de origem;
- allowlist de pastas;
- limites de payload;
- protecao para operacoes AEDT e VISA;
- TLS quando houver trafego fora da maquina.

O frontend nao recebe credenciais. Enderecos VISA e caminhos AEDT sao enviados
somente ao servidor local.

## Touchstone

`core.touchstone` le RI/MA/DB e escreve:

```text
# Hz S RI R 50
```

`NetworkPoint` usa frequencia em Hz e parametros S complexos. Conversoes para dB
acontecem na borda de apresentacao.

## Testes

Testes offline cobrem:

- criacao dos servidores;
- health e snapshot;
- validacao da sintese;
- conservacao de potencia, return loss, Q e zeros finitos;
- dimensoes de series, matriz e topologia;
- contrato PyAEDT 2026 e argumento `output_file`;
- fluxo AEDT simulado;
- fluxo VNA simulado;
- aquisicao PyVISA de quatro parametros com instrumento mockado;
- parser e comparador Touchstone;
- projetos e revisoes;
- modelagem cavity/planar/SIW;
- otimizacao, Monte Carlo, multiplexer e linhas;
- escrita `.s2p`;
- Playwright em desktop/mobile e fluxos de modulo.

Testes de integracao reais devem ser opt-in e separados por marcadores porque
dependem de licenca, desktop AEDT, VISA e equipamento.
