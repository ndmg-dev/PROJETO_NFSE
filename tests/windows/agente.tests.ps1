# Testes do instalador do agente (app/instalador), em PowerShell 7 num container
# Linux: `make test-windows`.
#
# LIMITE, EXPLÍCITO: provam a extração do arquivo gerado, a lógica pura e a
# validação do que a Adoptium devolve, com um zip do JDK falso. NÃO provam o
# Windows PowerShell 5.1 nem o javac, o atalho (COM) e o SunMSCAPI do Windows.
# A estrutura do zip real do JDK e o módulo jdk.crypto.mscapi foram conferidos à
# parte, baixando o arquivo de verdade (ver o commit que adicionou este teste).
$ErrorActionPreference = 'Stop'
$raiz = (Resolve-Path "$PSScriptRoot/../..").Path
# NFSE_BAT / NFSE_URL_ESPERADA permitem testar um arquivo baixado de um servidor de verdade.
$bat = if ($env:NFSE_BAT) { $env:NFSE_BAT } else { Join-Path $raiz '.tmp-windows/Instalar-Agente-NFSe.bat' }
$urlEsperada = if ($env:NFSE_URL_ESPERADA) { $env:NFSE_URL_ESPERADA } else { 'http://servidor-de-teste:8000' }
$falhas = 0
function Conferir([string]$Nome, [bool]$Ok) {
    if ($Ok) { Write-Host "  ✓ $Nome" } else { Write-Host "  ✗ $Nome"; $script:falhas++ }
}
function Lanca([scriptblock]$Bloco) { try { & $Bloco | Out-Null; return $false } catch { return $true } }
function Novo-Exe([string]$Caminho, [string]$Saida, [int]$Codigo = 0) {
    # LF explícito (`n): este arquivo é CRLF e um shebang com \r não executa.
    [IO.File]::WriteAllText($Caminho, "#!/bin/sh`necho '$Saida'`nexit $Codigo`n")
    & chmod +x $Caminho
}
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('nfse-ag-' + [guid]::NewGuid())
New-Item -ItemType Directory $tmp | Out-Null

Write-Host "`no arquivo gerado pelo servidor"
Conferir 'Instalar-Agente-NFSe.bat foi gerado (rode via make test-windows)' (Test-Path $bat)
$bytes = [IO.File]::ReadAllBytes($bat)
$texto = [Text.Encoding]::UTF8.GetString($bytes)
Conferir 'sem BOM (o cmd trata o BOM como lixo na primeira linha)' (-not ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB))
Conferir 'CRLF em todas as linhas, sem LF solto' (($texto -replace "`r`n", '') -notmatch "`n")
$linhas = $texto -split "`r`n"
Conferir 'começa com @echo off' ($linhas[0] -eq '@echo off')
$iPs1 = [array]::IndexOf($linhas, '#PS1#')
$iPay = [array]::IndexOf($linhas, '#PAYLOAD#')
Conferir '#PS1# aparece como linha inteira, uma vez' ($iPs1 -gt 0 -and ($linhas | Where-Object { $_ -eq '#PS1#' }).Count -eq 1)
Conferir '#PAYLOAD# aparece como linha inteira, uma vez' ($iPay -gt $iPs1 -and ($linhas | Where-Object { $_ -eq '#PAYLOAD#' }).Count -eq 1)
Conferir 'o texto literal #PS1# não aparece na linha de comando (montado por concatenação)' (($texto.Split('#PS1#').Count - 1) -eq 1)
Conferir 'o cabeçalho (até #PS1#) é só ASCII: o cmd o interpreta' (($bytes[0..([Text.Encoding]::UTF8.GetByteCount(($linhas[0..$iPs1] -join "`r`n")))] | Where-Object { $_ -gt 127 }).Count -eq 0)
Conferir 'termina o cmd com exit /b antes do script' ($linhas[0..$iPs1] -contains 'exit /b')
Conferir 'o pacote tem só caracteres base64' (($linhas[($iPay + 1)..($linhas.Count - 1)] | Where-Object { $_ -ne '' -and $_ -notmatch '^[A-Za-z0-9+/=]+$' }).Count -eq 0)
Conferir 'linhas do pacote com até 76 caracteres' (($linhas[($iPay + 1)..($linhas.Count - 1)] | Where-Object { $_.Length -gt 76 }).Count -eq 0)

