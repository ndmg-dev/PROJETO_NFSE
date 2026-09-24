# Plataforma de captura de NFS-e Nacional

Captura NFS-e do padrão nacional (ADN / gov.br) para vários CNPJs, cada um com
seu certificado A1, e gera relatórios fiscais. Substitui a exportação manual de
planilhas do Portal Nacional, uma empresa e um mês por vez.

Fonte da verdade do projeto: [spec-nfse-nacional.md](spec-nfse-nacional.md),
incluindo o adendo de arquitetura §3.3-A (22/09/2026) — leia-o antes de mexer
em autenticação ou sincronização.

## Como instalar

Sem digitar comando nenhum. O caminho principal é **tudo em cada computador
Windows do contador, sem Docker e sem servidor**: cada um tem o próprio banco, o
sistema e o teste de certificado (spec §3.3-A).

### Windows (caminho principal)

Precisa de Windows 10 ou mais novo, internet na primeira vez (cerca de 250 MB, com
verificação de integridade) e ~1,5 GB livres. **Não pede administrador.**

1. Consiga o arquivo **`Instalar-NFSe.bat`** (quem mantém o projeto o gera com
   `make instalador-windows`; ele fica em `dist/`).
2. Dê **duplo clique**. Se o Windows avisar que o arquivo é desconhecido, clique
   em *Mais informações* → *Executar assim mesmo* (o instalador não tem assinatura digital).
3. Espere. Ele instala o Python, o banco PostgreSQL e o sistema em
   `%LOCALAPPDATA%\NFSe`, cria as senhas sozinho e abre o navegador no
   **assistente de primeiro acesso**: nome do escritório, e-mail e senha.

Ficam atalhos na Área de Trabalho e no Menu Iniciar (pasta *NFS-e*): abrir o
sistema, parar, **cópia de segurança**, restaurar e desinstalar, mais o teste de
certificado. Rodar o instalador de novo atualiza o código e **mantém os dados**.

A cópia de segurança vai para *Documentos\NFSe-copias*. Ela inclui as senhas do
sistema (sem elas o banco restaurado não abriria): **guarde em lugar seguro**. O
desinstalar sempre salva uma cópia antes de apagar. Se der erro, mande o arquivo
`%LOCALAPPDATA%\NFSe\logs\instalacao.log`.

### Alternativa: servidor com Docker (um para o escritório)

Para quem prefere um servidor central: precisa do Docker (Docker Desktop no
Windows). Dê duplo clique em **`Iniciar.bat`** (Windows) ou **`iniciar.sh`**
(Linux/Mac); o navegador abre no assistente. As senhas ficam em `.env` (**guarde
uma cópia**). As estações baixam o teste de certificado em
`http://ENDEREÇO-DO-SERVIDOR:8000/instalar`.

### O que ainda não é como você gostaria

- **Nenhum instalador foi executado num Windows.** Os testes rodam em PowerShell 7
  num container Linux e provam sintaxe, o pacote e a lógica pura; um ensaio Linux
  usa os mesmos binários do PostgreSQL e prova a sequência (banco, migrations, API,
  reinício, cópia e restauração). **Não provam** o Windows PowerShell 5.1, o
  `postgres.exe`/`python.exe` do Windows, atalhos, caixas de mensagem, SmartScreen
  nem o `SunMSCAPI`. O primeiro teste real precisa de um PC Windows; me devolva o `instalacao.log`.
- **O agente completo não existe.** A estação só tem a **ferramenta de teste de
  certificado**, que diz se o certificado A1 já instalado pode ser usado sem
  exportá-lo. A sincronização com o ADN ainda depende da Fase 0 (certificado da AB
  e contrato do ADN).
- **Sem assinatura digital**: o Windows e alguns antivírus vão desconfiar.
- **Dados por computador**: cada PC tem o próprio banco; não há visão central do
  escritório nesse modo.
- **Python 3.12.10 embutido** não recebe correções de segurança posteriores; o
  banco usa ordenação sem acento (`--locale=C`).
- **Modo Docker: acesso por HTTP sem criptografia.** Coloque HTTPS na frente
  antes de abrir para fora da rede do escritório. No modo local o acesso é só
  por 127.0.0.1.

### Para quem desenvolve

O `docker-compose.yml` é o de desenvolvimento (monta o código do disco). O de
instalação é o `docker-compose.instalacao.yml`, usado só pelos instaladores.

```bash
cp .env.exemplo .env      # ou rode iniciar.sh uma vez, que cria o .env
make up && make migrate
make test                 # testes Python, contra Postgres real
make test-web             # páginas HTML em jsdom (Node, via Docker)
make test-windows         # instaladores do Windows em PowerShell 7 (via Docker)
make lint types reversivel
```

## Estado

| Fase | Situação |
|---|---|
| **0 — PoC contra o ADN** | **bloqueada**: falta o certificado A1 |
| 1 — infra, dinheiro, schema, RLS | pronta |
| 1 — autenticação, API de empresas | pronta |
| 1 — relatório com paridade de portal | pronta |
| 1 — relatório de retenções e divergências de líquido | pronto; com dado real, depende do contrato do ADN |
| 1 — parser, sincronização e projeção para `nfse` (mecânica) | pronta; contrato do ADN pendente |
| 1 — instalação: assistente de primeiro acesso, instalador do servidor e da estação | pronta; instaladores do Windows não executados num Windows |
| 1 — agente local (Java + `SunMSCAPI`) | **spike**, não verificado — precisa de estação Windows |
| 2, 3 | não iniciadas |

443 testes Python. Tudo roda em container.


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
