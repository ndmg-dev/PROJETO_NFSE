# Funções do sistema NFS-e local (Windows, sem Docker), usadas pelo instalador e pelos
# atalhos do dia a dia (Abrir, Parar, Cópia de segurança). Vêm DEPOIS de lib_windows.ps1.
# Compatível com o Windows PowerShell 5.1.

$script:DLLS_VC = @('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')
$script:MARCA_CONF = '# --- NFS-e (gerado pelo instalador; é reescrito a cada instalação) ---'

# ------------------------------------------------------------------ segredos ---

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

# ------------------------------------------------------------ programas externos ---

# Um caminho com espaço (usuário "Ana Maria") precisa de aspas; um sem, não.
function Aspas([string]$Texto) {
    if ($Texto -match '[\s"]') { return '"' + $Texto.Replace('"', '\"') + '"' }
    return $Texto
}

# Roda um programa e espera SÓ por ele, não pelos filhos. O `pg_ctl start` deixa o
# postgres rodando de fundo, e o filho herda os canos do pai. MEDIDO (PowerShell 7 no
# Linux, filho vivo por 12 s): `& programa | Out-Null` e a captura da saída seguram 12 s;
# esta função sem captura volta em 0 s. `Start-Process -Wait` não travou nessa medição,
# mas a documentação do PowerShell 7 diz que ele espera também os descendentes no Windows,
# e isso NÃO foi verificado no 5.1. Lançar com System.Diagnostics.Process e esperar só o
# processo lançado é seguro em todos os casos.
#   -Capturar  lê a saída e o erro (para programas que terminam: initdb, python, pip);
#              NÃO usar com `pg_ctl start`: o filho herdaria o cano e nunca o fecharia.
function Executar-Programa([string]$Exe, [string[]]$Argumentos = @(), [switch]$Capturar,
                           [int]$TimeoutMs = 300000, [hashtable]$Ambiente = $null, [string]$Pasta = '') {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $psi.Arguments = (($Argumentos | ForEach-Object { Aspas $_ }) -join ' ')
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    if ($Pasta) { $psi.WorkingDirectory = $Pasta }
    if ($Ambiente) { foreach ($k in $Ambiente.Keys) { $psi.EnvironmentVariables[$k] = [string]$Ambiente[$k] } }
    if ($Capturar) { $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true }

    $p = [System.Diagnostics.Process]::Start($psi)
    $lerSaida = $null; $lerErro = $null
    if ($Capturar) { $lerSaida = $p.StandardOutput.ReadToEndAsync(); $lerErro = $p.StandardError.ReadToEndAsync() }
    if (-not $p.WaitForExit($TimeoutMs)) {
        try { $p.Kill() } catch { }
        throw "O programa demorou demais e foi encerrado: $Exe"
    }
    $saida = ''
    if ($Capturar) { $saida = $lerSaida.Result + $lerErro.Result }
    return [pscustomobject]@{ Codigo = $p.ExitCode; Saida = $saida }
}

# ---------------------------------------------------------------- caminhos e config ---

function Base-Padrao { return (Join-Path $env:LOCALAPPDATA 'NFSe') }

# Join-Path com 2 argumentos só (o de 3+ é do PowerShell 7).
function Caminhos-Nfse([string]$Base) {
    $pg = Join-Path $Base 'pgsql'
    $py = Join-Path $Base 'python'
    return @{
        Base = $Base
        Bin = Join-Path $Base 'bin'
        Codigo = Join-Path $Base 'codigo'
        Python = $py
        PythonExe = Join-Path $py 'python.exe'
        Pgsql = $pg
        PgBin = Join-Path $pg 'bin'
        Jdk = Join-Path $Base 'jdk'
        Agente = Join-Path $Base 'agente'
        Dados = Join-Path (Join-Path $Base 'dados') 'pg'
        Config = Join-Path $Base 'config'
        Logs = Join-Path $Base 'logs'
        Cache = Join-Path $Base 'cache'
    }
}

function Ler-Json([string]$Arquivo) {
    if (Test-Path -LiteralPath $Arquivo) { return (Get-Content -Raw -LiteralPath $Arquivo -Encoding UTF8 | ConvertFrom-Json) }
    return $null
}

function Salvar-Json([string]$Arquivo, $Objeto) {
    [IO.File]::WriteAllText($Arquivo, ($Objeto | ConvertTo-Json -Depth 5), $script:Utf8SemBom)
}

