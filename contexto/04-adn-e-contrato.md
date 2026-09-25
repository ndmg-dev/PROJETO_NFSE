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

## NÃO documentado (não inventar)
Nomes dos campos da resposta, como o XML vem embutido (base64? gzip?), nome do parâmetro do CNPJ de
consulta, tamanho do lote, código quando a fila acaba, rate limit, tabela de eventos → situação.
Tudo isso está isolado em `app/adn/contrato.py` (`VERIFICADO=False`) e nas hipóteses de tags em `app/domain/parser.py`.

## Como fechar o contrato (uma das duas)
1. O dono abre o Swagger de testes no PC com o certificado e envia print/JSON de `GET /DFe/{NSU}` (parâmetros e exemplo de resposta).
2. Montar uma **sonda** que chama o ADN de testes com o certificado do Windows e imprime a resposta crua, sem interpretar.
Depois: preencher `contrato.py`, trocar `VERIFICADO` para `True`, rodar a suíte.

## Implicação de negócio
Cada empresa exige o **certificado dela** (ou de mesmo CNPJ raiz). O certificado do escritório não serve para clientes.
Para clientes sem certificado no escritório: investigar **procuração eletrônica** (pendente).

## Evidências do portal (spec §11.1, anonimizadas)
H1: cobertura por período (o portal pode mostrar notas que o ADN não distribuiu). H2: conversão de layout.
