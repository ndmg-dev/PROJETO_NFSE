# 03 — Estado atual (25/09/2026)

Repositório: https://github.com/ndmg-dev/PROJETO_NFSE (**público**). Branch `main`, último commit `6e0ea40`.
Release de teste: `v0.1-teste-windows` (pré-lançamento) com `Instalar-NFSe.bat` e `Instalar-Agente-NFSe.bat`.

## Verificado num Windows real (25/09/2026, PC do dono)
- `Instalar-NFSe.bat` percorre os 7 passos, abre o navegador em `http://localhost:8000/` e o painel carrega.
- O teste de certificado lista o e-CNPJ instalado em Pessoal e lê o CNPJ/razão social.
- O botão de cadastro cria as empresas no painel.
- Os relatórios são gerados (vazios: não há notas no banco).

## Testado só em Linux/PowerShell 7 (não prova o Windows PowerShell 5.1)
- 443 testes Python (`make test`), lint limpo (`make lint`), tipos (`make types`).
- Testes PowerShell (`make test-windows`), páginas em jsdom (`make test-web`),
  ensaio da instalação local com os mesmos binários PostgreSQL (`make test-local`, inclui cópia/restauração),
  lógica Java do cadastro contra servidor de mentira (`make test-agente`).

## NÃO provado / não existe
- **Nenhuma nota real foi buscada.** O contrato do ADN é `VERIFICADO=False`.
- **O agente completo não existe** (botão "Atualizar tudo" / sincronização pelo certificado).
- Cópia de segurança e restauração, atalhos de parar/desinstalar: testados só em Linux/PS7.
- Instalador sem assinatura digital (SmartScreen avisa). Acesso HTTP sem TLS fora do modo local.
- Python 3.12.10 embutido não recebe patches posteriores; PG com `--locale=C` (ordenação sem acento).
- Cópia de segurança inclui `config\segredos.json` (sensível).
- O painel foi testado com a API real só pelos contratos; a janela Java de cadastro foi confirmada em campo, não em teste automatizado.