# Cria os segredos na primeira vez e NUNCA os troca depois: com o banco já criado, uma
# senha nova o deixaria inacessível. Arquivo existente e incompleto é erro, não recriação.
function Garantir-Segredos([string]$Arquivo) {
    $atual = Ler-Json $Arquivo
    if ($atual) {
        if ($atual.postgres_senha -and $atual.app_senha -and $atual.jwt_secret) { return $atual }
        throw "O arquivo de senhas está incompleto ($Arquivo). Não vou recriá-lo para não deixar o banco inacessível."
    }
    $novo = [pscustomobject]@{
        postgres_senha = (Novo-Hex 24)
        app_senha = (Novo-Hex 24)
        jwt_secret = (Novo-Base64 32)
    }
    Salvar-Json $Arquivo $novo
    Restringir-Arquivo $Arquivo
    return $novo
}

# Uma porta que dá para abrir em 127.0.0.1 (só ali: nenhum aviso do firewall do Windows).
function Porta-Livre([int]$Preferida, [int]$Faixa = 50) {
    for ($p = $Preferida; $p -le ($Preferida + $Faixa); $p++) {
        $l = $null
        try {
            $l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $p)
            $l.Start()
            return $p
        } catch { } finally { if ($l) { try { $l.Stop() } catch { } } }
    }
    throw "Não encontrei uma porta livre a partir de $Preferida."
}

function Garantir-Config([string]$Arquivo) {
    $atual = Ler-Json $Arquivo
    if ($atual -and $atual.porta_api -and $atual.porta_pg) { return $atual }
    $novo = [pscustomobject]@{ porta_api = (Porta-Livre 8000); porta_pg = (Porta-Livre 54329) }
    Salvar-Json $Arquivo $novo
    return $novo
}

# ---------------------------------------------------------------------- requisitos ---

function Problemas-De-Requisitos([string]$Base, $VersaoWindows = $null, $Sistema64 = $null, $LivreMB = $null) {
    $problemas = @()
    if ($null -eq $VersaoWindows) { $VersaoWindows = [Environment]::OSVersion.Version }
    if ($null -eq $Sistema64) { $Sistema64 = [Environment]::Is64BitOperatingSystem }
    if ($null -eq $LivreMB) {
        try {
            $raiz = [IO.Path]::GetPathRoot($Base)
            $LivreMB = [int]([IO.DriveInfo]$raiz).AvailableFreeSpace / 1MB
        } catch { $LivreMB = 999999 }
    }
    if ($VersaoWindows.Major -lt 10) { $problemas += 'É preciso o Windows 10 ou 11 (o banco de dados usa componentes que só existem neles).' }
    if (-not $Sistema64) { $problemas += 'É preciso um Windows de 64 bits.' }
    if ($LivreMB -lt 2000) { $problemas += "Há pouco espaço em disco: são necessários cerca de 2 GB livres e há $([int]$LivreMB) MB." }
    return $problemas
}

# --------------------------------------------------------- runtime do Visual C++ ---

# O postgres.exe importa vcruntime140, vcruntime140_1 e msvcp140. Elas NÃO fazem parte do
# Windows: vêm do "Visual C++ Redistributable", que num PC limpo pode não estar (o
# postgres.exe então nem abre: erro 0xc0000135). Instalar o redistributable exige
# administrador; em vez disso, copia-se o mesmo conjunto (que o JDK já baixado traz) para
# a pasta do programa, onde o Windows procura primeiro.
function Pasta-DllsDoSistema {
    if ([Environment]::Is64BitProcess) { return (Join-Path $env:SystemRoot 'System32') }
    return (Join-Path $env:SystemRoot 'Sysnative')   # PowerShell de 32 bits num Windows de 64
}

function Faltam-DllsDoVc([string]$PastaDoSistema) {
    return @($script:DLLS_VC | Where-Object { -not (Test-Path -LiteralPath (Join-Path $PastaDoSistema $_)) })
}

# Copia só o que ainda não existe no destino. Devolve os nomes copiados.
function Copiar-DllsDoVc([string]$Origem, [string[]]$Destinos) {
    $copiadas = @()
    foreach ($destino in $Destinos) {
        New-Item -ItemType Directory -Force -Path $destino | Out-Null
        foreach ($dll in $script:DLLS_VC) {
            $alvo = Join-Path $destino $dll
            if (Test-Path -LiteralPath $alvo) { continue }
            $fonte = Join-Path $Origem $dll
            if (-not (Test-Path -LiteralPath $fonte)) { throw "Não encontrei $dll em $Origem." }
            Copy-Item -LiteralPath $fonte -Destination $alvo
            $copiadas += "$dll -> $destino"
        }
    }
    return $copiadas
}

# ------------------------------------------------------------- Python embutido ---