Write-Host "`na linha de comando do .bat extrai o script certo"
$cmd = $linhas | Where-Object { $_ -like 'powershell *' } | Select-Object -First 1
Conferir 'existe a linha que chama o PowerShell' ([bool]$cmd)
# reproduz exatamente o que a linha do .bat faz: tudo depois do marcador #PS1#
$m = '#' + 'PS1#'
$extraido = $texto.Substring($texto.LastIndexOf($m) + $m.Length)
$extraido = $extraido.Substring(0, $extraido.LastIndexOf('#' + 'PAYLOAD#'))
$erros = $null; $tokens = $null
[void][System.Management.Automation.Language.Parser]::ParseInput($extraido, [ref]$tokens, [ref]$erros)
Conferir 'o script extraído do .bat não tem erro de sintaxe' ($erros.Count -eq 0)
foreach ($e in $erros) { Write-Host "      $($e.Message) (linha $($e.Extent.StartLineNumber))" }
$fonte = (([IO.File]::ReadAllText("$raiz/app/instalador/lib_windows.ps1", [Text.Encoding]::UTF8) + "`n" + [IO.File]::ReadAllText("$raiz/app/instalador/instalar_agente.ps1", [Text.Encoding]::UTF8)) -replace "`r`n", "`n").TrimStart([char]0xFEFF)
Conferir 'o script extraído é a biblioteca + o script do repositório' ((($extraido -replace "`r`n", "`n").Trim()) -eq $fonte.Trim())
Conferir 'o script tem os acentos íntegros' ($extraido -match 'Não foi possível' -and $extraido -match 'Área de Trabalho')

. "$raiz/app/instalador/lib_windows.ps1"        # biblioteca compartilhada
. "$raiz/app/instalador/instalar_agente.ps1"     # funções do agente, sem executar a instalação

Write-Host "`no pacote embutido"
$pasta = Join-Path $tmp 'app'
Expandir-Pacote (Extrair-Payload $bat) $pasta
$nomes = (Get-ChildItem $pasta -File | ForEach-Object Name) | Sort-Object
Conferir 'contém exatamente os 3 fontes Java, servidor.txt e LEIAME.txt' (($nomes -join ',') -eq 'LEIAME.txt,Nucleo.java,ProvarHandshakeMTLS.java,ProvarHandshakeMTLSGui.java,servidor.txt')
Conferir 'servidor.txt traz o endereço do servidor' ((Get-Content "$pasta/servidor.txt" -Raw).Trim() -eq $urlEsperada)
foreach ($java in 'Nucleo.java', 'ProvarHandshakeMTLS.java', 'ProvarHandshakeMTLSGui.java') {
    $orig = (Get-FileHash "$raiz/agente/spike/$java").Hash
    Conferir "$java é idêntico ao do repositório" ((Get-FileHash "$pasta/$java").Hash -eq $orig)
}
Conferir 'nenhum .env, .pfx ou chave no pacote' (($nomes | Where-Object { $_ -match '\.(env|pfx|p12|pem|key)$' }).Count -eq 0)
Conferir 'Extrair-Payload num arquivo sem pacote dá erro claro' (Lanca { Extrair-Payload "$raiz/iniciar.sh" })

