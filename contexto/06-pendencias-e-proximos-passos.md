# 06 — Pendências e próximos passos

## Caminho crítico (em ordem)
1. **Fechar o contrato do ADN** (ver [04](04-adn-e-contrato.md)). Depende do dono: print do Swagger ou rodar a sonda.
2. **Chamada real ao ADN pelo agente**, com o certificado do Windows de cada empresa, gravando no banco (`dfe_bruto` → parser → `nfse`).
3. **Botão "Atualizar tudo"**: percorre as empresas cadastradas e busca as notas novas por NSU, sem passos repetitivos.
4. **Fase 0**: bater AB Engenharia 08/2026 (78 notas, R$ 198.227,91) com o `.pfx` da AB. Não ajustar para bater.

## Decisões abertas
- **Procuração eletrônica** para clientes sem certificado no escritório (investigar).
- **Dados por PC vs central**: o modo local não dá visão de escritório. Reavaliar se for necessário.
- **Assinatura digital** do instalador (SmartScreen) e **HTTPS** no modo servidor.
- Tornar o repositório **privado** (dados fiscais de clientes; hoje é público).

## Melhorias menores
- Validar em Windows real: cópia de segurança, restauração, parar/desinstalar.
- Avisar o Guilherme das mudanças no painel.
- Atualizar o `spec-nfse-nacional.md` para o modelo local (instalação por PC) e o cadastro pelo certificado.
- Apagar o arquivo de diagnóstico grande solto na raiz do repositório (`Invoke-Expression ... .txt`), se ainda existir.
- Higiene: os tokens do GitHub foram colados várias vezes na conversa. **Revogar** os antigos e usar um novo só quando necessário.

## Fora de escopo por enquanto
Robô que automatiza o portal (frágil: layout, captcha, termos). Importação de planilha/XML do portal foi
oferecida como alternativa sem ADN; o dono preferiu a API.
