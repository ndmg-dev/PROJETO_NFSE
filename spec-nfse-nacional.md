# Especificação Técnica — Plataforma de Captura de NFS-e Nacional e Relatórios Fiscais

**Versão:** 0.1 (draft para validação)
**Data:** 18/09/2026
**Contexto:** automatizar o que hoje é feito manualmente no Portal Nacional NFS-e (exportação da "Relação de NFS-e Recebidas", como o arquivo `AB ENGENHARIA LTDA - Recebidas - Completa - 01/08/2026 a 31/08/2026`).

**Premissas fechadas com o solicitante:**

- Escopo documental: **NFS-e padrão nacional** (ADN / gov.br). NF-e, CT-e e NFS-e municipais fora do padrão nacional ficam fora do MVP (ver §11).
- Autenticação: **certificado digital A1 (e-CNPJ)** próprio de cada empresa, mTLS direto nas APIs oficiais. Sem intermediário pago.
- **Multi-empresa** (escritório contábil): vários CNPJs, cada um com seu certificado.
- Stack: **Python — FastAPI + Celery + PostgreSQL**.

---

## 1. Resposta curta: dá para fazer?

Sim. O Sistema Nacional NFS-e expõe uma API REST de contribuintes no ADN (Ambiente de Dados Nacional) com **distribuição de DF-e por NSU** — o mesmo modelo da Distribuição DFe da NF-e. Com o certificado A1 da empresa, você consulta sequencialmente os documentos em que ela aparece como **prestador ou tomador**, guarda os XMLs e gera qualquer relatório em cima da sua própria base.

A parte "baixar" é resolvida por API oficial. A parte "relatório" passa a ser um problema seu de banco de dados — e, por isso, muito mais flexível do que a exportação do portal (que só entrega mês a mês, uma empresa por vez).

Pontos de atenção que definem o projeto:

1. **Cobertura é parcial por desenho.** O padrão nacional só cobre municípios conveniados/aderentes e MEIs. Notas emitidas em municípios com sistema próprio (São Paulo, Rio, muitos outros) **não** aparecem no ADN. Para um escritório contábil isso é decisivo — ver §11.
2. **O modelo é incremental por NSU, não por período.** Você não pergunta "me dê agosto/2026"; você percorre a fila de documentos desde o último NSU lido. O recorte por competência é feito depois, no seu banco.
3. **Certificado A1 por empresa.** O escritório precisa custodiar N certificados e senhas — isso é o maior risco de segurança e compliance do projeto (§8).

---

## 2. Arquitetura

```
                       ┌──────────────────────────┐
     Contador ────────▶│  Web UI (React/Next)     │
                       └───────────┬──────────────┘
                                   │ REST + SSE
                       ┌───────────▼──────────────┐
                       │  API — FastAPI           │
                       │  auth, empresas, consulta│
                       │  relatórios, downloads   │
                       └───────┬──────────┬───────┘
                               │          │
                 ┌─────────────▼──┐   ┌───▼────────────────┐
                 │ PostgreSQL     │   │ Redis (broker)     │
                 │ + object store │   └───┬────────────────┘
                 │   (XML/PDF)    │       │
                 └────────────────┘   ┌───▼────────────────┐
                                      │ Celery workers      │
                                      │  • sync_dfe         │
                                      │  • parse_xml        │
                                      │  • fetch_danfse     │
                                      │  • build_report     │
                                      └───┬─────────────────┘
                                          │ mTLS (cert A1 por empresa)
                                      ┌───▼─────────────────┐
                                      │ ADN NFS-e Nacional  │
                                      │ adn.nfse.gov.br     │
                                      └─────────────────────┘
```

Componentes:

| Componente | Responsabilidade |
|---|---|
| **API (FastAPI)** | CRUD de empresas/certificados, disparo de sincronizações, consultas, geração e download de relatórios, webhooks |
| **Worker de sincronização** | Loop de NSU por empresa, com backoff e respeito a rate limit |
| **Parser** | XML NFS-e → modelo relacional normalizado |
| **Cofre de certificados** | Armazenamento cifrado dos .pfx + senhas (KMS/Vault), nunca em disco claro |
| **Gerador de relatórios** | XLSX/PDF/CSV a partir do banco |
| **Agendador (Celery Beat)** | Sincronização periódica por empresa |

