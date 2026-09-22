# Plataforma de captura de NFS-e Nacional

Captura NFS-e do padrão nacional (ADN / gov.br) para vários CNPJs, cada um com
seu certificado A1, e gera relatórios fiscais. Substitui a exportação manual de
planilhas do Portal Nacional, uma empresa e um mês por vez.

Fonte da verdade do projeto: [spec-nfse-nacional.md](spec-nfse-nacional.md),
incluindo o adendo de arquitetura §3.3-A (22/09/2026) — leia-o antes de mexer
em autenticação ou sincronização.

## Estado

| Fase | Situação |
|---|---|
| **0 — PoC contra o ADN** | **bloqueada**: falta o certificado A1 |
| 1 — infra, dinheiro, schema, RLS | pronta |
| 1 — autenticação, API de empresas | pronta |
| 1 — relatório com paridade de portal | pronta |
| 1 — parser e sincronização (mecânica) | pronta; contrato do ADN pendente |
| 1 — agente local (Java + `SunMSCAPI`) | **spike**, não verificado — precisa de estação Windows |
| 2, 3 | não iniciadas |

211 testes Python. Tudo roda em container.

```bash
cp .env.exemplo .env      # preencha os segredos
make up && make migrate
make test                 # 211 testes
make lint types reversivel
```

## Mudança de arquitetura (22/09/2026)

O certificado A1 **não sobe mais para o servidor**. Decisão registrada em
§3.3-A da spec: ele fica na estação do contador, e um agente local o usa por
lá via CryptoAPI/`SunMSCAPI` do Windows — a chave privada nunca é extraída,
exportável ou não. A sincronização deixou de ser agendada (Celery Beat) e
passou a ser **sob demanda**, acionada pelo contador.

Consequência prática: o cofre de certificados da Fase 1 (upload de `.pfx`,
cifra envelope, tabela `certificado`) foi removido — não só desativado. A
migration `0005_remove_certificado.py` desfaz a tabela; o histórico de por que
existia e por que caiu está no próprio commit e na spec.

Um spike isolado prova (ou não) que o handshake mTLS via `SunMSCAPI` funciona:
[agente/README.md](agente/README.md). **Ainda não foi executado** — só compila
neste ambiente Linux; a prova real exige uma estação Windows com o certificado
instalado.

## O que falta para desbloquear a Fase 0

Um arquivo `.pfx` da AB Engenharia (CNPJ raiz `07.199.546`) nesta máquina. Com
ele, a sequência está em [poc/README.md](poc/README.md): descobrir o contrato
real, fixar os nomes em [app/adn/contrato.py](app/adn/contrato.py) e
[app/domain/parser.py](app/domain/parser.py), rodar a varredura e comparar com
a referência.

Não há atalho: o Manual dos Contribuintes v1.0 não documenta o formato das
respostas, e o Swagger da produção restrita exige certificado de cliente.

## O que falta para desbloquear o agente

Uma estação Windows com JDK 21+ para rodar o spike de verdade. Se
`SunMSCAPI` tiver o atrito na autenticação de cliente que o histórico do
OpenJDK relata, a abordagem muda (JNA direto na CryptoAPI, ou .NET) — por
isso o spike vem antes do agente completo, não depois.

## Uma decisão que ainda falta

**Não existe procuração eletrônica para as APIs do ADN.** O manual exige
certificado com o mesmo CNPJ raiz do contribuinte consultado. A FENACON pediu
procuração à Receita em 10/06/2026 e não houve resposta até aqui. Isso não
muda com o agente local — o certificado ainda precisa ser o do próprio
contribuinte (ou da matriz, para as filiais).

## Onde as incógnitas do ADN moram

Duas fronteiras, ambas marcadas no código e nenhuma espalhada pelo sistema:

- [app/adn/contrato.py](app/adn/contrato.py) — formato da resposta do ADN
- [app/domain/parser.py](app/domain/parser.py) — nomes de tag do XML

Nenhuma das duas escolhe um candidato em silêncio. Sem correspondência, param e
mostram o que realmente veio.