Write-Host "`nversão do Java"
$bin = Join-Path $tmp 'bin-teste'; New-Item -ItemType Directory $bin | Out-Null
Novo-Exe "$bin/javac21.exe" 'javac 21.0.12'
Novo-Exe "$bin/javac17.exe" 'javac 17'
Novo-Exe "$bin/javac8.exe" 'javac 1.8.0_402'
Novo-Exe "$bin/javac11.exe" 'javac 11.0.2'
Novo-Exe "$bin/lixo.exe" 'nada a ver'
Conferir 'javac 21.0.12 → 21' ((Versao-Do-Javac "$bin/javac21.exe") -eq 21)
Conferir 'javac 17 → 17' ((Versao-Do-Javac "$bin/javac17.exe") -eq 17)
Conferir 'javac 1.8.0_402 → 8 (formato antigo)' ((Versao-Do-Javac "$bin/javac8.exe") -eq 8)
Conferir 'saída ilegível → 0' ((Versao-Do-Javac "$bin/lixo.exe") -eq 0)
Conferir 'programa inexistente → 0, sem exceção' ((Versao-Do-Javac "$bin/nao-existe.exe") -eq 0)

Write-Host "`nescolha do Java"
$jdkPortatil = Join-Path $tmp 'portatil'; New-Item -ItemType Directory "$jdkPortatil/bin" -Force | Out-Null
Novo-Exe "$jdkPortatil/bin/java.exe" 'java'; Novo-Exe "$jdkPortatil/bin/javac.exe" 'javac 21.0.12'
$pathOriginal = $env:PATH
function Com-Path([string]$Versao, [scriptblock]$Bloco) {
    $d = Join-Path $tmp ('path-' + [guid]::NewGuid()); New-Item -ItemType Directory $d | Out-Null
    if ($Versao) { Novo-Exe "$d/java.exe" 'java'; Novo-Exe "$d/javac.exe" "javac $Versao" }
    $env:PATH = "$d$([IO.Path]::PathSeparator)$pathOriginal"
    try { & $Bloco $d } finally { $env:PATH = $pathOriginal }
}
$semJdk = Join-Path $tmp 'nao-existe'
Com-Path '21.0.1' { param($d); $r = Achar-Java $semJdk; Conferir 'usa o Java 21 que já está no PATH' ($r.Javac -eq "$d/javac.exe") }
Com-Path '17' { param($d); $r = Achar-Java $semJdk; Conferir 'aceita Java 17 (o mínimo)' ($null -ne $r) }
Com-Path '11.0.2' { param($d); Conferir 'recusa Java 11 do PATH (o código usa records)' ($null -eq (Achar-Java $semJdk)) }
Com-Path '1.8.0_402' { param($d); Conferir 'recusa Java 8 do PATH' ($null -eq (Achar-Java $semJdk)) }
Com-Path '11.0.2' { param($d); $r = Achar-Java $jdkPortatil; Conferir 'com Java velho no PATH, cai na cópia portátil' ($r.Javac -eq "$jdkPortatil/bin/javac.exe") }
Com-Path '' { param($d); $r = Achar-Java $jdkPortatil; Conferir 'sem Java no PATH, usa a cópia portátil' ($null -ne $r) }
Com-Path '' { param($d); Conferir 'sem Java em lugar nenhum → $null (aí o instalador baixa)' ($null -eq (Achar-Java $semJdk)) }
Com-Path '21.0.1' { param($d); Conferir 'javaw fica ao lado do java' ((Achar-Java $semJdk).Javaw -eq "$d/javaw.exe") }

Write-Host "`no que a Adoptium devolve (formato real, conferido em 24/09/2026)"
$real = Get-Content "$raiz/tests/windows/fixtures/adoptium_assets.json" -Raw | ConvertFrom-Json
$p = Escolher-Pacote $real
Conferir 'aceita a resposta real' ($null -ne $p)
Conferir 'o link é https e termina em .zip' ($p.link -match '^https://.*\.zip$')
Conferir 'o checksum tem 64 hexadecimais' ($p.checksum -match '^[0-9a-f]{64}$')
Conferir 'resposta vazia → erro' (Lanca { Escolher-Pacote @() })
Conferir 'sem checksum → erro' (Lanca { Escolher-Pacote ([pscustomobject]@{ binary = [pscustomobject]@{ package = [pscustomobject]@{ link = 'https://x/y.zip' } } }) })
Conferir 'link http (não seguro) → erro' (Lanca { Escolher-Pacote ([pscustomobject]@{ binary = [pscustomobject]@{ package = [pscustomobject]@{ link = 'http://x/y.zip'; checksum = ('a' * 64) } } }) })
Conferir 'checksum malformado → erro' (Lanca { Escolher-Pacote ([pscustomobject]@{ binary = [pscustomobject]@{ package = [pscustomobject]@{ link = 'https://x/y.zip'; checksum = 'curto' } } }) })

