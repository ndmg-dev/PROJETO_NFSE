# Plataforma de captura de NFS-e Nacional

Captura NFS-e do padrão nacional (ADN / gov.br) para vários CNPJs, cada um com
seu certificado A1, e gera relatórios fiscais. Substitui a exportação manual de
planilhas do Portal Nacional, uma empresa e um mês por vez.

Fonte da verdade do projeto: [spec-nfse-nacional.md](spec-nfse-nacional.md),
incluindo o adendo de arquitetura §3.3-A (22/09/2026) — leia-o antes de mexer
em autenticação ou sincronização.

## Como instalar

Sem digitar comando nenhum. São duas partes, em lugares diferentes, porque a
arquitetura não é uma coisa só (spec §3.3-A): **um servidor** para o escritório
e o **teste de certificado** em cada estação de contador.

### 1. O servidor (uma vez, em um computador que fique ligado)

Precisa do **Docker**: no Windows, o [Docker Desktop](https://www.docker.com/products/docker-desktop/);
no Linux/Mac, o Docker Engine.

1. Baixe ou clone este repositório.
2. **Windows:** dê duplo clique em **`Iniciar.bat`**.
   **Linux/Mac:** dê duplo clique em (ou rode) **`iniciar.sh`**.
3. O navegador abre sozinho no **assistente de primeiro acesso**. Digite o nome do
   escritório, o seu e-mail e uma senha. Pronto.

O instalador cria as senhas do sistema sozinho (ficam em `.env`, **guarde uma cópia
em local seguro**), sobe o banco e a aplicação, aplica a estrutura do banco e abre
o navegador já com o código de configuração preenchido. Pode rodar de novo quando
quiser: não apaga nada nem troca senha existente. Se o Docker não estiver
instalado ou aberto, ele explica o que fazer.

Para acessar de outros computadores, use o endereço que o instalador mostra no fim
(algo como `http://10.0.0.106:8000`).

### 2. Cada estação de contador (Windows)

1. No navegador da estação, abra **`http://ENDEREÇO-DO-SERVIDOR:8000/instalar`**.
2. Clique em **Baixar o instalador** e abra o arquivo `Instalar-Agente-NFSe.bat`.
3. Espere. Na primeira vez ele baixa uma cópia do Java (cerca de 200 MB, com
   verificação de integridade), prepara tudo e abre a janela do teste.

Não pede permissão de administrador e não precisa instalar Java antes.

### O que ainda não é como você gostaria

- **O agente completo não existe.** O que a estação instala hoje é a **ferramenta de
  teste de certificado** (o spike): ela responde se o certificado A1 já instalado
  pode ser usado sem exportá-lo. Quando o agente existir, o mesmo link o instalará.
- **Os instaladores do Windows não foram executados num Windows.** Os testes rodam
  em PowerShell 7 num container Linux e provam sintaxe, o formato dos arquivos e a
  lógica pura. **Não provam** o Windows PowerShell 5.1, o Docker Desktop, o javac, o
  atalho na Área de Trabalho nem o `SunMSCAPI`. A estrutura do zip real do Java e o
  módulo `jdk.crypto.mscapi` foram conferidos baixando o arquivo de verdade.
- **O instalador da estação não tem assinatura digital.** O Windows vai avisar que
  o arquivo é desconhecido (o `/instalar` explica o que clicar); antivírus mais
  rígidos podem bloqueá-lo.
- **O acesso é por HTTP, sem criptografia.** Numa rede interna de confiança é
  aceitável para começar, mas a senha do administrador e o arquivo do instalador
  trafegam em claro. **Antes de abrir para fora da rede do escritório, coloque HTTPS
  na frente** (um proxy reverso com certificado).
- **Precisa de Docker no servidor.** Num Windows isso significa o Docker Desktop
  rodando; se a máquina desligar, o sistema cai até ela voltar.

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

431 testes Python. Tudo roda em container.


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