# O Python embutido só enxerga site-packages e a pasta do código se o ._pth mandar: a
# presença desse arquivo desliga PYTHONPATH e o resto, e `import site` vem comentado.
function Escrever-Pth([string]$Arquivo, [string]$ZipDaBiblioteca) {
    $linhas = @($ZipDaBiblioteca, '.', 'Lib\site-packages', '..\codigo', 'import site')
    [IO.File]::WriteAllLines($Arquivo, $linhas, $script:Utf8SemBom)
}

# Python do sistema instalado: -X utf8 para os logs com acento, -u para não guardar saída.
function Python-Nfse($C, [string[]]$Argumentos, [switch]$Capturar, [hashtable]$Ambiente = $null, [int]$TimeoutMs = 600000) {
    $todos = @('-X', 'utf8', '-u') + $Argumentos
    return (Executar-Programa $C.PythonExe $todos -Capturar:$Capturar -TimeoutMs $TimeoutMs -Ambiente $Ambiente -Pasta $C.Codigo)
}

# --------------------------------------------------------------------- PostgreSQL ---

function Argumentos-Initdb([string]$Dados, [string]$ArquivoDaSenha) {
    # A senha vai por arquivo (--pwfile), nunca na linha de comando: argumentos de processo
    # aparecem para qualquer programa que liste processos.
    return @('-D', $Dados, '-U', 'nfse', '-E', 'UTF8', '--locale=C', '--auth=scram-sha-256', "--pwfile=$ArquivoDaSenha")
}

# Só escuta em 127.0.0.1: nada de rede, nada de aviso do firewall. Reescreve o próprio bloco.
function Configurar-Postgres([string]$ArquivoConf, [int]$Porta) {
    $texto = [IO.File]::ReadAllText($ArquivoConf)
    $i = $texto.IndexOf($script:MARCA_CONF)
    if ($i -ge 0) { $texto = $texto.Substring(0, $i) }
    $bloco = @($script:MARCA_CONF, "listen_addresses = '127.0.0.1'", "port = $Porta", 'max_connections = 30', 'shared_buffers = 64MB') -join "`n"
    [IO.File]::WriteAllText($ArquivoConf, ($texto.TrimEnd() + "`n`n" + $bloco + "`n"), $script:Utf8SemBom)
}

function Pg-Ctl($C, [string[]]$Argumentos, [int]$TimeoutMs = 120000) {
    return (Executar-Programa (Join-Path $C.PgBin 'pg_ctl.exe') $Argumentos -TimeoutMs $TimeoutMs)
}

function Postgres-Rodando($C) {
    # Instalação nova: sem pg_ctl.exe ou sem banco criado, não há o que estar rodando
    # (e executar um programa que não existe lança exceção).
    if (-not (Test-Path -LiteralPath (Join-Path $C.PgBin 'pg_ctl.exe'))) { return $false }
    if (-not (Test-Path -LiteralPath (Join-Path $C.Dados 'PG_VERSION'))) { return $false }
    return ((Pg-Ctl $C @('status', '-D', $C.Dados) 30000).Codigo -eq 0)
}

function Iniciar-Postgres($C) {
    if (Postgres-Rodando $C) { return }
    $log = Join-Path $C.Logs 'postgres.log'
    $r = Pg-Ctl $C @('start', '-D', $C.Dados, '-l', $log, '-w', '-t', '90') 150000
    if ($r.Codigo -ne 0) { throw "O banco de dados não iniciou. Veja o registro em $log." }
}

function Parar-Postgres($C) {
    if (Postgres-Rodando $C) { [void](Pg-Ctl $C @('stop', '-D', $C.Dados, '-m', 'fast', '-w', '-t', '90') 150000) }
}

# ---------------------------------------------------------------------------- API ---

function Url-Do-Banco([string]$Usuario, [string]$Senha, [int]$Porta) {
    # Senhas hexadecimais: nenhum caractere que precise de escape na URL.
    return "postgresql+psycopg://${Usuario}:${Senha}@127.0.0.1:${Porta}/nfse"
}

function Ambiente-Admin($Seg, $Cfg) {
    return @{ DATABASE_URL = (Url-Do-Banco 'nfse' $Seg.postgres_senha $Cfg.porta_pg); APP_DB_PASSWORD = $Seg.app_senha }
}

# Sem REDIS_URL: a API local não tem fila.
function Ambiente-Da-Api($Seg, $Cfg) {
    return @{
        DATABASE_URL = (Url-Do-Banco 'nfse_app' $Seg.app_senha $Cfg.porta_pg)
        JWT_SECRET = $Seg.jwt_secret
    }
}

