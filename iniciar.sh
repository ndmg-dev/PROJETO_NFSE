#!/usr/bin/env bash
# Instala e inicia o sistema NFS-e nesta máquina. Não pergunta nada:
#   1. cria o .env com senhas aleatórias (só na primeira vez);
#   2. sobe o banco, a fila e a API, aplicando a estrutura do banco sozinho;
#   3. abre o navegador no assistente de primeiro acesso, já com o código.
#
# Precisa do Docker. Pode rodar de novo quando quiser: não apaga nada.
#
#   NFSE_PORTA=9000            usa outra porta (padrão 8000)
#   NFSE_NAO_ABRIR_NAVEGADOR=1 não abre o navegador (útil em servidor sem tela)
set -euo pipefail
cd "$(dirname "$0")"

ARQUIVO="docker-compose.instalacao.yml"
PORTA="${NFSE_PORTA:-8000}"
URL="http://localhost:${PORTA}"

dizer() { printf '%s\n' "$*"; }

if ! command -v docker >/dev/null 2>&1; then
  dizer "O Docker não está instalado nesta máquina."
  dizer "Instale em https://docs.docker.com/get-docker/ e rode este arquivo de novo."
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  dizer "O Docker está instalado, mas não está em execução (ou seu usuário não tem permissão)."
  dizer "Abra o Docker e rode este arquivo de novo."
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  dizer "Falta o Docker Compose v2 (comando 'docker compose')."
  exit 1
fi

# Hexadecimal, não base64: '/' e '+' quebram a URL de conexão com o banco.
hex()    { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }
base64s() { head -c "$1" /dev/urandom | base64 | tr -d '\n'; }

garantir() {  # garantir NOME VALOR — só cria se ainda não existir no .env
  if ! grep -q "^$1=." .env 2>/dev/null; then
    printf '%s=%s\n' "$1" "$2" >> .env
    return 0
  fi
  return 1
}

if [ ! -f .env ]; then
  dizer "Primeira instalação: gerando as senhas do sistema (ficam só neste computador)..."
  (umask 077; : > .env)
fi
novo=0
garantir POSTGRES_PASSWORD "$(hex 24)"   && novo=1 || true
garantir APP_DB_PASSWORD   "$(hex 24)"   && novo=1 || true
garantir JWT_SECRET        "$(base64s 32)" && novo=1 || true
chmod 600 .env
[ "$novo" = 1 ] && dizer "Senhas geradas em .env — guarde uma cópia em local seguro."

LOG="instalacao.log"
dizer "Subindo o sistema (a primeira vez pode levar alguns minutos)..."
if ! docker compose -f "$ARQUIVO" up -d --build >"$LOG" 2>&1; then
  dizer "Não foi possível subir o sistema. Últimas linhas do registro (${LOG}):"
  tail -20 "$LOG"
  exit 1
fi

busca() {
  if command -v curl >/dev/null 2>&1; then curl -fsS --max-time 4 "$1"
  else wget -qO- --timeout=4 "$1"; fi
}

dizer "Esperando o sistema ficar pronto..."
pronto=0
for _ in $(seq 1 90); do
  if busca "${URL}/health" >/dev/null 2>&1; then pronto=1; break; fi
  sleep 2
done
if [ "$pronto" != 1 ]; then
  dizer "O sistema não respondeu a tempo. Veja o que houve com:"
  dizer "  docker compose -f ${ARQUIVO} logs api migrate"
  exit 1
fi

destino="${URL}/"
if ! busca "${URL}/setup/status" 2>/dev/null | grep -q '"configurado":true'; then
  codigo="$(docker compose -f "$ARQUIVO" exec -T api python -m app.setup.codigo | tr -d '\r\n')"
  destino="${URL}/setup?codigo=${codigo}"
fi

dizer ""
dizer "Pronto. Sistema em ${URL}"
if command -v hostname >/dev/null 2>&1; then
  ip="$( (hostname -I 2>/dev/null || true) | awk '{print $1}')"
  [ -n "$ip" ] && dizer "Para acessar de outros computadores da rede: http://${ip}:${PORTA}"
fi

if [ "${NFSE_NAO_ABRIR_NAVEGADOR:-0}" != 1 ]; then
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$destino" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then open "$destino" || true
  fi
fi
dizer "Abra no navegador: ${destino}"
