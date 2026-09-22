# Plataforma de captura de NFS-e Nacional

Captura NFS-e do padrão nacional (ADN / gov.br) para vários CNPJs, cada um com
seu certificado A1, e gera relatórios fiscais. Substitui a exportação manual de
planilhas do Portal Nacional, uma empresa e um mês por vez.

Fonte da verdade do projeto: [spec-nfse-nacional.md](spec-nfse-nacional.md).

## Estado

| Fase | Situação |
|---|---|
| **0 — PoC contra o ADN** | **bloqueada**: falta o certificado A1 |
| 1 — infra, dinheiro, schema, RLS | pronta |
| 1 — cofre, autenticação, API | pronta |
| 1 — relatório com paridade de portal | pronta |
| 1 — parser e sincronização | mecânica pronta; contrato do ADN pendente |
| 2, 3 | não iniciadas |

243 testes. Tudo roda em container.

```bash
cp .env.exemplo .env      # preencha os segredos
make up && make migrate
make test                 # 243 testes
make lint types reversivel
```

## O que falta para desbloquear

Um arquivo `.pfx` da AB Engenharia (CNPJ raiz `07.199.546`) nesta máquina. Com
ele, a sequência está em [poc/README.md](poc/README.md): descobrir o contrato
real, fixar os nomes em [app/adn/contrato.py](app/adn/contrato.py) e
[app/domain/parser.py](app/domain/parser.py), rodar a varredura e comparar com
a referência.

Não há atalho: o Manual dos Contribuintes v1.0 não documenta o formato das
respostas, e o Swagger da produção restrita exige certificado de cliente.

## Duas coisas que precisam de decisão sua

**O cofre está abaixo do exigido pela spec §8.** A chave mestra vem do `.env`;
a spec pede KMS. Serve para desenvolvimento. Antes de qualquer certificado de
cliente real entrar, `EnvolucroKMS` em [app/core/cofre.py](app/core/cofre.py)
precisa ser implementado — hoje ele levanta `NotImplementedError` em vez de
fingir que cifra.

**Não existe procuração eletrônica para as APIs do ADN.** O manual exige
certificado com o mesmo CNPJ raiz do contribuinte consultado. A FENACON pediu
procuração à Receita em 10/06/2026 e não houve resposta até aqui. Na prática: o
escritório precisa custodiar um A1 por grupo econômico, e o termo de custódia
da §8 é requisito, não boa prática.

## Onde as incógnitas moram

Duas fronteiras, ambas marcadas no código e nenhuma espalhada pelo sistema:

- [app/adn/contrato.py](app/adn/contrato.py) — formato da resposta do ADN
- [app/domain/parser.py](app/domain/parser.py) — nomes de tag do XML

Nenhuma das duas escolhe um candidato em silêncio. Sem correspondência, param e
mostram o que realmente veio.
