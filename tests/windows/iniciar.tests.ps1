# Testes do instalador do Windows (iniciar.ps1 / Iniciar.bat), rodados em
# PowerShell 7 num container Linux: `make test-windows`.
#
# LIMITE, EXPLÍCITO: isto pega erro de sintaxe e testa a lógica pura (geração de
# segredos, escrita do .env, leitura do estado). NÃO prova o comportamento no
# Windows PowerShell 5.1 nem o docker, o navegador e o icacls do Windows.
$ErrorActionPreference = 'Stop'
$raiz = Resolve-Path "$PSScriptRoot/../.."
$falhas = 0
function Conferir([string]$Nome, [bool]$Ok) {
    if ($Ok) { Write-Host "  ✓ $Nome" } else { Write-Host "  ✗ $Nome"; $script:falhas++ }
}

Write-Host "`nsintaxe e formato dos arquivos"
$erros = $null; $tokens = $null
[void][System.Management.Automation.Language.Parser]::ParseFile("$raiz/iniciar.ps1", [ref]$tokens, [ref]$erros)
Conferir 'iniciar.ps1 sem erro de sintaxe' ($erros.Count -eq 0)
foreach ($e in $erros) { Write-Host "      $($e.Message) (linha $($e.Extent.StartLineNumber))" }

$ps1 = [IO.File]::ReadAllBytes("$raiz/iniciar.ps1")
Conferir 'iniciar.ps1 tem BOM UTF-8 (senão o PowerShell 5.1 estraga os acentos)' ($ps1[0] -eq 0xEF -and $ps1[1] -eq 0xBB -and $ps1[2] -eq 0xBF)
Conferir 'iniciar.ps1 usa CRLF' (([Text.Encoding]::UTF8.GetString($ps1)) -match "`r`n")

$bat = [IO.File]::ReadAllBytes("$raiz/Iniciar.bat")
Conferir 'Iniciar.bat só tem ASCII' (($bat | Where-Object { $_ -gt 127 }).Count -eq 0)
$batTexto = [Text.Encoding]::ASCII.GetString($bat)
Conferir 'Iniciar.bat usa CRLF (o cmd falha com LF)' ($batTexto -match "`r`n" -and $batTexto -notmatch "[^`r]`n")
Conferir 'Iniciar.bat chama o iniciar.ps1' ($batTexto -match 'iniciar\.ps1')

. "$raiz/iniciar.ps1"   # carrega as funções sem executar a instalação

Write-Host "`nsegredos"
$a = Novo-Hex 24; $b = Novo-Hex 24
Conferir 'Novo-Hex 24 tem 48 caracteres' ($a.Length -eq 48)
Conferir 'Novo-Hex só tem [0-9a-f]' ($a -cmatch '^[0-9a-f]+$')
Conferir 'dois Novo-Hex diferem' ($a -ne $b)
$j = Novo-Base64 32
Conferir 'Novo-Base64 32 decodifica em 32 bytes' ([Convert]::FromBase64String($j).Length -eq 32)

Write-Host "`n.env"
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("nfse-env-" + [guid]::NewGuid())
New-Item -ItemType Directory $tmp | Out-Null
$env1 = Join-Path $tmp '.env'
$ger = @{ POSTGRES_PASSWORD = { Novo-Hex 24 }; APP_DB_PASSWORD = { Novo-Hex 24 }; JWT_SECRET = { Novo-Base64 32 } }

$criadas = Garantir-Env $env1 $ger
Conferir 'primeira vez cria as 3 chaves' ($criadas.Count -eq 3)
$b0 = [IO.File]::ReadAllBytes($env1)
Conferir '.env NÃO tem BOM (um BOM corrompe a primeira chave no Compose)' (-not ($b0[0] -eq 0xEF -and $b0[1] -eq 0xBB))
$lidas = Ler-Env $env1
Conferir 'as 3 chaves têm valor' (($lidas.Keys.Count -eq 3) -and (($lidas.Values | Where-Object { $_.Length -gt 0 }).Count -eq 3))
Conferir 'a senha do banco tem 48 caracteres hex' ($lidas['POSTGRES_PASSWORD'] -cmatch '^[0-9a-f]{48}$')
Conferir 'o JWT_SECRET é base64 de 32 bytes' ([Convert]::FromBase64String($lidas['JWT_SECRET']).Length -eq 32)

$hashAntes = (Get-FileHash $env1).Hash
$criadas2 = Garantir-Env $env1 $ger
Conferir 'segunda vez não cria nada' ($criadas2.Count -eq 0)
Conferir 'segunda vez não altera o arquivo (senha existente nunca é trocada)' ((Get-FileHash $env1).Hash -eq $hashAntes)

$env2 = Join-Path $tmp 'parcial.env'
[IO.File]::WriteAllText($env2, "POSTGRES_PASSWORD=minha-senha-antiga`n", (New-Object Text.UTF8Encoding($false)))
$criadas3 = Garantir-Env $env2 $ger
$l3 = Ler-Env $env2
Conferir 'preserva a senha que já existia' ($l3['POSTGRES_PASSWORD'] -eq 'minha-senha-antiga')
Conferir 'cria só as que faltavam' ($criadas3.Count -eq 2 -and $criadas3 -notcontains 'POSTGRES_PASSWORD')

$env3 = Join-Path $tmp 'vazia.env'
[IO.File]::WriteAllText($env3, "JWT_SECRET=`n", (New-Object Text.UTF8Encoding($false)))
[void](Garantir-Env $env3 $ger)
Conferir 'chave com valor vazio conta como ausente e é preenchida' ((Ler-Env $env3)['JWT_SECRET'].Length -gt 0)
Conferir 'Ler-Env de arquivo inexistente devolve vazio, sem erro' ((Ler-Env (Join-Path $tmp 'nao-existe')).Count -eq 0)
Remove-Item -Recurse -Force $tmp

Write-Host "`nleitura do estado do sistema"
Conferir 'configurado: true'          (Configurado-DoJson '{"configurado":true,"verificacoes":[]}')
Conferir 'configurado: true com espaço' (Configurado-DoJson '{"configurado": true}')
Conferir 'configurado: false'         (-not (Configurado-DoJson '{"configurado":false,"verificacoes":[]}'))
Conferir 'configurado: null (banco subindo)' (-not (Configurado-DoJson '{"configurado":null,"verificacoes":[]}'))
Conferir 'resposta vazia não conta como configurado' (-not (Configurado-DoJson ''))

Write-Host ($(if ($falhas) { "`n$falhas FALHA(S)" } else { "`ntodos os testes passaram" }))
exit $(if ($falhas) { 1 } else { 0 })
