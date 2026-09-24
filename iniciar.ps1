# Instala e inicia o sistema NFS-e nesta máquina (Windows). Chamado por Iniciar.bat.
# Não pergunta nada:
#   1. cria o .env com senhas aleatórias (só na primeira vez);
#   2. sobe o banco, a fila e a API, aplicando a estrutura do banco sozinho;
#   3. abre o navegador no assistente de primeiro acesso, já com o código.
#
# Compatível com o Windows PowerShell 5.1 (o que vem no Windows 10/11).
#   $env:NFSE_PORTA = '9000'              usa outra porta (padrão 8000)
#   $env:NFSE_NAO_ABRIR_NAVEGADOR = '1'   não abre o navegador

# 'Continue' de propósito: no 5.1, 'Stop' transforma a saída de erro de um
# programa externo (docker) em exceção. Os erros são checados por $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$script:Utf8SemBom = New-Object System.Text.UTF8Encoding($false)

function Dizer([string]$Texto) { Write-Host $Texto }

# Hexadecimal, não base64: '/' e '+' quebram a URL de conexão com o banco.
function Novo-Hex([int]$Bytes) {
    $b = New-Object byte[] $Bytes
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($b) } finally { $rng.Dispose() }
    return (($b | ForEach-Object { $_.ToString('x2') }) -join '')
}

function Novo-Base64([int]$Bytes) {
    $b = New-Object byte[] $Bytes
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($b) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($b)
}

# Lê NOME=valor do .env; só entram chaves com valor.
function Ler-Env([string]$Caminho) {
    $achado = @{}
    if (-not (Test-Path -LiteralPath $Caminho)) { return $achado }
    foreach ($linha in [IO.File]::ReadAllLines($Caminho)) {
        if ($linha -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.+)$') { $achado[$Matches[1]] = $Matches[2] }
    }
    return $achado
}

# Cria as chaves que faltam e devolve os nomes que criou. Nunca reescreve uma
# senha que já existe (trocá-la depois de o banco ser criado o deixaria
# inacessível). Sem BOM: um BOM no início corrompe a primeira chave no Compose.
function Garantir-Env([string]$Caminho, [hashtable]$Geradores) {
    $existentes = Ler-Env $Caminho
    $criadas = @()
    foreach ($nome in $Geradores.Keys) {
        if (-not $existentes.ContainsKey($nome)) {
            $valor = & $Geradores[$nome]
            [IO.File]::AppendAllText($Caminho, "$nome=$valor`n", $script:Utf8SemBom)
            $criadas += $nome
        }
    }
    return $criadas
}

# Equivalente do chmod 600: só o usuário atual lê o .env. Falhar aqui não
# impede a instalação.
function Restringir-Arquivo([string]$Caminho) {
    try { & icacls.exe $Caminho /inheritance:r /grant:r "$($env:USERNAME):(R,W)" 2>&1 | Out-Null } catch { }
}

function Configurado-DoJson([string]$Json) {
    return [bool]($Json -match '"configurado"\s*:\s*true')
}

function Testar-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Dizer 'O Docker Desktop não está instalado nesta máquina.'
        Dizer 'Vou abrir a página de download. Instale, abra o Docker Desktop e rode este arquivo de novo.'
        Start-Process 'https://www.docker.com/products/docker-desktop/'
        return $false
    }
    & docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Dizer 'O Docker está instalado, mas não está em execução.'
        Dizer 'Abra o Docker Desktop, espere o ícone ficar verde e rode este arquivo de novo.'
        return $false
    }
    & docker compose version 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Dizer "Falta o Docker Compose v2 (comando 'docker compose'). Atualize o Docker Desktop."
        return $false
    }
    return $true
}

function Principal {
    Set-Location -LiteralPath $PSScriptRoot
    $arquivo = 'docker-compose.instalacao.yml'
    $porta = if ($env:NFSE_PORTA) { $env:NFSE_PORTA } else { '8000' }
    $url = "http://localhost:$porta"

    if (-not (Testar-Docker)) { exit 1 }

    $criadas = Garantir-Env (Join-Path $PSScriptRoot '.env') @{
        POSTGRES_PASSWORD = { Novo-Hex 24 }
        APP_DB_PASSWORD   = { Novo-Hex 24 }
        JWT_SECRET        = { Novo-Base64 32 }
    }
    if ($criadas.Count -gt 0) {
        Restringir-Arquivo (Join-Path $PSScriptRoot '.env')
        Dizer 'Senhas geradas em .env (ficam só neste computador). Guarde uma cópia em local seguro.'
    }

    $log = 'instalacao.log'
    Dizer 'Subindo o sistema (a primeira vez pode levar alguns minutos)...'
    # cmd /c evita que o PowerShell 5.1 embrulhe cada linha de erro do docker.
    & cmd.exe /c "docker compose -f $arquivo up -d --build > $log 2>&1"
    if ($LASTEXITCODE -ne 0) {
        Dizer "Não foi possível subir o sistema. Últimas linhas do registro ($log):"
        Get-Content -LiteralPath $log -Tail 20 | ForEach-Object { Dizer $_ }
        exit 1
    }

    Dizer 'Esperando o sistema ficar pronto...'
    $pronto = $false
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Uri "$url/health" -TimeoutSec 4
            if ($r.StatusCode -eq 200) { $pronto = $true; break }
        } catch { }
        Start-Sleep -Seconds 2
    }
    if (-not $pronto) {
        Dizer 'O sistema não respondeu a tempo. Veja o que houve com:'
        Dizer "  docker compose -f $arquivo logs api migrate"
        exit 1
    }

    $destino = "$url/"
    $estado = ''
    try { $estado = (Invoke-WebRequest -UseBasicParsing -Uri "$url/setup/status" -TimeoutSec 4).Content } catch { }
    if (-not (Configurado-DoJson $estado)) {
        $saida = & docker compose -f $arquivo exec -T api python -m app.setup.codigo
        $codigo = ($saida | Select-Object -First 1).ToString().Trim()
        $destino = "$url/setup?codigo=$codigo"
    }

    Dizer ''
    Dizer "Pronto. Sistema em $url"
    try {
        $ip = [Net.Dns]::GetHostAddresses([Net.Dns]::GetHostName()) |
            Where-Object { $_.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1
        if ($ip) { Dizer "Para acessar de outros computadores da rede: http://${ip}:$porta" }
    } catch { }

    if ($env:NFSE_NAO_ABRIR_NAVEGADOR -ne '1') { Start-Process $destino }
    Dizer "Abra no navegador: $destino"
}

# Permite carregar as funções (dot-source) nos testes sem executar a instalação.
if ($MyInvocation.InvocationName -ne '.') { Principal }
