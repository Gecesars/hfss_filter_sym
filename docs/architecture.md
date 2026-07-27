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
  |          -> series + matrix + topology
  |
  +-- /api/aedt/*, /aedt/*, /hfss/*
  |     -> SymMatrixDispatcher
  |          -> RuntimeRegistry
  |               -> SimulatedAedtAdapter ou PyAedtAdapter
  |
  +-- /api/vna/*, /vna/*, /*
        -> SymMatrixDispatcher
             -> RuntimeRegistry
                  -> SimulatedVnaAdapter ou PyVisaVnaAdapter
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

### `services.synthesis`

Recebe uma especificacao sem estado e retorna:

- especificacao normalizada;
- vetores de resposta;
- matriz;
- topologia;
- dispersao;
- resumo.

A funcao e deterministica: o mesmo payload produz o mesmo resultado. Isso
permite cache, testes numericos e futura substituicao por um engine rigoroso sem
alterar o contrato da UI.

### `services.symmatrix`

Traduz nomes e formatos de interoperabilidade para os contratos internos.
Mantem:

- estado complementar da sessao AEDT;
- ultima medicao VNA;
- configuracoes que nao pertencem ao adaptador;
- lista de metodos implementados e reservados.

Metodos sao normalizados removendo `-` e `_` e convertendo para minusculas.

### `core`

Contem tipos estaveis:

- `AdapterState`;
- `SweepConfig`;
- `NetworkPoint`;
- `RuntimeRegistry`;
- escrita Touchstone.

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

### `adapters.vna`

Contrato:

- conectar;
- consultar estado;
- resetar;
- configurar sweep;
- medir;
- salvar Touchstone.

Backends:

- `SimulatedVnaAdapter`;
- `PyVisaVnaAdapter`.

O adaptador real concentra comandos SCPI e a sessao VISA.

### `api`

FastAPI permanece como servidor tecnico opcional. Ele e util para Swagger e
clientes REST modernos, mas nao serve o cockpit Flask.

## Estado

### Servidor

Uma instancia Flask possui um `RuntimeRegistry`:

- um adaptador AEDT ativo;
- um adaptador VNA ativo;
- uma configuracao de sweep;
- uma ultima medicao.

Trocar backend substitui o adaptador do dominio correspondente.

### Navegador

O frontend possui estado efemero para:

- especificacao em edicao;
- resposta calculada;
- matriz editada;
- projeto sujo;
- medicao VNA para overlay;
- marcador e visibilidade de curvas.

Esse estado e serializado pelo formato de projeto JSON. Estado de conexao nunca
e restaurado do arquivo.

## Contratos de Erro

| Status interno | HTTP | Significado |
| --- | --- | --- |
| `0` | 200 | Operacao concluida |
| `-400` | 400 | Payload de sintese invalido |
| `-404` | 200 | Metodo fora da superficie conhecida |
| `-501` | 200 | Metodo conhecido e planejado |
| `-500` | 500 | Falha de backend ou conversao |

Endpoints de compatibilidade preservam HTTP 200 para metodos planejados porque
clientes legados inspecionam o campo `status`.

## Concorrencia

A versao atual assume:

- uma sessao AEDT por processo;
- um VNA por processo;
- chamadas de integracao serializadas pelo cliente;
- calculos analiticos curtos executados na thread Flask.

Antes de habilitar multiplos usuarios ou analyses longas, adicionar:

1. fila de jobs;
2. identificador de projeto/sessao;
3. lock por adaptador;
4. armazenamento de progresso;
5. cancelamento cooperativo.

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

`core.touchstone` escreve:

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
- dimensoes de series, matriz e topologia;
- fluxo AEDT simulado;
- fluxo VNA simulado;
- escrita `.s2p`;
- endpoints planejados.

Testes de integracao reais devem ser opt-in e separados por marcadores porque
dependem de licenca, desktop AEDT, VISA e equipamento.
