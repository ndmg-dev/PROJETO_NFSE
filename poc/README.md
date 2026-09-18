# Fase 0 — prova de conceito

Objetivo (spec §12): provar que `GET /contribuintes/DFe/{NSU}` devolve o mesmo
conjunto de notas que o Portal Nacional exporta em planilha.

**Critério de aceite:** AB Engenharia (07.199.546/0001-62), 08/2026, como
tomadora — 78 notas, R$ 198.227,91.

## Estado

| Parte | Situação |
|---|---|
| Carga do .pfx, mTLS, tmpfs | escrito, **não exercitado** (falta certificado) |
| Backoff, jitter, `Retry-After` | escrito e testado |
| Conversão de dinheiro (`Decimal`) | escrito e testado |
| Decodificação base64/gzip do DF-e | escrito e testado |
| Tolerância a namespace inesperado | escrito e testado |
| Comparador × planilha | escrito e **executado contra a referência real** |
| **Nomes de campo da resposta do ADN** | **desconhecidos** — bloco HIPÓTESES |
| **Tags do XML da NFS-e** | **desconhecidas** — bloco HIPÓTESES |

O Manual dos Contribuintes v1.0 (12/02/2026) não documenta formato de resposta,
paginação, tamanho de lote nem rate limit. O Swagger da produção restrita exige
certificado de cliente — não há como ler o contrato sem um `.pfx`.

## Instalação

```bash
sudo apt install python3.12-venv      # este ambiente não tem o módulo venv
python3 -m venv .venv && . .venv/bin/activate
pip install -r poc/requirements.txt
```

## Ordem de execução

Com o certificado em mãos, nesta ordem:

```bash
# 1. descobrir o formato da resposta (salva o JSON cru e para)
python poc/fase0_dfe.py --ambiente restrita --pfx ~/certs/ab.pfx --dump-contrato

# 2. descobrir o layout do XML (imprime a árvore de tags e para)
python poc/fase0_dfe.py --ambiente restrita --pfx ~/certs/ab.pfx --inspecionar-xml

# 3. fixar o bloco HIPÓTESES no topo de fase0_dfe.py com os nomes reais

# 4. varredura completa
python poc/fase0_dfe.py --ambiente restrita --pfx ~/certs/ab.pfx
python poc/fase0_dfe.py --ambiente producao  --pfx ~/certs/ab.pfx

# 5. diff contra a planilha do portal
python poc/comparar_referencia.py --xml-dir poc/out/xml
```

A senha é pedida por `getpass` — nunca em `argv` (aparece no `ps` e no
histórico do shell). `NFSE_PFX_PATH` e `NFSE_PFX_PASSWORD` funcionam como
alternativa não interativa.

## Testes

```bash
pytest poc/tests -v
```

Cobrem só o que não depende do contrato do ADN. O mapeamento de campos não é
testado de propósito: mock de contrato desconhecido testa a nossa imaginação,
não o ADN (spec §10, nível "Contrato").

## Segurança

O `.pfx` fica fora do repositório (`.gitignore`). O PEM derivado vive em
`/dev/shm` com modo 600 e é apagado no `finally`. Senha nunca vai para log nem
para mensagem de erro — inclusive na falha de abertura do `.pfx`.
