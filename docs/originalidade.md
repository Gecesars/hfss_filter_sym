# Originalidade

Esta aplicacao foi criada do zero para ser uma base propria de integracao
AEDT/HFSS e VNA.

## O Que Foi Usado

Foram usados apenas requisitos tecnicos de interoperabilidade:

- necessidade de um servico local;
- necessidade de controlar AEDT/HFSS por automacao Python;
- necessidade de abrir projeto, selecionar design, alterar variaveis e rodar analise;
- necessidade de controlar VNA com frequencia, IFBW, potencia, sweep unico e exportacao;
- uso de Touchstone como formato comum entre simulacao e medicao.

## O Que Nao Foi Usado

Este repositorio nao inclui:

- codigo fonte recuperado de terceiros;
- decompilacao transcrita;
- patches binarios;
- assets de aplicacoes externas;
- chaves, tokens ou licencas;
- nomes internos proprietarios desnecessarios;
- arquivos `.exe`, `.pyd`, `.dll` ou dumps de recuperacao.

## Politica de Evolucao

Novas funcionalidades devem seguir estas regras:

- implementar comportamento de forma original;
- preferir APIs publicas como PyAEDT, PyVISA e FastAPI;
- documentar contratos HTTP antes de acoplar clientes externos;
- manter testes simulados para qualquer fluxo sem hardware;
- isolar comandos especificos de fabricante em adaptadores proprios.

