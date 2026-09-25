# 05 — Instalação e distribuição

## Instalador local (caminho principal)
`Instalar-NFSe.bat`: um arquivo só (script PowerShell + pacote zip em base64). Instala em
`%LOCALAPPDATA%\NFSe` sem administrador: Python 3.12.10 embutido, PostgreSQL 16.15 portátil (Zonky),
JDK (Adoptium, para o teste de certificado), o código, atalhos (Área de Trabalho e Menu Iniciar).
Baixa ~250 MB na primeira vez; versões e SHA-256 em `app/instalador/pins.json`
(`python -m app.instalador.verificar_pins`). Idempotente: rodar de novo atualiza e mantém dados e senhas.
Estrutura: `codigo\`, `bin\` (scripts), `python\`, `pgsql\`, `dados\pg\`, `config\` (segredos, portas), `logs\`, `agente\`, `jdk\`.

Scripts de uso: `Abrir-NFSe`, `Parar-NFSe`, `Copia-de-seguranca` (a frio, para Documentos\NFSe-copias),
`Restaurar-copia` (não apaga: move o anterior para `pg.antes-<data>`), `Desinstalar-NFSe` (salva cópia antes).

## Instalador do agente (só o teste de certificado)
`Instalar-Agente-NFSe.bat`, gerado por `python -m app.instalador.agente`.
Janela com 3 botões: ver certificados, testar conexão (o sucesso só é prova se o servidor exigir certificado
de cliente; `badssl.com` responde igual sem certificado), **cadastrar as empresas dos certificados** (lê CNPJ
do CN `RAZAO:14dígitos`, valida o dígito verificador, faz login e cadastra tudo com um só login).

## Modo Docker (alternativa)
`Iniciar.bat` / `iniciar.sh` sobem banco, redis e API; página `/instalar` serve o instalador do agente.

## Publicar uma versão
`make instalador-windows` gera `dist/Instalar-NFSe.bat`; o do agente sai de `python -m app.instalador.agente`.
A Release `v0.1-teste-windows` é atualizada substituindo os assets (API do GitHub). **O repositório é público**:
a Release é baixável por qualquer pessoa. Os arquivos não têm segredos.

## Diagnóstico
`%LOCALAPPDATA%\NFSe\logs\instalacao.log`, `api.log`, `api-erro.log`, `postgres.log`. Não use "Executar como administrador".