---

## 3. Integração com o ADN

### 3.1 Ambientes

| Ambiente | Base URL |
|---|---|
| Produção | `https://adn.nfse.gov.br` |
| Produção restrita (homologação) | `https://adn.producaorestrita.nfse.gov.br` |
| Swagger contribuintes | `https://adn.producaorestrita.nfse.gov.br/contribuintes/docs/index.html` |
| SEFIN Nacional (emissão — fora do MVP) | `https://sefin.nfse.gov.br/SefinNacional` |

### 3.2 Endpoints usados

| Método | Rota | Uso |
|---|---|---|
| `GET` | `/contribuintes/DFe/{NSU}` | Distribuição incremental: retorna o lote de documentos a partir do NSU informado |
| `GET` | `/contribuintes/NFSe/{chaveAcesso}` | Recupera o XML de uma NFS-e específica |
| `GET` | `/contribuintes/NFSe/{chaveAcesso}/Eventos` | Eventos vinculados (cancelamento, substituição) |
| `GET` | `/danfse/{chaveAcesso}` | PDF da DANFSE |

> **A validar em homologação antes do build:** nomes exatos dos campos de resposta, se a paginação usa `maxNSU`/`ultNSU`, o teto de documentos por chamada e o intervalo mínimo entre requisições. O manual oficial não fixa esses limites em texto; a suíte de contrato (§10) existe justamente para travar isso.

### 3.3 Autenticação

mTLS: o cliente HTTP apresenta o certificado A1 (e-CNPJ) da empresa. A regra oficial é que o **CNPJ raiz do certificado** precisa corresponder ao do contribuinte consultado — o que permite um certificado da matriz consultar as filiais, mas **não** um certificado do escritório consultar clientes. Cada empresa-cliente precisa fornecer o próprio A1 (ou uma procuração eletrônica equivalente, se disponível).

Implementação Python:

```python
import httpx, ssl, tempfile
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

def build_client(pfx_bytes: bytes, password: bytes, base_url: str) -> httpx.Client:
    key, cert, chain = pkcs12.load_key_and_certificates(pfx_bytes, password)
    ctx = ssl.create_default_context()
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
        f.write(cert.public_bytes(Encoding.PEM))
        for c in (chain or []):
            f.write(c.public_bytes(Encoding.PEM))
        f.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        path = f.name
    ctx.load_cert_chain(path)          # arquivo em tmpfs, apagado logo após
    return httpx.Client(base_url=base_url, verify=ctx, timeout=60.0)
```

Regras: o PEM temporário vive em **tmpfs** e é removido no `finally`; a senha nunca vai para log; um pool de clientes por empresa evita reconstruir o contexto TLS a cada chamada.

### 3.3-A. ADENDO (22/09/2026) — custódia sai do servidor, agente local entra

**Revoga a custódia central de certificado descrita acima e em §4/§6/§8.** Decisão do solicitante, registrada aqui em vez de contornada em silêncio (regra 8 do projeto).

**O que muda:**

- O `.pfx` **nunca sobe para o servidor**. Ele continua onde já está hoje: instalado no repositório do Windows (`CurrentUser\My`) da estação de cada contador.
- Um **agente local**, instalado na estação do contador, lê o certificado diretamente da store do Windows via CryptoAPI/CNG — sem nunca extrair a chave privada, exportável ou não.
- **Tecnologia do agente: Java, com o provider `SunMSCAPI`** (`KeyStore.getInstance("Windows-MY", "SunMSCAPI")`). É um provider padrão do JDK, feito exatamente para isto: TLS de cliente usando certificado da store do Windows. Empacotado com `jpackage` como instalador nativo — o contador não instala JDK à parte.
  - Atenção conhecida: há relatos de atrito específico na autenticação TLS de cliente com `SunMSCAPI` (não é só leitura de certificado). Por isso o projeto começa por um **spike isolado** (`agente/`) que só prova o handshake mTLS antes de construir o resto.
  - `SunMSCAPI` não tem controle de senha por certificado: qualquer processo rodando como aquele usuário do Windows acessa qualquer certificado da store sem prompt. Mesmo modelo de segurança do navegador — não é risco novo, mas é diferente do cofre cifrado que caiu.
