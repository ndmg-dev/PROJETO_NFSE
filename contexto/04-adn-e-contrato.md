# 04 — ADN: o que se sabe e o que não

## Confirmado na documentação oficial
Fonte: *Manual dos Contribuintes — APIs do ADN*, v1.0 de 12/02/2026
(https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-apis-adn-sistema-nacional-nfse.pdf).
- `GET /DFe/{NSU}`: devolve o documento fiscal daquele NSU (emitente, tomador ou intermediário).
- `GET /NFSe/{ChaveAcesso}/Eventos`: eventos de uma nota.
- Hosts: produção restrita `adn.producaorestrita.nfse.gov.br`; produção `adn.nfse.gov.br`.
- Swagger de testes: `https://adn.producaorestrita.nfse.gov.br/contribuintes/docs/index.html` (exige certificado).
- Autenticação por certificado (mTLS). **O CNPJ raiz do certificado deve ser o do contribuinte consultado.**
  Na consulta por NSU há um parâmetro para informar CNPJ diferente do certificado, com validação do CNPJ raiz.
- Outras APIs no portal: CNC, Parâmetros Municipais, DANFSE, SEFIN Nacional.

## Confirmado no Swagger real (25/09/2026, esquema — ainda sem dado de verdade)
Lido em `https://adn.producaorestrita.nfse.gov.br/contribuintes/docs/index.html` sem precisar de "Try it out"
(é doc estático, Redocly). `app/adn/contrato.py` já foi atualizado com os nomes abaixo; `VERIFICADO` continua
`False` porque isto é o esquema, não uma resposta real.
- Compactação do XML: **GZip com base64** (confirmado em "Padrões técnicos").
- Envelope de `GET /DFe/{NSU}` (PascalCase): `StatusProcessamento` (enum `REJEICAO`/`NENHUM_DOCUMENTO_LOCALIZADO`/
  `DOCUMENTOS_LOCALIZADOS`), `LoteDFe` (array de `DistribuicaoNSU`|null), `Alertas`/`Erros` (array de
  `MensagemProcessamento`|null), `TipoAmbiente`, `VersaoAplicativo`, `DataHoraProcessamento`.
- `DistribuicaoNSU`: `NSU`, `ChaveAcesso`, `TipoDocumento` (enum: NENHUM/DPS/PEDIDO_REGISTRO_EVENTO/NFSE/EVENTO/CNC),
  `TipoEvento` (enum, só quando `TipoDocumento=EVENTO`), `ArquivoXml`, `DataHoraGeracao`.
- Query params: `cnpjConsulta` (opcional) e `lote` (bool, default `true`).
- **Não existe campo de "próximo/máximo NSU"** no envelope — ao contrário do que se supunha. A paginação só pode
  vir do maior NSU dentro do próprio `LoteDFe` (já é o que `Lote.maior_nsu` calcula).

## NÃO documentado ainda (não inventar)
Se `NENHUM_DOCUMENTO_LOCALIZADO` vem com `LoteDFe=null` ou `[]`; tamanho máximo do lote por chamada; rate limit;
código HTTP de erro genérico (o Swagger só documenta 200/400/404); tabela completa de eventos → situação de
negócio. Tudo isso está isolado em `app/adn/contrato.py` (`VERIFICADO=False`) e nas hipóteses de tags em
`app/domain/parser.py`.

## Como fechar o contrato de vez
Falta uma chamada real (não só o esquema) contra um NSU com documento, para confirmar que o corpo de verdade
bate com o esquema documentado. Uma das duas:
1. O dono abre o Swagger de testes no PC com o certificado e, se houver "Try it out" ali (não achou em 25/09/2026 —
   pode ser doc só-leitura), executa `GET /DFe/{NSU}` com um NSU real e envia print/JSON da resposta.
2. Montar uma **sonda** que chama o ADN de testes com o certificado do Windows e imprime a resposta crua, sem interpretar.
Depois: remover as tuplas `CANDIDATOS_*` de `contrato.py`, trocar `VERIFICADO` para `True`, rodar a suíte.

## Implicação de negócio
Cada empresa exige o **certificado dela** (ou de mesmo CNPJ raiz). O certificado do escritório não serve para clientes.
Para clientes sem certificado no escritório: investigar **procuração eletrônica** (pendente).

## Evidências do portal (spec §11.1, anonimizadas)
H1: cobertura por período (o portal pode mostrar notas que o ADN não distribuiu). H2: conversão de layout.