function Api-Respondendo([int]$Porta, [int]$TimeoutS = 3) {
    try { return ((Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Porta/health" -TimeoutSec $TimeoutS).StatusCode -eq 200) }
    catch { return $false }
}

function Esperar-Api([int]$Porta, [int]$Segundos = 90) {
    for ($i = 0; $i -lt $Segundos; $i++) {
        if (Api-Respondendo $Porta) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Iniciar-Api($C, $Seg, $Cfg) {
    if (Api-Respondendo $Cfg.porta_api) { return }
    $saida = Join-Path $C.Logs 'api.log'
    $erro = Join-Path $C.Logs 'api-erro.log'
    $antes = @{}
    $novas = Ambiente-Da-Api $Seg $Cfg
    foreach ($k in $novas.Keys) { $antes[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, [string]$novas[$k]) }
    try {
        $p = Start-Process -FilePath $C.PythonExe -WorkingDirectory $C.Codigo -WindowStyle Hidden -PassThru `
            -ArgumentList @('-X', 'utf8', '-m', 'uvicorn', 'app.api.main:app', '--host', '127.0.0.1', '--port', [string]$Cfg.porta_api) `
            -RedirectStandardOutput $saida -RedirectStandardError $erro
        [IO.File]::WriteAllText((Join-Path $C.Config 'api.pid'), [string]$p.Id, $script:Utf8SemBom)
    } finally {
        foreach ($k in $novas.Keys) { [Environment]::SetEnvironmentVariable($k, $antes[$k]) }
    }
}

# Só encerra o processo se ele for MESMO o nosso python: o número de um processo antigo
# pode ter sido reaproveitado pelo Windows para outro programa.
function Parar-Api($C) {
    $arquivo = Join-Path $C.Config 'api.pid'
    if (-not (Test-Path -LiteralPath $arquivo)) { return }
    try {
        $id = [int](Get-Content -LiteralPath $arquivo -Raw)
        $p = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($p -and $p.Path -and ($p.Path -ieq $C.PythonExe)) { Stop-Process -Id $id -Force }
    } catch { }
    Remove-Item -LiteralPath $arquivo -Force -ErrorAction SilentlyContinue
}

# Encerra QUALQUER processo que esteja rodando de dentro da pasta de instalação (python,
# postgres, java de uma tentativa anterior que falhou ou foi interrompida): eles seguram
# as pastas e impedem a troca do código. Só toca no que roda de dentro de $C.Base.
function Encerrar-Processos-Da-Instalacao($C) {
    $raiz = ([IO.Path]::GetFullPath($C.Base)).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $encerrados = @()
    foreach ($p in @(Get-Process -ErrorAction SilentlyContinue)) {
        if ($p.Id -eq $PID) { continue }
        $caminho = $null
        try { $caminho = $p.Path } catch { }
        if ($caminho -and $caminho.StartsWith($raiz, [StringComparison]::OrdinalIgnoreCase)) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction Stop; $encerrados += $p.Id }
            catch { Dizer "  AVISO: não consegui encerrar $($p.ProcessName) (pid $($p.Id)): $($_.Exception.Message)" }
        } elseif (-not $caminho -and $p.ProcessName -match '^(python|pythonw|postgres|pg_ctl|java|javaw)$') {
            # Um programa comum não enxerga o caminho de um processo aberto como
            # administrador: é o que sobra de uma instalação feita "como administrador".
            Dizer "  AVISO: há um $($p.ProcessName) (pid $($p.Id)) que não consigo inspecionar; se a pasta continuar presa, encerre-o no Gerenciador de Tarefas ou reinicie o computador."
        }
    }
    if ($encerrados.Count -gt 0) { Start-Sleep -Milliseconds 800 }
    return $encerrados
}

# Remove e recria uma pasta. Logo depois de extrair arquivos, o antivírus ou o Explorer
# costumam segurá-la por instantes: tenta de novo antes de desistir.
function Substituir-Pasta([string]$Origem, [string]$Destino, [int]$Tentativas = 8) {
    for ($i = 1; $i -le $Tentativas; $i++) {
        try {
            if (Test-Path -LiteralPath $Destino) { Remove-Item -LiteralPath $Destino -Recurse -Force -ErrorAction Stop }
            Move-Item -LiteralPath $Origem -Destination $Destino -ErrorAction Stop
            return
        } catch {
            if ($i -eq $Tentativas) { throw }
            Start-Sleep -Seconds 1
        }
    }
}

# Liga o que estiver desligado e devolve a configuração. Idempotente: é o que o atalho
# "NFS-e" faz toda vez que é aberto.
function Ligar-Sistema($C) {
    $cfg = Ler-Json (Join-Path $C.Config 'config.json')
    $seg = Ler-Json (Join-Path $C.Config 'segredos.json')
    if (-not $cfg -or -not $seg) { throw 'O NFS-e não está instalado completamente. Rode o instalador de novo.' }
    Iniciar-Postgres $C
    Iniciar-Api $C $seg $cfg
    if (-not (Esperar-Api $cfg.porta_api 90)) {
        throw "O sistema não respondeu a tempo. Veja $(Join-Path $C.Logs 'api-erro.log')."
    }
    return [pscustomobject]@{ Config = $cfg; Segredos = $seg }
}

# Já configurado: a página inicial. Ainda não: o assistente, com o código na URL.
function Url-Inicial($C, $Seg, $Cfg) {
    $base = "http://localhost:$($Cfg.porta_api)"
    $estado = ''
    try { $estado = (Invoke-WebRequest -UseBasicParsing -Uri "$base/setup/status" -TimeoutSec 5).Content } catch { }
    if ($estado -match '"configurado"\s*:\s*true') { return "$base/" }
    $r = Python-Nfse $C @('-m', 'app.setup.codigo') -Capturar -Ambiente (Ambiente-Da-Api $Seg $Cfg) -TimeoutMs 60000
    $codigo = ($r.Saida.Trim() -split "`r?`n" | Select-Object -Last 1).Trim()
    if ($r.Codigo -ne 0 -or $codigo -notmatch '^[A-Z2-7]{4}-[A-Z2-7]{4}$') { return "$base/setup" }
    return "$base/setup?codigo=$codigo"
}

function Mostrar-Erro([string]$Mensagem) {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [void][System.Windows.Forms.MessageBox]::Show($Mensagem, 'NFS-e', 'OK', 'Error')
    } catch { Write-Host $Mensagem }
}

# ---------------------------------------------------------- cópia de segurança ---

# Cópia A FRIO: com o banco parado, é uma cópia de arquivos (o pacote de PostgreSQL não
# traz pg_dump). Leva também config\ porque restaurar os dados sem as senhas deixaria o
# banco inacessível. Por isso o arquivo é sensível e deve ficar em lugar seguro.
function Fazer-Copia($C, [string]$PastaDestino, [switch]$SemParar) {
    New-Item -ItemType Directory -Force -Path $PastaDestino | Out-Null
    $estavaLigado = (Test-Path -LiteralPath $C.Dados) -and (Postgres-Rodando $C)
    if (-not $SemParar) { Parar-Api $C; Parar-Postgres $C }
    $arquivo = Join-Path $PastaDestino ('nfse-{0:yyyyMMdd-HHmmss}.zip' -f (Get-Date))
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('nfse-copia-' + [guid]::NewGuid())
    try {
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        Copy-Item -LiteralPath $C.Dados -Destination (Join-Path $tmp 'dados') -Recurse
        Copy-Item -LiteralPath $C.Config -Destination (Join-Path $tmp 'config') -Recurse
        [IO.Compression.ZipFile]::CreateFromDirectory($tmp, $arquivo)
    } finally { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
    Restringir-Arquivo $arquivo
    return [pscustomobject]@{ Arquivo = $arquivo; EstavaLigado = $estavaLigado }
}

# Guarda o que existia antes (nunca apaga): se a cópia estiver errada, dá para voltar.
function Restaurar-Copia($C, [string]$Arquivo) {
    Parar-Api $C; Parar-Postgres $C
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('nfse-restaura-' + [guid]::NewGuid())
    try {
        Extrair-Zip $Arquivo $tmp
        if (-not ((Test-Path -LiteralPath (Join-Path $tmp 'dados')) -and (Test-Path -LiteralPath (Join-Path $tmp 'config')))) {
            throw 'Este arquivo não parece ser uma cópia de segurança do NFS-e.'
        }
        $carimbo = '{0:yyyyMMdd-HHmmss}' -f (Get-Date)
        $antesDados = Join-Path (Split-Path -Parent $C.Dados) "pg.antes-$carimbo"
        $antesConfig = Join-Path (Split-Path -Parent $C.Config) "config.antes-$carimbo"
        if (Test-Path -LiteralPath $C.Dados) { Move-Item -LiteralPath $C.Dados -Destination $antesDados }
        if (Test-Path -LiteralPath $C.Config) { Move-Item -LiteralPath $C.Config -Destination $antesConfig }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $C.Dados) | Out-Null
        Move-Item -LiteralPath (Join-Path $tmp 'dados') -Destination $C.Dados
        Move-Item -LiteralPath (Join-Path $tmp 'config') -Destination $C.Config
    } finally { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