- **A sincronização deixa de ser agendada e passa a ser sob demanda.** O contador aciona pela tela; não há mais Celery Beat rodando a cada 4h esperando um certificado que pode não estar disponível (estação desligada, contador deslogado). O modelo por NSU já tolera isso: retoma de onde parou, e o alerta de `nsu_lag` (§9) passa a cobrir "sem sincronizar há X dias" em vez de "atrasou 4h".
- **Fluxo:** contador clica "sincronizar" → API cria o pedido (mesmo contrato de `POST /empresas/{id}/sync`, 202 + task_id, §6) → o agente da estação daquele contador identifica o pedido (poll ou SSE) → agente faz o mTLS com o ADN e devolve os bytes crus da resposta para a API → o servidor interpreta a resposta (parser, checkpoint, idempotência — lógica já escrita e testada, indiferente a quem fez a chamada de rede) e persiste.
- **Consequência prática:** o agente é "burro" de propósito — só seguro o certificado e transporta bytes. Toda a lógica de contrato do ADN, checkpoint, idempotência e detecção de lacuna continua em Python, testada, um lugar só. Isso evita duplicar em Java a mesma hipótese de contrato que §3.2 já isola.

**O que cai, do que estava planejado em §4/§6/§8:** tabela `certificado`, upload de `.pfx` por API, cofre com KMS/Vault. O maior risco do projeto (§8, custódia de N certificados) deixa de existir por desenho — não porque foi mitigado, porque o servidor nunca chega a tocar o segredo.

**O que fica em aberto:** o protocolo exato entre agente e servidor (fila de pedidos, autenticação do próprio agente, como casar "empresa X no sistema" com "certificado Y na store pelo CNPJ raiz") é desenho da próxima etapa ("agente completo"), depois do spike validar o handshake.

### 3.4 Algoritmo de sincronização

```
sync_empresa(empresa_id):
    lock = redis.lock(f"sync:{empresa_id}", ttl=15min)   # evita concorrência
    nsu = empresa.ultimo_nsu
    while True:
        resp = GET /contribuintes/DFe/{nsu+1}
        if resp.status == 204 or lote vazio:            # fim da fila
            break
        for doc in resp.documentos:
            persistir_documento_bruto(doc)               # idempotente por (empresa, nsu)
            enfileirar parse_xml(doc)
            nsu = max(nsu, doc.nsu)
        empresa.ultimo_nsu = nsu                         # commit a cada lote
        if nsu >= resp.maxNSU: break
        sleep(intervalo_minimo)
    lock.release()
```

Invariantes:

- **Idempotência**: `UNIQUE (empresa_id, nsu)`; reprocessar um lote nunca duplica nota.
- **Checkpoint por lote**, não no fim — queda no meio da varredura retoma de onde parou.
- **Backoff exponencial** com jitter em 429/5xx; respeito a `Retry-After`.
- **Fila morta**: documento que falhar no parse 3× vai para `documentos_erro` com o XML bruto preservado, e gera alerta — nunca é descartado.
- **Sem lacuna**: o NSU é a garantia de completude. Um `gap` detectado (NSU ausente entre dois lotes) vira um alerta de auditoria, não um silêncio.

Agendamento sugerido: a cada 4h em dias úteis, mais varredura diária de eventos (cancelamentos/substituições chegam depois da nota original).

---

## 4. Modelo de dados (PostgreSQL)

