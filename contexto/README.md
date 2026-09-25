# Contexto do projeto — NFS-e Nacional

Pasta de **retomada**: quem abrir o projeto (pessoa ou IA) depois de um tempo lê isto e sabe
onde está, o que foi decidido, o que está bloqueado e o que fazer em seguida.
Atualizada em 25/09/2026. **Não contém segredos nem dados de clientes**: nunca coloque aqui
token, senha, `.pfx`, DSN ou CNPJ de cliente.

| Arquivo | Para quê |
|---|---|
| [01-objetivo-e-regras.md](01-objetivo-e-regras.md) | O que o projeto é, para quem, a stack e as 8 regras de trabalho |
| [02-arquitetura-e-decisoes.md](02-arquitetura-e-decisoes.md) | Como o sistema é montado e por que cada decisão foi tomada |
| [03-estado-atual.md](03-estado-atual.md) | O que está pronto, o que está testado e o que NÃO foi provado |
| [04-adn-e-contrato.md](04-adn-e-contrato.md) | O que se sabe (e o que não) sobre a API do ADN |
| [05-instalacao-e-distribuicao.md](05-instalacao-e-distribuicao.md) | Instalador do Windows, Release, agente e teste de certificado |
| [06-pendencias-e-proximos-passos.md](06-pendencias-e-proximos-passos.md) | O que falta, em ordem, e o que depende de quem |
| [07-erros-e-licoes.md](07-erros-e-licoes.md) | Erros reais encontrados e como foram resolvidos |
| [08-comandos-e-testes.md](08-comandos-e-testes.md) | Como rodar, testar, gerar e publicar |

Documentos de fonte da verdade que ficam fora desta pasta:
- [../spec-nfse-nacional.md](../spec-nfse-nacional.md): a especificação (leia o adendo §3.3-A).
- [../README.md](../README.md): guia de instalação para o usuário final.

## Retomada em 30 segundos
1. **Onde estamos:** instalação local no Windows funciona (verificado num PC real em 25/09/2026); empresas são cadastradas a partir dos certificados; relatórios funcionam com dados de teste.
2. **Por que os relatórios saem vazios:** nenhuma nota é buscada do ADN ainda.
3. **O bloqueio:** falta o contrato real da API do ADN (campos da resposta), que só aparece no Swagger com certificado. Ver [04](04-adn-e-contrato.md).
4. **Princípio do produto (do dono):** facilitar a vida do contador. Nada de processos repetitivos: instala uma vez, cadastra tudo sozinho, "Atualizar tudo" com um clique.
