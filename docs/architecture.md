# Arquitetura

O projeto e uma ponte local entre clientes externos, AEDT/HFSS e VNA. A
aplicacao mantem dependencias de hardware isoladas em adaptadores para que o
restante do codigo possa ser testado sem AEDT, VISA ou instrumentos fisicos.

## Camadas

1. `api`: FastAPI, validacao de payloads e serializacao de respostas.
2. `core`: tipos compartilhados, estado de runtime e escrita Touchstone.
3. `adapters.aedt`: backends AEDT/HFSS.
4. `adapters.vna`: backends VNA/SCPI.
5. `tests`: testes offline com adaptadores simulados.

## Fluxo de Dependencias

```text
Cliente HTTP
  -> FastAPI routes
    -> RuntimeRegistry
      -> AedtAdapter ou VnaAdapter
        -> PyAEDT, PyVISA ou simulador
```

A API nao importa AEDT ou PyVISA diretamente. Esses imports ficam nos adaptadores
reais e sao tardios. Isso permite iniciar a aplicacao mesmo sem AEDT instalado.

## RuntimeRegistry

`RuntimeRegistry` guarda os adaptadores ativos. Quando um cliente chama
`/aedt/session` ou `/vna/connect`, o adaptador anterior e substituido por um novo
backend.

Essa decisao simplifica o servidor:

- uma sessao AEDT ativa por processo;
- um VNA ativo por processo;
- troca explicita de backend via API;
- testes previsiveis com estado isolado por instancia de app.

## Adaptadores

### AEDT

Contrato principal:

- conectar sessao;
- listar designs;
- ler variaveis;
- escrever variaveis;
- rodar analise;
- exportar Touchstone quando solicitado.

Backends:

- `SimulatedAedtAdapter`
- `PyAedtAdapter`

### VNA

Contrato principal:

- conectar instrumento;
- resetar;
- configurar sweep;
- executar sweep unico;
- salvar Touchstone.

Backends:

- `SimulatedVnaAdapter`
- `PyVisaVnaAdapter`

## Touchstone

O modulo `core.touchstone` escreve `.s2p` em formato:

```text
# Hz S RI R 50
```

Os pontos sao representados por `NetworkPoint`, sempre em Hz e numeros complexos
para parametros S.

## Estrategia de Testes

Os testes usam apenas simuladores. Isso cobre:

- criacao da API;
- health check;
- ciclo VNA basico;
- escrita de Touchstone;
- ciclo AEDT basico de variaveis.

Testes com AEDT e VNA reais devem ser adicionados como testes manuais ou
marcados como integracao, pois dependem de licenca, hardware e laboratorio.

