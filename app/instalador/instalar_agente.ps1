# Instalador da ferramenta de teste de certificado (versão de validação do agente).
#
# NÃO é para executar direto: este texto é embutido no Instalar-Agente-NFSe.bat,
# que o servidor gera em /instalar. Compatível com o Windows PowerShell 5.1.
#
# O que faz, sem perguntar nada:
#   1. extrai os fontes (que vêm dentro do próprio .bat) para %LOCALAPPDATA%\nfse-agente;
#   2. acha um Java 17+ ou, se não houver, baixa uma cópia portátil da Adoptium e
#      confere o SHA-256 antes de usá-la;
#   3. compila, cria um atalho na Área de Trabalho e abre a janela do teste.
# Nada é instalado no sistema e não pede permissão de administrador.

$ErrorActionPreference = 'Stop'
# O Windows PowerShell 5.1 negocia TLS antigo por padrão e a Adoptium exige 1.2.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
# No 5.1 a barra de progresso torna o download dezenas de vezes mais lento.
$ProgressPreference = 'SilentlyContinue'

# ZipFile do .NET em vez de Expand-Archive: no Windows PowerShell 5.1 o Expand-Archive
# é muito lento em zips grandes, e o do JDK tem centenas de arquivos.
Add-Type -AssemblyName System.IO.Compression.FileSystem

$script:URL_JDK = 'https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse'
$script:JAVA_MINIMO = 17   # o código usa records (Java 16+) e java.net.http (Java 11+)

function Dizer([string]$Texto) { Write-Host $Texto }

function Extrair-Payload([string]$CaminhoDoInstalador) {
    $t = [IO.File]::ReadAllText($CaminhoDoInstalador, [Text.Encoding]::UTF8)
    $m = '#' + 'PAYLOAD#'
    $i = $t.LastIndexOf($m)
    if ($i -lt 0) { throw 'O instalador está incompleto (pacote não encontrado). Baixe-o de novo.' }
    $b64 = $t.Substring($i + $m.Length) -replace '\s', ''
    return [Convert]::FromBase64String($b64)
}

function Extrair-Zip([string]$Zip, [string]$Destino) {
    [IO.Compression.ZipFile]::ExtractToDirectory($Zip, $Destino)
}

function Expandir-Pacote([byte[]]$Zip, [string]$Destino) {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('nfse-agente-' + [guid]::NewGuid() + '.zip')
    try {
        [IO.File]::WriteAllBytes($tmp, $Zip)
        if (Test-Path -LiteralPath $Destino) { Remove-Item -LiteralPath $Destino -Recurse -Force }
        Extrair-Zip $tmp $Destino
    } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
}

# Versão principal do javac: 21 para "javac 21.0.1"; 8 para "javac 1.8.0_402"; 0 se não entender.
function Versao-Do-Javac([string]$Javac) {
    $antes = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'   # no 5.1, 'Stop' faz a saída de erro de um programa virar exceção
    try { $saida = (& $Javac -version 2>&1 | ForEach-Object { "$_" }) -join "`n" } catch { return 0 } finally { $ErrorActionPreference = $antes }
    if ($saida -match 'javac\s+(\d+)(?:\.(\d+))?') {
        $maior = [int]$Matches[1]
        if ($maior -eq 1 -and $Matches[2]) { $maior = [int]$Matches[2] }
        return $maior
    }
    return 0
}

# Precisa ser JDK (tem javac), não só JRE, e de versão suficiente. Devolve $null se não achar.
function Achar-Java([string]$PastaDoJdk) {
    $java = Get-Command 'java.exe' -ErrorAction SilentlyContinue
    $javac = Get-Command 'javac.exe' -ErrorAction SilentlyContinue
    if ($java -and $javac -and ((Versao-Do-Javac $javac.Source) -ge $script:JAVA_MINIMO)) {
        return @{ Java = $java.Source; Javac = $javac.Source; Javaw = (Join-Path (Split-Path $java.Source) 'javaw.exe') }
    }
    $j = Join-Path $PastaDoJdk 'bin\java.exe'
    $c = Join-Path $PastaDoJdk 'bin\javac.exe'
    if ((Test-Path -LiteralPath $j) -and (Test-Path -LiteralPath $c)) {
        return @{ Java = $j; Javac = $c; Javaw = (Join-Path $PastaDoJdk 'bin\javaw.exe') }
    }
    return $null
}

# Valida o que a API da Adoptium devolveu ANTES de baixar qualquer coisa.
function Escolher-Pacote($Assets) {
    $lista = @($Assets)
    if ($lista.Count -eq 0) { throw 'A resposta da Adoptium veio vazia.' }
    $p = $lista[0].binary.package
    if (-not $p -or -not $p.link -or -not $p.checksum) { throw 'A resposta da Adoptium mudou de formato.' }
    if ($p.link -notmatch '^https://') { throw 'O endereço de download do Java não é seguro (https).' }
    if ($p.checksum -notmatch '^[0-9a-fA-F]{64}$') { throw 'A soma de verificação do Java está em formato inesperado.' }
    return $p
}