```sql
-- tenancy
create table escritorio (id uuid primary key, nome text not null, created_at timestamptz default now());

create table usuario (
  id uuid primary key, escritorio_id uuid references escritorio,
  email citext unique not null, senha_hash text not null,
  papel text not null check (papel in ('admin','operador','leitura')),
  mfa_secret text, ativo bool default true
);

create table empresa (
  id uuid primary key, escritorio_id uuid references escritorio not null,
  cnpj char(14) not null, razao_social text not null,
  inscricao_municipal text, municipio_ibge char(7), regime_tributario text,
  ultimo_nsu bigint default 0,
  sync_ativo bool default true, ultimo_sync_at timestamptz, ultimo_sync_status text,
  unique (escritorio_id, cnpj)
);

-- REVOGADA pelo adendo de §3.3-A (22/09/2026): sem custódia central, sem
-- tabela certificado. O agente local nunca envia .pfx/senha para o servidor.
-- create table certificado ( ... );

-- documentos
create table dfe_bruto (
  id bigserial primary key, empresa_id uuid references empresa not null,
  nsu bigint not null, tipo_documento text,          -- NFSe | Evento
  chave_acesso char(50), xml_path text not null,     -- object store
  hash_sha256 char(64) not null, recebido_em timestamptz default now(),
  status text default 'pendente',                    -- pendente|processado|erro
  unique (empresa_id, nsu)
);

create table nfse (
  id bigserial primary key, empresa_id uuid references empresa not null,
  chave_acesso char(50) not null,
  numero text, data_geracao timestamptz, competencia date,
  papel text not null check (papel in ('prestador','tomador')),
  prestador_cnpj char(14), prestador_nome text, prestador_im text,
  tomador_cnpj char(14), tomador_nome text, tomador_im text,
  municipio_incidencia char(7),
  valor_servico numeric(15,2), desconto_incondicionado numeric(15,2),
  base_calculo numeric(15,2), aliquota_issqn numeric(7,4), valor_issqn numeric(15,2),
  issqn_retido bool, tributacao_issqn text, simples_nacional bool,
  cod_tributacao_nacional text, item_nbs text, descricao_servico text,
  -- reforma tributária (IBS/CBS) — colunas presentes no layout atual
  cst_ibs_cbs text, class_trib_ibs_cbs text, indicador_operacao text,
  bc_ibs_cbs numeric(15,2),
  aliq_cbs numeric(7,4), aliq_efetiva_cbs numeric(7,4), valor_cbs numeric(15,2),
  aliq_ibs_estadual numeric(7,4), valor_ibs_estadual numeric(15,2),
  aliq_ibs_municipal numeric(7,4), valor_ibs_municipal numeric(15,2),
  valor_ibs_total numeric(15,2),
  -- retenções federais
  sit_trib_pis_cofins text, bc_pis_cofins numeric(15,2),
  pis_aliquota numeric(7,4), pis_debito numeric(15,2),
  cofins_aliquota numeric(7,4), cofins_debito numeric(15,2),
  irrf numeric(15,2), contrib_sociais_retidas numeric(15,2), contrib_previd_retida numeric(15,2),
  pct_total_tributos_sn numeric(7,4),
  informacoes_complementares text,
  situacao text not null default 'Normal',           -- Normal|Cancelada|Substituída
  dfe_bruto_id bigint references dfe_bruto,
  unique (empresa_id, chave_acesso)
);
create index on nfse (empresa_id, competencia);
create index on nfse (empresa_id, data_geracao);
create index on nfse (prestador_cnpj);

create table nfse_evento (
  id bigserial primary key, nfse_id bigint references nfse not null,
  tipo_evento text not null, autor text, data_evento timestamptz,
  data_registro timestamptz, motivo text, xml_path text,
  unique (nfse_id, tipo_evento, data_evento)
);

create table relatorio (
  id uuid primary key, escritorio_id uuid references escritorio not null,
  empresa_ids uuid[], tipo text, periodo_inicio date, periodo_fim date,
  formato text, filtros jsonb, status text, arquivo_path text,
  solicitado_por uuid references usuario, created_at timestamptz default now()
);

create table audit_log (
  id bigserial primary key, escritorio_id uuid, usuario_id uuid,
  acao text not null, recurso text, detalhe jsonb, ip inet, created_at timestamptz default now()
);
```