Write-Host "`nverificação de integridade do download"
$arq = Join-Path $tmp 'conteudo.bin'; [IO.File]::WriteAllBytes($arq, [Text.Encoding]::ASCII.GetBytes('conteudo de teste'))
$hash = (Get-FileHash $arq -Algorithm SHA256).Hash
Conferir 'checksum em minúsculas confere (Get-FileHash devolve maiúsculas)' (Confere-Checksum $arq $hash.ToLower())
Conferir 'checksum em maiúsculas confere' (Confere-Checksum $arq $hash.ToUpper())
Conferir 'arquivo alterado NÃO confere' (-not (Confere-Checksum $arq ('0' * 64)))

Write-Host "`nzip do Java"
function Novo-ZipJdk([string]$Zip, [string[]]$Pastas) {
    $r = Join-Path $tmp ('z-' + [guid]::NewGuid())
    foreach ($pasta in $Pastas) { New-Item -ItemType Directory "$r/$pasta/bin" -Force | Out-Null; 'x' | Set-Content "$r/$pasta/bin/java.exe"; 'x' | Set-Content "$r/$pasta/bin/javac.exe" }
    Compress-Archive -Path "$r/*" -DestinationPath $Zip -Force
}
$zip1 = Join-Path $tmp 'jdk1.zip'; Novo-ZipJdk $zip1 @('jdk-21.0.12.1+1')
$dest = Join-Path $tmp 'jdk-instalado'
Instalar-JdkDeZip $zip1 $dest
Conferir 'a pasta única do topo vira o destino (bin/java.exe está direto nele)' ((Test-Path "$dest/bin/java.exe") -and (Test-Path "$dest/bin/javac.exe"))
Conferir 'sobra nada de temporário em jdk-instalado/jdk-*' (-not (Test-Path "$dest/jdk-21.0.12.1+1"))
Instalar-JdkDeZip $zip1 $dest
Conferir 'instalar de novo por cima funciona' (Test-Path "$dest/bin/java.exe")
$zip2 = Join-Path $tmp 'jdk2.zip'; Novo-ZipJdk $zip2 @('uma', 'duas')
Conferir 'zip com duas pastas no topo → erro (formato inesperado)' (Lanca { Instalar-JdkDeZip $zip2 (Join-Path $tmp 'nao-vai-existir') })

Write-Host "`ncompilação"
$fontes = Join-Path $tmp 'fontes'; New-Item -ItemType Directory $fontes | Out-Null; 'class A {}' | Set-Content "$fontes/A.java"
Novo-Exe "$tmp/javac-ok.exe" 'compilou' 0
Novo-Exe "$tmp/javac-erro.exe" 'A.java:1: erro: simbolo nao encontrado' 1
Compilar "$tmp/javac-ok.exe" $fontes
Conferir 'javac com sucesso cria a pasta classes' (Test-Path "$fontes/classes")
$msg = ''; try { Compilar "$tmp/javac-erro.exe" $fontes } catch { $msg = $_.Exception.Message }
Conferir 'javac com erro levanta exceção que traz a mensagem do compilador' ($msg -match 'simbolo nao encontrado')
$vazio = Join-Path $tmp 'vazio'; New-Item -ItemType Directory $vazio | Out-Null
Conferir 'pasta sem .java → erro claro' (Lanca { Compilar "$tmp/javac-ok.exe" $vazio })

Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
Write-Host ($(if ($falhas) { "`n$falhas FALHA(S)" } else { "`ntodos os testes passaram" }))
exit $(if ($falhas) { 1 } else { 0 })
