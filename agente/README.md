# Agente local — spike de validação

Decisão de arquitetura (spec §3.3-A, 22/09/2026): o certificado A1 nunca sobe
para o servidor. Fica na estação do contador, e um agente ali usa a CryptoAPI
do Windows para autenticar mTLS com o ADN sem nunca extrair a chave privada.

## Estado

**Spike, não o agente.** Um programa isolado que responde uma pergunta:
"`SunMSCAPI` consegue fechar um handshake TLS de cliente nesta máquina, com
este JDK?" — antes de investir na comunicação com a API central, na seleção
de certificado por CNPJ raiz, ou em qualquer outra parte do agente completo.

`spike/ProvarHandshakeMTLS.java` — sem Maven, sem dependência, um arquivo só.

## O que já foi verificado, e o que não foi

| | |
|---|---|
| Compila com JDK 21 | ✅ verificado (`javac`, container Linux) |
| Roda no Linux e falha de forma limpa (sem `SunMSCAPI`) | ✅ verificado |
| Handshake mTLS real via `SunMSCAPI` numa estação Windows | ❌ **não verificado** — precisa rodar num Windows de verdade |

`SunMSCAPI` só existe em builds Windows do JDK. Não há como testar a parte que
importa a partir deste ambiente de desenvolvimento — o mesmo tipo de bloqueio
da Fase 0 do projeto (lá, falta certificado para falar com o ADN; aqui, falta
uma máquina Windows para falar com a CryptoAPI).

## Como rodar o teste real

Numa estação Windows com JDK 21+ e um certificado A1 instalado em
`CurrentUser\My`:

```
javac ProvarHandshakeMTLS.java
java ProvarHandshakeMTLS
```

Sem argumento, tenta `https://client.badssl.com/` — um endpoint público que
exige certificado de cliente, só para provar que o handshake acontece (não
valida qual certificado; isso é do lado deles). Para testar contra outro
endpoint: `java ProvarHandshakeMTLS https://...`.

O programa lista todos os certificados da store antes de escolher (pega o
primeiro, sem filtro) — é assim que se vê se o A1 esperado aparece.

## O que este spike deliberadamente não faz

Não escolhe certificado por CNPJ raiz, não fala com a API central, não define
o protocolo agente↔servidor (fila de pedidos, autenticação do agente). Isso é
a etapa "agente completo", que só faz sentido depois deste spike confirmar que
o handshake em si funciona.

## Atenção conhecida, a confirmar no teste real

Há relatos históricos de atrito específico na autenticação TLS de cliente com
`SunMSCAPI` (não é só leitura de certificado — o handshake em si tem bugs
documentados no rastreador do OpenJDK). Se o teste falhar de um jeito
diferente do "provider ausente", é isso que está em jogo, e pode significar
trocar a abordagem (ex.: JNA chamando CryptoAPI diretamente, ou .NET).
