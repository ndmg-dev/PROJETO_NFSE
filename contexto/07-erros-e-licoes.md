# 07 — Erros reais e lições

| Problema | Causa | Correção / lição |
|---|---|---|
| RLS não valia | Superusuário ignora RLS | Papel `nfse_app` sem privilégio; `FORCE ROW LEVEL SECURITY` |
| `SET LOCAL` recusava parâmetro | Não aceita bind | `set_config(..., true)` |
| Login quebrado pela RLS | Precisa ler antes de saber o tenant | Função `SECURITY DEFINER autenticar` |
| 503 lido como "fila vazia" (perda silenciosa) | Corpo vazio antes do status | Checar status retentável primeiro + teste de regressão |
| `make test-web` nunca falhava | `PIPESTATUS` no `sh` | Sem pipe; provado com mutação |
| Imagem Docker vazava `.env`/`.git` | Sem `.dockerignore` | `.dockerignore` + teste |
| Redis obrigatório impedia API local | Import/config | Opcional; guarda estática de imports |
| `.bat` quebrou no Windows ("Invoke-Expression linha 811") | O corte do script incluía o base64 do pacote | Cortar antes de `#PAYLOAD#`; testes agora **executam a linha real do .bat** |
| "Não pode encontrar o arquivo" no passo 3 | `Postgres-Rodando` executava `pg_ctl.exe` inexistente | Retorna falso sem o binário/banco; teste + mutante |
| "Pasta em uso por outro processo" | Processos de tentativa anterior/antivírus; elevado não é inspecionável | Encerra processos da pasta, repete a troca 8×, avisa o que não consegue ver; **não rodar como admin** |
| Teste de certificado dizia "SUCESSO" sem certificado | Mensagem afirmava o que não ocorreu | "NADA FOI TESTADO" sem certificado; aviso de que `badssl.com` não prova nada |
| Restauração de cópia não subia no ensaio | Zip sem pastas vazias/modo 0700 | Incluir pastas vazias (o .NET inclui); chmod só no Linux |
| BOM inserido em script `.ps1` por edição | `utf-8-sig` na gravação | Conferir com `xxd`; o BOM no meio da concatenação quebra o parse |
| Gate com `tail` deixou commit passar com teste vermelho | Pipe mascara o código de saída | Redirecionar para arquivo e testar `$?` |

## Lições gerais
- Um teste que **refaz** a lógica do código em vez de executá-la esconde defeitos. Prefira executar o artefato real.
- Prove a sensibilidade dos testes com **mutantes** (reverter a correção e ver falhar).
- No PowerShell 5.1: TLS 1.2, `$ProgressPreference`, `ZipFile.ExtractToDirectory`, argumentos com aspas frágeis (usar helpers Python), `[Uri]` de caminho Linux dá `$null`.
- Não afirmar o que não foi medido (ex.: comportamento do `Start-Process -Wait` no 5.1).
