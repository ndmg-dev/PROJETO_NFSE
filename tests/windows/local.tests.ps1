# Testes das funções do sistema local (comum_nfse.ps1 e a biblioteca), em PowerShell 7
# num container Linux: `make test-windows`.
#
# LIMITE, EXPLÍCITO: provam a lógica pura, a montagem de argumentos e ambiente, o
# comportamento dos processos externos (com programas de Linux no lugar dos do
# Windows) e as cópias de arquivo. NÃO provam o Windows PowerShell 5.1 nem o
# postgres.exe, o python.exe embutido, o icacls, a MessageBox ou o WScript.Shell.
$ErrorActionPreference = 'Stop'
$raiz = (Resolve-Path "$PSScriptRoot/../..").Path
$falhas = 0
function Conferir([string]$Nome, [bool]$Ok) {
    if ($Ok) { Write-Host "  ✓ $Nome" } else { Write-Host "  ✗ $Nome"; $script:falhas++ }
}
function Lanca([scriptblock]$Bloco) { try { & $Bloco | Out-Null; return $false } catch { return $true } }
function Mensagem-De([scriptblock]$Bloco) { try { & $Bloco | Out-Null; return '' } catch { return $_.Exception.Message } }

. "$raiz/app/instalador/lib_windows.ps1"
. "$raiz/app/instalador/windows/comum_nfse.ps1"

Write-Host "`no .bat do instalador local: o que a linha real executa"
$batLocal = Join-Path $raiz '.tmp-windows/Instalar-NFSe.bat'
Conferir 'Instalar-NFSe.bat foi gerado (rode via make test-windows)' (Test-Path $batLocal)
$textoLocal = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($batLocal))
$cmdLocal = ($textoLocal -split "`r`n") | Where-Object { $_ -like 'powershell *' } | Select-Object -First 1
$comando = $cmdLocal.Substring($cmdLocal.IndexOf('-Command "') + 10).TrimEnd('"').Replace('Invoke-Expression', 'Write-Output')
$env:NFSE_INSTALADOR = $batLocal
$extraidoLocal = (& pwsh -NoProfile -Command $comando) -join "`n"
$erros = $null; $tokens = $null
[void][System.Management.Automation.Language.Parser]::ParseInput($extraidoLocal, [ref]$tokens, [ref]$erros)
Conferir 'o script executado não tem erro de sintaxe' ($erros.Count -eq 0)
Conferir 'o pacote em base64 NÃO vai junto para o Invoke-Expression' ($extraidoLocal -notmatch '(?m)^[A-Za-z0-9+/=]{70,}$' -and $extraidoLocal -match 'function Principal')
Remove-Item Env:NFSE_INSTALADOR

Write-Host "`ninstalação nova: nada instalado ainda"
$vazio = Caminhos-Nfse (Join-Path ([IO.Path]::GetTempPath()) ('nfse-vazio-' + [guid]::NewGuid()))
Conferir 'Postgres-Rodando é falso, sem exceção, quando o pg_ctl.exe não existe' ((Postgres-Rodando $vazio) -eq $false)
Conferir 'Parar-Postgres não faz nada e não falha numa instalação nova' (-not (Lanca { Parar-Postgres $vazio }))
Conferir 'Parar-Api não falha numa instalação nova' (-not (Lanca { Parar-Api $vazio }))

$tmp = Join-Path ([IO.Path]::GetTempPath()) ('nfse-loc-' + [guid]::NewGuid())
New-Item -ItemType Directory $tmp | Out-Null
function Novo-Exe([string]$Caminho, [string]$Corpo) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Caminho) | Out-Null
    [IO.File]::WriteAllText($Caminho, "#!/bin/sh`n$Corpo`n")   # LF: um shebang com \r não executa
    & chmod +x $Caminho
}

Write-Host "`nsintaxe dos scripts do instalador local"
$erros = $null; $tokens = $null
foreach ($f in Get-ChildItem "$raiz/app/instalador" -Recurse -Filter '*.ps1') {
    [void][System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$erros)
    Conferir "$($f.Name) sem erro de sintaxe" ($erros.Count -eq 0)
    foreach ($e in $erros) { Write-Host "      $($e.Message) (linha $($e.Extent.StartLineNumber))" }
}