Isolamento multi-tenant: **Row-Level Security** no Postgres com `escritorio_id` vindo do JWT via `SET LOCAL app.escritorio_id`. Não confiar apenas no filtro na camada de aplicação.

---

## 5. Camada de relatórios

### 5.1 Relatório "Relação de NFS-e" (paridade com o portal)

Reproduz exatamente as duas abas do arquivo atual:

**Aba `Relação`** — 60 colunas, na mesma ordem do export do portal (de `Número NFS-e` a `Chave NFS-e`), ordenada por `data_geracao` decrescente.

**Aba `Resumo`** — agregado por situação:

| Situação | Qtd | Valor (R$) |
|---|---|---|
| Normal | … | … |
| Cancelada | … | … |
| Substituída | … | … |
| **Total** | … | … |

Mais o rodapé `Gerado em: dd/mm/aaaa, hh:mm:ss`.

Parâmetros: empresa(s), período (por data de geração **ou** competência), papel (recebidas = `tomador`, emitidas = `prestador`), situações incluídas, formato (XLSX/CSV/PDF).

> Um ponto de qualidade que o portal não entrega: na planilha atual o total sai como `198227.90999999997`. Usando `numeric` no banco e `Decimal` em Python, o relatório fecha em `198.227,91` — sem ruído de ponto flutuante.

### 5.2 Relatórios adicionais (o ganho real sobre o portal)

- **Consolidado multi-empresa**: um XLSX por competência com todas as empresas do escritório — hoje é N exportações manuais.
- **Por fornecedor**: ranking de prestadores, com recorrência e variação mês a mês.
- **Retenções**: ISSQN retido, IRRF, INSS, PIS/COFINS — insumo direto para DCTFWeb/EFD-Reinf.
- **IBS/CBS**: acompanhamento da transição da reforma tributária (colunas já existem no layout).
- **Divergências e alertas**: notas canceladas após o fechamento contábil, competência fora do período, prestador novo, valor fora do padrão histórico.
- **Conciliação**: CSV/OFX de pagamentos × notas recebidas (fase 2).

Geração: `openpyxl` para XLSX, `WeasyPrint` para PDF, streaming por chunks para volumes grandes; execução em worker Celery com resultado em object store e link assinado de curta duração.

---

## 6. API interna (FastAPI)

```
POST   /auth/login                      → JWT (access 15min / refresh 7d), MFA opcional
POST   /auth/refresh

GET    /empresas                        → lista (paginada, escopo do escritório)
POST   /empresas                        → cadastra CNPJ
GET    /empresas/{id}
PATCH  /empresas/{id}                   → sync_ativo, dados cadastrais
-- REVOGADO por §3.3-A: sem upload de certificado. O agente local casa
-- "empresa X" com "certificado Y da store" pelo CNPJ raiz, sem passar pela API.
-- POST   /empresas/{id}/certificado       → upload .pfx + senha (multipart)
-- DELETE /empresas/{id}/certificado/{cid}

POST   /empresas/{id}/sync              → dispara sincronização sob demanda; o agente
                                          da estação do contador atende o pedido (§3.3-A)
GET    /empresas/{id}/sync/status       → ultimo_nsu, status, pendências
GET    /sync/eventos                    → SSE com progresso em tempo real

GET    /nfse                            → filtros: empresa_id[], papel, competencia_de/ate,
                                          data_de/ate, situacao[], prestador_cnpj, valor_min/max
                                          + paginação por cursor
GET    /nfse/{chave}                    → detalhe completo
GET    /nfse/{chave}/xml                → XML original
GET    /nfse/{chave}/danfse             → PDF (cache local; busca no ADN se ausente)
GET    /nfse/{chave}/eventos

POST   /relatorios                      → cria job (202 + relatorio_id)
GET    /relatorios/{id}                 → status
GET    /relatorios/{id}/download        → URL assinada

POST   /webhooks                        → registra callback (nota_nova, nota_cancelada, sync_falhou)
GET    /health  /metrics                → liveness + Prometheus
```

Convenções: erros em RFC 7807 (`application/problem+json`); `Idempotency-Key` em todos os POST que criam jobs; rate limit por escritório; OpenAPI gerado automaticamente.