function Confere-Checksum([string]$Arquivo, [string]$Esperado) {
    # Get-FileHash devolve MAIÚSCULAS e a Adoptium publica minúsculas: comparação sem caixa.
    return ((Get-FileHash -LiteralPath $Arquivo -Algorithm SHA256).Hash -ieq $Esperado)
}

# O zip do Java traz UMA pasta no topo (jdk-21.x+y); o conteúdo dela vira o destino.
function Instalar-JdkDeZip([string]$Zip, [string]$Destino) {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('nfse-jdk-' + [guid]::NewGuid())
    try {
        Extrair-Zip $Zip $tmp
        $pastas = @(Get-ChildItem -LiteralPath $tmp -Directory)
        if ($pastas.Count -ne 1) { throw 'O pacote do Java veio em formato inesperado.' }
        if (Test-Path -LiteralPath $Destino) { Remove-Item -LiteralPath $Destino -Recurse -Force }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destino) | Out-Null
        Move-Item -LiteralPath $pastas[0].FullName -Destination $Destino
    } finally { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
}

function Baixar-Jdk([string]$Destino) {
    Dizer 'O Java não foi encontrado. Baixando uma cópia portátil (cerca de 200 MB, só na primeira vez)...'
    $pacote = Escolher-Pacote (Invoke-RestMethod -UseBasicParsing -Uri $script:URL_JDK)
    $zip = Join-Path ([IO.Path]::GetTempPath()) 'nfse-jdk.zip'
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $pacote.link -OutFile $zip
        if (-not (Confere-Checksum $zip $pacote.checksum)) {
            throw 'O arquivo do Java baixado está corrompido (a verificação de integridade falhou). Tente de novo.'
        }
        Instalar-JdkDeZip $zip $Destino
    } finally { Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue }
}

function Compilar([string]$Javac, [string]$Pasta) {
    $saida = Join-Path $Pasta 'classes'
    New-Item -ItemType Directory -Force -Path $saida | Out-Null
    $fontes = @(Get-ChildItem -LiteralPath $Pasta -Filter '*.java' | ForEach-Object { $_.FullName })
    if ($fontes.Count -eq 0) { throw 'Não há arquivos para compilar no pacote.' }
    $antes = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # -encoding UTF-8: os fontes têm acentos, e o padrão do Windows é outro.
        $log = (& $Javac -encoding UTF-8 -d $saida $fontes 2>&1 | ForEach-Object { "$_" }) -join "`n"
        $codigo = $LASTEXITCODE
    } finally { $ErrorActionPreference = $antes }
    if ($codigo -ne 0) { throw "Não foi possível preparar a ferramenta:`n$log" }
}

# Atalho na Área de Trabalho. Falhar aqui não impede o uso.
function Criar-Atalho([string]$Javaw, [string]$Pasta) {
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $w = New-Object -ComObject WScript.Shell
        $atalho = $w.CreateShortcut((Join-Path $desktop 'Teste de certificado NFS-e.lnk'))
        $atalho.TargetPath = $Javaw
        $atalho.Arguments = "-cp `"$Pasta\classes`" ProvarHandshakeMTLSGui"
        $atalho.WorkingDirectory = $Pasta
        $atalho.Save()
        return $true
    } catch { return $false }
}

function Principal {
    $base = Join-Path $env:LOCALAPPDATA 'nfse-agente'
    $app = Join-Path $base 'app'
    $jdk = Join-Path $base 'jdk'

    $instalador = $env:NFSE_INSTALADOR
    if (-not $instalador -or -not (Test-Path -LiteralPath $instalador)) {
        throw 'Não foi possível localizar o instalador. Abra o arquivo Instalar-Agente-NFSe.bat diretamente.'
    }

    Dizer 'Preparando a ferramenta de teste de certificado...'
    Expandir-Pacote (Extrair-Payload $instalador) $app

    $java = Achar-Java $jdk
    if (-not $java) {
        Baixar-Jdk $jdk
        $java = Achar-Java $jdk
        if (-not $java) { throw 'Não foi possível obter o Java.' }
    }

    Dizer 'Compilando...'
    Compilar $java.Javac $app

    if (Criar-Atalho $java.Javaw $app) { Dizer 'Atalho criado na Área de Trabalho: "Teste de certificado NFS-e".' }
    Dizer 'Pronto! Abrindo a ferramenta...'
    Start-Process -FilePath $java.Javaw -ArgumentList @('-cp', "`"$app\classes`"", 'ProvarHandshakeMTLSGui') -WorkingDirectory $app
}

# NFSE_SOMENTE_FUNCOES e o dot-source permitem carregar as funções nos testes
# sem executar a instalação.
if ($env:NFSE_SOMENTE_FUNCOES -ne '1' -and $MyInvocation.InvocationName -ne '.') {
    try { Principal }
    catch {
        Write-Host ''
        Write-Host "Não foi possível concluir: $($_.Exception.Message)"
        exit 1
    }
}