Write-Host "`naspas para argumentos de programas externos"
Conferir 'sem espaço: como está' ((Aspas 'abc') -eq 'abc')
Conferir 'com espaço (usuário "Ana Maria"): entre aspas' ((Aspas 'C:\Users\Ana Maria\x') -eq '"C:\Users\Ana Maria\x"')
Conferir 'com aspas dentro: escapadas' ((Aspas 'a"b') -eq '"a\"b"')

Write-Host "`nprocessos externos: Executar-Programa"
$r = Executar-Programa '/bin/sh' @('-c', 'printf "%s|%s|" "$1" "$2"', '_', 'a b', 'c') -Capturar
Conferir 'argumento com espaço chega inteiro' ($r.Saida -eq 'a b|c|')
Conferir 'código de saída zero' ($r.Codigo -eq 0)
Conferir 'código de saída diferente de zero é devolvido' ((Executar-Programa '/bin/sh' @('-c', 'exit 7')).Codigo -eq 7)
Conferir 'a saída de erro também é capturada' ((Executar-Programa '/bin/sh' @('-c', 'echo falhou >&2') -Capturar).Saida.Trim() -eq 'falhou')
Conferir 'variável de ambiente chega ao programa' ((Executar-Programa '/bin/sh' @('-c', 'printf %s "$NFSE_TESTE"') -Capturar -Ambiente @{ NFSE_TESTE = 'valor' }).Saida -eq 'valor')
Conferir 'a variável NÃO vaza para o PowerShell que chamou' ($null -eq $env:NFSE_TESTE)
$pasta = Join-Path $tmp 'pasta com espaço'; New-Item -ItemType Directory $pasta | Out-Null
Conferir 'pasta de trabalho é respeitada' ((Executar-Programa '/bin/sh' @('-c', 'pwd') -Capturar -Pasta $pasta).Saida.Trim() -eq $pasta)
Novo-Exe "$pasta/meu programa.sh" 'printf ok'
Conferir 'executável em caminho com espaço' ((Executar-Programa "$pasta/meu programa.sh" @() -Capturar).Saida -eq 'ok')
Conferir 'programa inexistente → erro' (Lanca { Executar-Programa '/nao/existe/xyz' @() })
$t0 = Get-Date
$demora = Mensagem-De { Executar-Programa '/bin/sleep' @('30') -TimeoutMs 800 }
Conferir 'estouro de tempo levanta erro claro' ($demora -match 'demorou demais')
Conferir 'e não espera os 30 s' (((Get-Date) - $t0).TotalSeconds -lt 10)

Write-Host "`no problema do pg_ctl: programa que deixa um filho rodando de fundo e termina"
$t0 = Get-Date
$r = Executar-Programa '/bin/sh' @('-c', 'sleep 20 & echo iniciado')
Conferir 'sem -Capturar, espera SÓ o programa lançado (não o filho)' (((Get-Date) - $t0).TotalSeconds -lt 8 -and $r.Codigo -eq 0)

Write-Host "`ncaminhos com espaço no nome do usuário"
$base = Join-Path $tmp 'Users Ana Maria/NFSe'
$C = Caminhos-Nfse $base
Conferir 'tudo fica dentro da base' (($C.Values | Where-Object { $_ -is [string] -and -not $_.StartsWith($base) }).Count -eq 0)
Conferir 'dados do banco em dados/pg' ($C.Dados.EndsWith((Join-Path 'dados' 'pg')))
Conferir 'python.exe dentro de python' ($C.PythonExe -eq (Join-Path $C.Python 'python.exe'))
Conferir 'pg_ctl fica em pgsql/bin' ($C.PgBin -eq (Join-Path (Join-Path $base 'pgsql') 'bin'))

Write-Host "`nsegredos"
$arqSeg = Join-Path $tmp 'segredos.json'
$s1 = Garantir-Segredos $arqSeg
Conferir 'cria os três segredos' ($s1.postgres_senha -cmatch '^[0-9a-f]{48}$' -and $s1.app_senha -cmatch '^[0-9a-f]{48}$' -and [Convert]::FromBase64String($s1.jwt_secret).Length -eq 32)
Conferir 'as duas senhas de banco são diferentes' ($s1.postgres_senha -ne $s1.app_senha)
$b = [IO.File]::ReadAllBytes($arqSeg)
Conferir 'o arquivo não tem BOM' (-not ($b[0] -eq 0xEF -and $b[1] -eq 0xBB))
$s2 = Garantir-Segredos $arqSeg
Conferir 'segunda vez devolve os MESMOS (trocar deixaria o banco inacessível)' ($s2.postgres_senha -eq $s1.postgres_senha -and $s2.jwt_secret -eq $s1.jwt_secret)
$ruim = Join-Path $tmp 'incompleto.json'; [IO.File]::WriteAllText($ruim, '{"postgres_senha":"x"}')
Conferir 'arquivo incompleto NÃO é recriado: é erro' ((Mensagem-De { Garantir-Segredos $ruim }) -match 'incompleto')
Conferir 'e continua intacto' ((Get-Content -Raw $ruim) -match '"postgres_senha":"x"')