---

## 7. Parser de XML

Responsabilidade isolada em um módulo testável, sem I/O de rede:

```python
def parse_nfse(xml: bytes) -> NFSeDTO: ...
def parse_evento(xml: bytes) -> EventoDTO: ...
```

Regras:

- Validação contra o **XSD oficial** antes do mapeamento; falha de schema → `documentos_erro`, nunca gravação parcial.
- O **XML bruto é a fonte da verdade** e fica armazenado para sempre (guarda fiscal de 5 anos, na prática 10). O banco relacional é uma projeção reconstruível — deve ser possível **reprocessar toda a base** a partir dos XMLs quando o layout mudar.
- Versionamento de layout: campo `versao_layout` no `dfe_bruto`, com parser por versão. A reforma tributária vai mudar o layout mais de uma vez até 2033.
- Evento de cancelamento/substituição atualiza `nfse.situacao` e mantém o histórico em `nfse_evento`.

---

## 8. Segurança e conformidade

Este é o capítulo que decide se o sistema pode existir em um escritório contábil.

> **Revisado por §3.3-A (22/09/2026):** com o certificado ficando na estação do
> contador e nunca subindo para o servidor, os itens abaixo (KMS, decifrar em
> memória do worker, alerta de vencimento) deixam de ser responsabilidade do
> servidor e passam a ser do agente local — que lê metadados de validade
> diretamente da store do Windows, sem precisar decifrar nada. O texto original
> fica como registro de por que a custódia central foi descartada, não como
> especificação vigente.

**Certificados digitais (histórico — arquitetura revogada).** O .pfx e a senha são credenciais que permitem assinar em nome do cliente. Exigências mínimas:

- Cifrados em repouso com chave gerenciada por KMS (AWS KMS, GCP KMS ou HashiCorp Vault) — **não** com chave no `.env`.
- Decifrados apenas em memória do worker, pelo tempo da requisição; PEM temporário em tmpfs.
- Nunca logados, nunca em backup em claro, nunca expostos por API (só metadados: titular, validade).
- Alerta automático 30/15/7 dias antes do vencimento.
- Termo de custódia assinado por cliente, registrando a autorização de uso — proteção jurídica do escritório.

**Dados.** LGPD: a base contém CNPJ/CPF de prestadores e valores. Retenção definida, direito de exclusão por empresa, `audit_log` de todo acesso a dados de terceiros, TLS 1.2+ em tudo, criptografia em repouso no banco e no object store.

**Acesso.** MFA obrigatório para `admin`; papéis `admin`/`operador`/`leitura`; RLS no banco; segregação por escritório testada explicitamente (teste que tenta ler dados de outro tenant e **deve** falhar).

---

## 9. Operação

- **Observabilidade**: logs estruturados JSON com `empresa_id`/`nsu` correlacionados; métricas Prometheus (`sync_duration`, `docs_por_sync`, `erros_parse`, `nsu_lag`); Sentry para exceções.
- **Alertas**: sincronização falhando 2× seguidas, certificado vencendo, `nsu_lag` parado, taxa de erro de parse > 1%.
- **Backup**: Postgres PITR diário; object store com versionamento e replicação; **teste de restore trimestral** (backup não testado não é backup).
- **Deploy**: Docker Compose no MVP; Kubernetes se o número de empresas crescer. Migrations com Alembic, sempre reversíveis.
- **Capacidade**: ~100 empresas × ~100 notas/mês = ~10 mil notas/mês. Carga trivial para Postgres; o gargalo é a latência do ADN, não o banco. Paralelizar por empresa, nunca por NSU dentro da mesma empresa.

---

## 10. Testes

| Nível | Escopo |
|---|---|
| Unidade | Parser (XMLs reais anonimizados, incluindo casos degenerados), cálculos do resumo, formatação monetária |
| Contrato | Suíte contra produção restrita que trava o comportamento real do ADN: formato do lote, paginação, 204 de fila vazia, rate limit, erros |
| Integração | Ciclo completo sync → parse → relatório com ADN mockado (`respx`) |
| Segurança | Tentativa de acesso cross-tenant deve falhar; certificado não deve aparecer em log nem em resposta |
| Regressão de paridade | Relatório gerado × planilha exportada do portal para o mesmo período — **diff zero** (exceto a correção de arredondamento do total) |

