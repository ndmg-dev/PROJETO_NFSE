# 02 — Arquitetura e decisões

## Mudança de arquitetura (22/09/2026, spec §3.3-A)
- **Sem cofre central de certificados.** O certificado A1 fica **só na estação Windows do contador**
  (Pessoal/CurrentUser\My). Nenhum `.pfx` sobe para servidor nenhum. A migração 0005 removeu o cofre.
- **Consulta sob demanda**, não periódica: o sistema age quando há necessidade.
- **Java para o agente**: o SunMSCAPI usa a chave do Windows sem exportá-la.
- **Modelo escolhido para a instalação (25/09/2026):** "tudo em cada PC, sem Docker": cada
  contador tem o próprio banco e sistema. Sem servidor, sem administrador.
  *Consequência:* não há visão central do escritório nesse modo (ver pendências).

## Componentes
- **API FastAPI** (`app/api/`): auth (JWT), empresas, relatórios, setup (primeiro acesso), instalar.
- **Domínio** (`app/domain/`): parser de DF-e, análise de líquido, retenções, projeção, resumo.
- **Banco** (`app/db/`, `alembic/versions/0001…0007`): multi-tenant com RLS forçada.
- **Workers** (`app/workers/`): laço de sincronização por NSU (pronto, testado com dados simulados).
- **Relatórios** (`app/reports/`): Relação de NFS-e (formato do portal) e Retenções/Divergências.
- **Agente / teste de certificado** (`agente/spike/*.java`): lê o certificado do Windows,
  testa conexão e **cadastra empresas** a partir dos e-CNPJ.
- **Instaladores** (`app/instalador/`): Docker (`Iniciar.bat`) e local Windows (`Instalar-NFSe.bat`).

## Decisões de segurança
- **RLS forçada** (`FORCE ROW LEVEL SECURITY`), papel `nfse_app` sem privilégio (superusuário ignora RLS);
  `set_config('app.escritorio_id', …, true)` local à transação; funções `SECURITY DEFINER`
  (`autenticar`, `setup_concluido`, `criar_primeiro_acesso` com advisory lock).
- **Primeiro acesso protegido por código** (HMAC do `JWT_SECRET`, `XXXX-XXXX`, limitador por origem e global, trava após configurado).
- **XSS**: `textContent`. **Injeção de fórmula**: XLSX vira texto; CSV prefixa apóstrofo em colunas de texto.
- **Host header** sanitizado (`url_servidor_segura`). `.dockerignore` (a imagem já vazou `.env`/`.git` uma vez).
- **Cadastro pelo certificado só fala com `localhost`** (a senha do sistema não sai do PC).
- PostgreSQL local escuta **só em 127.0.0.1**; senhas geradas na máquina, `icacls` restringe arquivos.

## Regras de negócio relevantes
- **Análise de líquido**: cenário estrito (IRRF, contrib. sociais, previdência, ISSQN retido) vs ampliado
  (+PIS/COFINS "débito de apuração própria"). Tolerância de 1 centavo. PIS/COFINS ficam fora do "total retido".
- **Projeção parser → `nfse`** idempotente (upsert por empresa+chave); `situacao` vem dos eventos e
  não é sobrescrita. **A tabela evento→situação (101101 Cancelada, 105102 Substituída) é HIPÓTESE.**
- **Relatório "Relação de NFS-e"** replica o layout do portal (60 colunas; 10 preenchidas hoje, 50 vazias como na referência).