Write-Host "`nportas"
$l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 47210); $l.Start()
Conferir 'pula uma porta ocupada' ((Porta-Livre 47210) -eq 47211)
$l.Stop()
Conferir 'usa a preferida quando livre' ((Porta-Livre 47210) -eq 47210)
Conferir 'sem porta livre na faixa → erro' (Lanca { Porta-Livre 47220 -1 })
$arqCfg = Join-Path $tmp 'config.json'
$c1 = Garantir-Config $arqCfg
Conferir 'escolhe as duas portas' ($c1.porta_api -ge 8000 -and $c1.porta_pg -ge 54329)
Conferir 'a segunda chamada reaproveita (não reescolhe)' ((Garantir-Config $arqCfg).porta_api -eq $c1.porta_api)

Write-Host "`nrequisitos da máquina"
Conferir 'Windows 10, 64 bits, espaço de sobra → nenhum problema' ((Problemas-De-Requisitos $tmp ([version]'10.0.19045') $true 50000).Count -eq 0)
Conferir 'Windows 7 é recusado (sem o UCRT o banco não abre)' ((Problemas-De-Requisitos $tmp ([version]'6.1.7601') $true 50000) -join ' ' -match 'Windows 10')
Conferir '32 bits é recusado' ((Problemas-De-Requisitos $tmp ([version]'10.0') $false 50000) -join ' ' -match '64 bits')
Conferir 'pouco espaço é recusado, dizendo quanto há' ((Problemas-De-Requisitos $tmp ([version]'10.0') $true 500) -join ' ' -match '500 MB')
Conferir 'vários problemas aparecem juntos' ((Problemas-De-Requisitos $tmp ([version]'6.1') $false 100).Count -eq 3)

Write-Host "`nruntime do Visual C++ (o postgres.exe não abre sem ele)"
$sis = Join-Path $tmp 'sistema'; $jdkBin = Join-Path $tmp 'jdk/bin'; $pgBin = Join-Path $tmp 'pg/bin'; $pyDir = Join-Path $tmp 'py'
New-Item -ItemType Directory $sis, $jdkBin, $pgBin, $pyDir | Out-Null
Conferir 'sistema sem nenhuma DLL: faltam as 3' ((Faltam-DllsDoVc $sis).Count -eq 3)
'x' | Set-Content "$sis/msvcp140.dll"; 'x' | Set-Content "$sis/vcruntime140.dll"
Conferir 'faltando só a vcruntime140_1 (redistributable antigo): detecta' ((Faltam-DllsDoVc $sis) -eq @('vcruntime140_1.dll'))
'x' | Set-Content "$sis/vcruntime140_1.dll"
Conferir 'sistema completo: nada falta' ((Faltam-DllsDoVc $sis).Count -eq 0)
foreach ($d in $script:DLLS_VC) { "jdk-$d" | Set-Content "$jdkBin/$d" }
$copiadas = Copiar-DllsDoVc $jdkBin @($pgBin, $pyDir)
Conferir 'copia as 3 para cada destino (6 no total)' ($copiadas.Count -eq 6)
Conferir 'ficam na pasta do programa' ((Test-Path "$pgBin/vcruntime140.dll") -and (Test-Path "$pyDir/msvcp140.dll"))
'do-python' | Set-Content "$pyDir/vcruntime140.dll" -NoNewline
[void](Copiar-DllsDoVc $jdkBin @($pyDir))
Conferir 'NÃO sobrescreve o que já existe (a DLL própria do Python fica)' ((Get-Content -Raw "$pyDir/vcruntime140.dll") -eq 'do-python')
Remove-Item "$jdkBin/msvcp140.dll"
Conferir 'origem sem uma das DLLs → erro que diz qual' ((Mensagem-De { Copiar-DllsDoVc $jdkBin @((Join-Path $tmp 'outro')) }) -match 'msvcp140')