O último é o critério de aceite mais importante do MVP: reproduzir agosto/2026 da AB Engenharia e bater linha a linha com o arquivo existente (78 notas, R$ 198.227,91).

---

## 11. Riscos e limitações

| Risco | Impacto | Mitigação |
|---|---|---|
| **Cobertura municipal parcial** — municípios com sistema próprio não estão no ADN | Alto. Para um escritório, pode significar que boa parte das notas não é capturada | Mapear, antes do build, quais municípios dos clientes são conveniados. Se a cobertura for baixa, o projeto precisa de uma camada adicional (§12) |
| Layout muda com a reforma tributária (IBS/CBS até 2033) | Médio-alto | Parser versionado + XML bruto preservado + reprocessamento em massa |
| Rate limit / instabilidade do ADN | Médio | Backoff, fila, sincronização assíncrona, alerta de lag |
| Vazamento de certificado | Crítico | KMS, tmpfs, auditoria, termo de custódia |
| CNPJ raiz do certificado limita a consulta | Médio | Coleta de um A1 por grupo econômico; validar no cadastro |
| Certificado vencido interrompe a captura silenciosamente | Médio | Alerta proativo por validade e por falha de handshake |

---

## 12. Roadmap

**Fase 0 — Prova de conceito (1–2 semanas).** Script isolado: certificado A1 da AB Engenharia → `GET /contribuintes/DFe/{NSU}` em produção restrita e produção → contar documentos de agosto/2026 e comparar com as 78 notas da planilha. **Gate de decisão**: se a API não devolver o mesmo conjunto, o problema é de cobertura e a arquitetura muda.

**Fase 1 — MVP (4–6 semanas).** Multi-empresa, cofre de certificados, sincronização agendada, parser, relatório com paridade de portal em XLSX, UI de consulta.

**Fase 2 — Valor incremental (4 semanas).** Relatórios consolidados e de retenções, DANFSE em lote, alertas de cancelamento, webhooks, exportação para o sistema contábil.

**Fase 3 — Extensões.** NF-e (Distribuição DFe da SEFAZ — modelo muito parecido, reusa toda a arquitetura de NSU), CT-e, municípios fora do padrão nacional (por integração direta ou por provedor comercial como fallback), conciliação financeira, emissão via SEFIN Nacional.

---

## 13. Decisões em aberto

1. Quais municípios concentram os prestadores dos clientes do escritório? (define a viabilidade — ver Fase 0)
2. O sistema precisa **emitir** NFS-e também, ou só capturar?
3. Há um sistema contábil de destino (Domínio, Alterdata, Questor…) que deva receber exportação em layout próprio?
4. Hospedagem: nuvem pública ou servidor do escritório? (afeta a estratégia de KMS)
5. O escritório já custodia os certificados A1 dos clientes hoje, ou isso seria novo? (define o esforço jurídico/operacional)

---

## Fontes

- [Manual dos Contribuintes — APIs ADN, Sistema Nacional NFS-e (gov.br)](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-apis-adn-sistema-nacional-nfse.pdf)
- [APIs — produção restrita e produção (gov.br/nfse)](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao)
- [Guia para utilização das APIs do Emissor Público — Manual dos Contribuintes v1.2 (out/2025)](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-emissor-publico-api-sistema-nacional-nfs-e-v1-2-out2025.pdf)
- [Documentação Técnica — Padrão NFS-e Nacional (Tecnospeed)](https://atendimento.tecnospeed.com.br/hc/pt-br/articles/38360053945367-Documenta%C3%A7%C3%A3o-T%C3%A9cnica-Padr%C3%A3o-NFS-e-Nacional)
- [Nota Técnica 2014.002 — Web Service de Distribuição de DF-e (modelo de referência por NSU)](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=wLVBlKchUb4%3D)
