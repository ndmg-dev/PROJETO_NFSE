# Biblioteca compartilhada dos instaladores do Windows (agente e instalação local).
# Não é para executar direto: o gerador a coloca antes do script de cada instalador.
# Compatível com o Windows PowerShell 5.1. Só usa Join-Path com 2 argumentos (o de 3+
# só existe no PowerShell 7) e nenhuma sintaxe do 7 (?., ?:, &&).

$ErrorActionPreference = 'Stop'
# O Windows PowerShell 5.1 negocia TLS antigo por padrão e as fontes exigem 1.2.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
# No 5.1 a barra de progresso torna o download dezenas de vezes mais lento.
$ProgressPreference = 'SilentlyContinue'
# Atrás de proxy de escritório com autenticação do Windows: usa a credencial do usuário.
try { [Net.WebRequest]::DefaultWebProxy.Credentials = [Net.CredentialCache]::DefaultCredentials } catch { }

# ZipFile do .NET em vez de Expand-Archive: no Windows PowerShell 5.1 o Expand-Archive
# é muito lento em zips grandes, e o do JDK tem centenas de arquivos.
Add-Type -AssemblyName System.IO.Compression.FileSystem

$script:URL_JDK = 'https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse'
$script:JAVA_MINIMO = 17   # o código usa records (Java 16+) e java.net.http (Java 11+)
$script:ArquivoLog = $null
$script:Utf8SemBom = New-Object System.Text.UTF8Encoding($false)

# Escreve na tela e, se houver um arquivo de registro definido, nele também.
function Dizer([string]$Texto) {
    Write-Host $Texto
    if ($script:ArquivoLog) {
        try { [IO.File]::AppendAllText($script:ArquivoLog, ("{0:HH:mm:ss} {1}`r`n" -f (Get-Date), $Texto), $script:Utf8SemBom) } catch { }
    }
}

function Extrair-Zip([string]$Zip, [string]$Destino) {
    [IO.Compression.ZipFile]::ExtractToDirectory($Zip, $Destino)
}

function Extrair-Payload([string]$CaminhoDoInstalador) {
    $t = [IO.File]::ReadAllText($CaminhoDoInstalador, [Text.Encoding]::UTF8)
    $m = '#' + 'PAYLOAD#'
    $i = $t.LastIndexOf($m)
    if ($i -lt 0) { throw 'O instalador está incompleto (pacote não encontrado). Baixe-o de novo.' }
    $b64 = $t.Substring($i + $m.Length) -replace '\s', ''
    return [Convert]::FromBase64String($b64)
}

function Expandir-Pacote([byte[]]$Zip, [string]$Destino) {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('nfse-pacote-' + [guid]::NewGuid() + '.zip')
    try {
        [IO.File]::WriteAllBytes($tmp, $Zip)
        if (Test-Path -LiteralPath $Destino) { Remove-Item -LiteralPath $Destino -Recurse -Force }
        Extrair-Zip $tmp $Destino
    } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
}

function Confere-Checksum([string]$Arquivo, [string]$Esperado) {
    # Get-FileHash devolve MAIÚSCULAS e as fontes publicam minúsculas: comparação sem caixa.
    return ((Get-FileHash -LiteralPath $Arquivo -Algorithm SHA256).Hash -ieq $Esperado)
}

# Baixa, confere o SHA-256 e só então põe o arquivo no destino. Um arquivo que não
# confere NUNCA fica no destino (o parcial é apagado). Já baixado e íntegro: não baixa
# de novo. `file:` existe para instalação offline e para os testes; a rede só aceita https.
function Baixar-Verificado([string]$Url, [string]$Sha256, [string]$Destino, [int]$Tentativas = 3, [int]$PausaS = 2) {
    if ($Sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw "Soma de verificação inválida para $Url" }
    $pasta = Split-Path -Parent $Destino
    if ($pasta) { New-Item -ItemType Directory -Force -Path $pasta | Out-Null }
    if ((Test-Path -LiteralPath $Destino) -and (Confere-Checksum $Destino $Sha256)) { return }

    $parcial = "$Destino.parcial"
    $erro = 'erro desconhecido'
    for ($i = 1; $i -le $Tentativas; $i++) {
        try {
            Remove-Item -LiteralPath $parcial -Force -ErrorAction SilentlyContinue
            if ($Url -like 'file:*') { Copy-Item -LiteralPath ([Uri]$Url).LocalPath -Destination $parcial -Force }
            elseif ($Url -match '^https://') { Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $parcial }
            else { throw "endereço não permitido (só https): $Url" }
            if (-not (Confere-Checksum $parcial $Sha256)) { throw 'a verificação de integridade falhou' }
            Move-Item -LiteralPath $parcial -Destination $Destino -Force
            return
        } catch {
            $erro = $_.Exception.Message
            Remove-Item -LiteralPath $parcial -Force -ErrorAction SilentlyContinue
            if ($i -lt $Tentativas -and $PausaS -gt 0) { Start-Sleep -Seconds ($PausaS * $i) }
        }
    }
    throw "Não foi possível baixar $Url ($erro)"
}

# Equivalente do chmod 600: só o usuário atual lê o arquivo. Falhar aqui não impede a instalação.
function Restringir-Arquivo([string]$Caminho) {
    try { & icacls.exe $Caminho /inheritance:r /grant:r "$($env:USERNAME):(R,W)" 2>&1 | Out-Null } catch { }
}

# ---- Java ----

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

function Escolher-Pacote($Assets) {
    $lista = @($Assets)
    if ($lista.Count -eq 0) { throw 'A resposta da Adoptium veio vazia.' }
    $p = $lista[0].binary.package
    if (-not $p -or -not $p.link -or -not $p.checksum) { throw 'A resposta da Adoptium mudou de formato.' }
    if ($p.link -notmatch '^https://') { throw 'O endereço de download do Java não é seguro (https).' }
    if ($p.checksum -notmatch '^[0-9a-fA-F]{64}$') { throw 'A soma de verificação do Java está em formato inesperado.' }
    return $p
}

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
        Baixar-Verificado $pacote.link $pacote.checksum $zip
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

# Atalho (.lnk). Falhar aqui não impede o uso.
function Criar-Atalho([string]$Arquivo, [string]$Alvo, [string]$Argumentos, [string]$Pasta) {
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Arquivo) | Out-Null
        $w = New-Object -ComObject WScript.Shell
        $atalho = $w.CreateShortcut($Arquivo)
        $atalho.TargetPath = $Alvo
        $atalho.Arguments = $Argumentos
        $atalho.WorkingDirectory = $Pasta
        $atalho.Save()
        return $true
    } catch { return $false }
}