Write-Host "`nPython embutido"
$pth = Join-Path $tmp 'python312._pth'
Escrever-Pth $pth 'python312.zip'
$linhas = [IO.File]::ReadAllLines($pth)
Conferir 'lista a biblioteca, o site-packages e a pasta do código' ($linhas -contains 'python312.zip' -and $linhas -contains 'Lib\site-packages' -and $linhas -contains '..\codigo')
Conferir '`import site` DESCOMENTADO (sem ele o site-packages não é lido)' ($linhas -contains 'import site' -and -not ($linhas | Where-Object { $_ -match '^#\s*import site' }))
$pb = [IO.File]::ReadAllBytes($pth)
Conferir 'sem BOM' (-not ($pb[0] -eq 0xEF))

Write-Host "`nPostgreSQL"
$a = Argumentos-Initdb '/x/dados' '/x/pw'
Conferir 'initdb com autenticação por senha, UTF8 e usuário nfse' (($a -join ' ') -match '--auth=scram-sha-256' -and ($a -join ' ') -match '-E UTF8' -and ($a -join ' ') -match '-U nfse')
Conferir 'a senha vai por arquivo (--pwfile), nunca na linha de comando' ($a -contains '--pwfile=/x/pw')
$conf = Join-Path $tmp 'postgresql.conf'
[IO.File]::WriteAllText($conf, "# original`nmax_connections = 100`nport = 5432`n")
Configurar-Postgres $conf 54329
$t1 = [IO.File]::ReadAllText($conf)
Conferir 'escuta só em 127.0.0.1' ($t1 -match "listen_addresses = '127\.0\.0\.1'")
Conferir 'usa a porta escolhida' ($t1 -match 'port = 54329')
Conferir 'preserva o conteúdo original' ($t1 -match '# original' -and $t1 -match 'max_connections = 100')
Configurar-Postgres $conf 54330
$t2 = [IO.File]::ReadAllText($conf)
Conferir 'reescrever troca a porta sem duplicar o bloco' (([regex]::Matches($t2, 'NFS-e \(gerado')).Count -eq 1 -and $t2 -match 'port = 54330' -and $t2 -notmatch 'port = 54329')

Write-Host "`nambiente da aplicação"
$seg = [pscustomobject]@{ postgres_senha = ('a' * 48); app_senha = ('b' * 48); jwt_secret = 'JWT' }
$cfg = [pscustomobject]@{ porta_api = 8000; porta_pg = 54329 }
$api = Ambiente-Da-Api $seg $cfg
Conferir 'a API conecta como o papel SEM privilégio (nfse_app)' ($api.DATABASE_URL -match '^postgresql\+psycopg://nfse_app:b{48}@127\.0\.0\.1:54329/nfse$')
Conferir 'a API recebe o JWT_SECRET' ($api.JWT_SECRET -eq 'JWT')
Conferir 'sem REDIS_URL (a API local não tem fila)' (-not $api.ContainsKey('REDIS_URL'))
$adm = Ambiente-Admin $seg $cfg
Conferir 'as migrations usam o dono (nfse) e recebem a senha do papel da app' ($adm.DATABASE_URL -match '^postgresql\+psycopg://nfse:a{48}@' -and $adm.APP_DB_PASSWORD -eq ('b' * 48))
Conferir 'o dono do banco NÃO é o usuário da API (superusuário ignora a RLS)' ($api.DATABASE_URL -notmatch '//nfse:')

Write-Host "`ncópia de segurança e restauração"
$B = Caminhos-Nfse (Join-Path $tmp 'inst')
foreach ($d in $B.Dados, $B.Config, $B.PgBin, $B.Logs) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
Novo-Exe (Join-Path $B.PgBin 'pg_ctl.exe') 'case "$1" in status) exit 3;; esac; exit 0'   # "não está rodando"
'dado-1' | Set-Content (Join-Path $B.Dados 'PG_VERSION') -NoNewline
'{"postgres_senha":"s1"}' | Set-Content (Join-Path $B.Config 'segredos.json') -NoNewline
$dest = Join-Path $tmp 'copias'
$copia = Fazer-Copia $B $dest
Conferir 'gera um .zip com carimbo de data' ($copia.Arquivo -match 'nfse-\d{8}-\d{6}\.zip$' -and (Test-Path $copia.Arquivo))
$conteudo = [IO.Compression.ZipFile]::OpenRead($copia.Arquivo).Entries.FullName
Conferir 'leva os dados do banco E a pasta config (com as senhas)' (($conteudo -match 'dados/PG_VERSION|dados\\PG_VERSION') -and ($conteudo -match 'config/segredos.json|config\\segredos.json'))
'dado-2-depois' | Set-Content (Join-Path $B.Dados 'PG_VERSION') -NoNewline
'{"postgres_senha":"s2"}' | Set-Content (Join-Path $B.Config 'segredos.json') -NoNewline
Restaurar-Copia $B $copia.Arquivo
Conferir 'restaurar devolve os dados de antes' ((Get-Content -Raw (Join-Path $B.Dados 'PG_VERSION')) -eq 'dado-1')
Conferir 'e as senhas de antes (sem elas o banco ficaria inacessível)' ((Get-Content -Raw (Join-Path $B.Config 'segredos.json')) -match 's1')
$guardados = Get-ChildItem (Split-Path -Parent $B.Dados) -Directory | Where-Object { $_.Name -like 'pg.antes-*' }
Conferir 'o que existia antes é GUARDADO, não apagado' (($guardados.Count -eq 1) -and ((Get-Content -Raw (Join-Path $guardados[0].FullName 'PG_VERSION')) -eq 'dado-2-depois'))
$falso = Join-Path $tmp 'qualquer.zip'; Compress-Archive -Path $conf -DestinationPath $falso
Conferir 'um zip que não é cópia do NFS-e é recusado' ((Mensagem-De { Restaurar-Copia $B $falso }) -match 'não parece ser uma cópia')
Conferir 'e os dados atuais continuam intactos após a recusa' ((Get-Content -Raw (Join-Path $B.Dados 'PG_VERSION')) -eq 'dado-1')

Write-Host "`ndownload com verificação de integridade (Baixar-Verificado)"
$origem = Join-Path $tmp 'origem.bin'; [IO.File]::WriteAllBytes($origem, [Text.Encoding]::ASCII.GetBytes('conteudo verificado'))
$hash = (Get-FileHash $origem -Algorithm SHA256).Hash.ToLower()
# [Uri]"/caminho" dá $null em silêncio no Linux (o acesso à propriedade engole a exceção): monta à mão.
$url = "file://$origem"
$dst = Join-Path $tmp 'baixados/arquivo.bin'
Baixar-Verificado $url $hash $dst 3 0
Conferir 'arquivo íntegro chega ao destino' ((Test-Path $dst) -and ((Get-FileHash $dst -Algorithm SHA256).Hash.ToLower() -eq $hash))
Conferir 'não sobra arquivo parcial' (-not (Test-Path "$dst.parcial"))
[IO.File]::WriteAllBytes($origem, [Text.Encoding]::ASCII.GetBytes('adulterado'))
Baixar-Verificado $url $hash $dst 3 0
Conferir 'já baixado e íntegro: não baixa de novo (mesmo com a origem alterada)' ((Get-Content -Raw $dst) -eq 'conteudo verificado')
$dst2 = Join-Path $tmp 'baixados/outro.bin'
Conferir 'hash que não confere → erro' ((Mensagem-De { Baixar-Verificado $url $hash $dst2 2 0 }) -match 'verificação de integridade falhou')
Conferir 'e o arquivo adulterado NÃO chega ao destino' (-not (Test-Path $dst2))
Conferir 'nem deixa .parcial' (-not (Test-Path "$dst2.parcial"))
Conferir 'SHA-256 malformado → erro antes de baixar' (Lanca { Baixar-Verificado $url 'curto' $dst2 })
Conferir 'http (sem TLS) é recusado' ((Mensagem-De { Baixar-Verificado 'http://exemplo.invalido/x' $hash $dst2 1 0 }) -match 'só https')
'lixo' | Set-Content $dst -NoNewline
[IO.File]::WriteAllBytes($origem, [Text.Encoding]::ASCII.GetBytes('conteudo verificado'))
Baixar-Verificado $url $hash $dst 3 0
Conferir 'arquivo já existente porém corrompido é substituído pelo íntegro' ((Get-Content -Raw $dst) -eq 'conteudo verificado')

Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
Write-Host ($(if ($falhas) { "`n$falhas FALHA(S)" } else { "`ntodos os testes passaram" }))
exit $(if ($falhas) { 1 } else { 0 })
