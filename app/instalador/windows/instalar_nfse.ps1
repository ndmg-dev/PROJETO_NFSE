# Instalador do sistema NFS-e para Windows, SEM Docker. Embutido em Instalar-NFSe.bat,
# depois de lib_windows.ps1 e comum_nfse.ps1. Compatível com o Windows PowerShell 5.1.
#
# Instala tudo em %LOCALAPPDATA%\NFSe, para o usuário atual, sem pedir administrador:
#   python\   Python embutido (3.12) e as dependências, com hash conferido
#   pgsql\    PostgreSQL 16 portátil, escutando só em 127.0.0.1
#   codigo\   a aplicação      dados\  o banco (sobrevive às atualizações)
#   jdk\ agente\   Java portátil e o teste de certificado
# Pode rodar de novo a qualquer momento: atualiza o código, aplica as migrations e
# MANTÉM os dados e as senhas.

function Ler-Pins([string]$Caminho) {
    return (Get-Content -Raw -LiteralPath $Caminho -Encoding UTF8 | ConvertFrom-Json)
}

function Hash-Do-Arquivo([string]$Arquivo) {
    return (Get-FileHash -LiteralPath $Arquivo -Algorithm SHA256).Hash.ToLower()
}

function Falha-Com-Log([string]$Passo, $Resultado, [string]$Log) {
    $fim = (($Resultado.Saida -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -Last 8) -join "`n"
    throw "$Passo falhou (código $($Resultado.Codigo)). Últimas linhas:`n$fim`n`nRegistro completo: $Log"
}

# Troca o código, os atalhos e o teste de certificado pela versão do pacote. Os dados
# (dados\, config\) não são tocados. Precisa parar a API antes: ela roda de dentro de codigo\.
function Instalar-Codigo($C, [string]$Payload) {
    $tmp = Join-Path $C.Cache ('pacote-' + [guid]::NewGuid())
    try {
        Expandir-Pacote (Extrair-Payload $Payload) $tmp
        Parar-Api $C
        foreach ($par in @(@('codigo', $C.Codigo), @('bin', $C.Bin), @('agente', $C.Agente))) {
            $origem = Join-Path $tmp $par[0]
            if (-not (Test-Path -LiteralPath $origem)) { throw "O pacote está incompleto: falta a pasta $($par[0])." }
            if (Test-Path -LiteralPath $par[1]) { Remove-Item -LiteralPath $par[1] -Recurse -Force }
            Move-Item -LiteralPath $origem -Destination $par[1]
        }
    } finally { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
}

function Precisa-Python($C, $Pins, $Versoes) {
    if (-not (Test-Path -LiteralPath $C.PythonExe)) { return $true }
    return (-not ($Versoes -and $Versoes.python -eq $Pins.python.versao))
}

function Instalar-Python($C, $Pins, $Versoes) {
    $whl = Join-Path $C.Cache 'pip.whl'
    Baixar-Verificado $Pins.pip.url $Pins.pip.sha256 $whl
    if (Precisa-Python $C $Pins $Versoes) {
        Dizer "Baixando o Python $($Pins.python.versao) (cerca de 11 MB)..."
        $zip = Join-Path $C.Cache 'python-embed.zip'
        Baixar-Verificado $Pins.python.url $Pins.python.sha256 $zip
        if (Test-Path -LiteralPath $C.Python) { Remove-Item -LiteralPath $C.Python -Recurse -Force }
        Extrair-Zip $zip $C.Python
        Escrever-Pth (Join-Path $C.Python $Pins.python.arquivo_pth) $Pins.python.zip_da_biblioteca
        New-Item -ItemType Directory -Force -Path (Join-Path (Join-Path $C.Python 'Lib') 'site-packages') | Out-Null
    }
    return $whl
}

# Instala as dependências travadas: --require-hashes exige o SHA-256 de cada pacote (o lock
# tem o de cada wheel do Windows) e --only-binary evita rodar código de instalação.
function Instalar-Dependencias($C, [string]$Whl, $Versoes) {
    $lock = Join-Path $C.Codigo 'requirements-local.lock'
    $hashLock = Hash-Do-Arquivo $lock
    $importa = 'import fastapi, sqlalchemy, psycopg, bcrypt, pydantic, uvicorn, alembic, openpyxl, httpx; print(psycopg.pq.version())'
    if ($Versoes -and $Versoes.lock_sha256 -eq $hashLock) {
        if ((Python-Nfse $C @('-c', $importa) -Capturar -TimeoutMs 120000).Codigo -eq 0) { return $hashLock }
    }
    Dizer 'Instalando as bibliotecas do sistema (cerca de 10 MB)...'
    $r = Python-Nfse $C @('-m', 'app.local.rodar_pip', $Whl, 'install', '--no-input', '--disable-pip-version-check',
        '--require-hashes', '--only-binary=:all:', '--no-deps', '-r', $lock) -Capturar
    if ($r.Codigo -ne 0) { Falha-Com-Log 'A instalação das bibliotecas' $r (Join-Path $C.Logs 'instalacao.log') }
    $r = Python-Nfse $C @('-c', $importa) -Capturar -TimeoutMs 120000
    if ($r.Codigo -ne 0) { Falha-Com-Log 'A conferência das bibliotecas' $r (Join-Path $C.Logs 'instalacao.log') }
    return $hashLock
}

function Garantir-Java($C) {
    $java = Achar-Java $C.Jdk
    if ($java) { return $java }
    Baixar-Jdk $C.Jdk
    return (Achar-Java $C.Jdk)
}

function Instalar-Postgres($C, $Pins, $Versoes) {
    if ((Test-Path -LiteralPath (Join-Path $C.PgBin 'postgres.exe')) -and $Versoes -and $Versoes.postgres -eq $Pins.postgres.versao) { return }
    Dizer "Baixando o PostgreSQL $($Pins.postgres.versao) (cerca de 23 MB)..."
    $jar = Join-Path $C.Cache 'postgres.jar'
    Baixar-Verificado $Pins.postgres.url $Pins.postgres.sha256 $jar
    $tmp = Join-Path $C.Cache ('pg-' + [guid]::NewGuid())
    try {
        Extrair-Zip $jar $tmp                                    # o .jar é um zip
        $txz = Get-ChildItem -LiteralPath $tmp -Filter '*.txz' | Select-Object -First 1
        if (-not $txz) { throw 'O pacote do PostgreSQL não tem o arquivo esperado (.txz).' }
        Parar-Postgres $C                                        # não se troca o programa com o banco no ar
        if (Test-Path -LiteralPath $C.Pgsql) { Remove-Item -LiteralPath $C.Pgsql -Recurse -Force }
        $r = Python-Nfse $C @('-m', 'app.local.extrair_txz', $txz.FullName, $C.Pgsql) -Capturar
        if ($r.Codigo -ne 0) { Falha-Com-Log 'A extração do PostgreSQL' $r (Join-Path $C.Logs 'instalacao.log') }
    } finally { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
    if (-not (Test-Path -LiteralPath (Join-Path $C.PgBin 'postgres.exe'))) { throw 'O PostgreSQL não ficou completo (falta o postgres.exe).' }
}

# O postgres.exe precisa do runtime do Visual C++, que NÃO faz parte do Windows.
function Garantir-Runtime-Vc($C) {
    $faltam = Faltam-DllsDoVc (Pasta-DllsDoSistema)
    if ($faltam.Count -eq 0) { Dizer 'Runtime do Visual C++ presente no Windows.'; return }
    Dizer "Este computador não tem o runtime do Visual C++ ($($faltam -join ', ')). Uso uma cópia local, sem precisar de administrador."
    if (-not (Garantir-Java $C)) {
        throw 'Não foi possível obter o runtime do Visual C++. Instale-o manualmente (https://aka.ms/vs/17/release/vc_redist.x64.exe) e rode este instalador de novo.'
    }
    $copiadas = Copiar-DllsDoVc (Join-Path $C.Jdk 'bin') @($C.PgBin, $C.Python)
    foreach ($c in $copiadas) { Dizer "  copiada: $c" }
}

function Inicializar-Cluster($C, $Seg, $Cfg) {
    $conf = Join-Path $C.Dados 'postgresql.conf'
    if (-not (Test-Path -LiteralPath (Join-Path $C.Dados 'PG_VERSION'))) {
        Dizer 'Criando o banco de dados...'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $C.Dados) | Out-Null
        $pw = Join-Path $C.Cache 'pg.pw'
        [IO.File]::WriteAllText($pw, $Seg.postgres_senha, $script:Utf8SemBom)
        Restringir-Arquivo $pw
        try {
            $r = Executar-Programa (Join-Path $C.PgBin 'initdb.exe') (Argumentos-Initdb $C.Dados $pw) -Capturar -TimeoutMs 300000
        } finally { Remove-Item -LiteralPath $pw -Force -ErrorAction SilentlyContinue }
        if ($r.Codigo -ne 0) { Falha-Com-Log 'A criação do banco de dados' $r (Join-Path $C.Logs 'instalacao.log') }
    }
    Configurar-Postgres $conf $Cfg.porta_pg
}

function Preparar-Banco($C, $Seg, $Cfg) {
    Iniciar-Postgres $C
    $amb = Ambiente-Admin $Seg $Cfg
    $r = Python-Nfse $C @('-m', 'app.local.preparar_banco') -Capturar -Ambiente $amb
    if ($r.Codigo -ne 0) { Falha-Com-Log 'A criação do banco' $r (Join-Path $C.Logs 'instalacao.log') }
    Dizer 'Aplicando a estrutura do banco...'
    $r = Python-Nfse $C @('-m', 'alembic', 'upgrade', 'head') -Capturar -Ambiente $amb
    if ($r.Codigo -ne 0) { Falha-Com-Log 'A estrutura do banco' $r (Join-Path $C.Logs 'instalacao.log') }
}

function Criar-Atalhos($C, $Java) {
    $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $comum = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File'
    $desktop = [Environment]::GetFolderPath('Desktop')
    $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'NFS-e'
    $itens = @(
        @{ Nome = 'NFS-e'; Arquivo = 'Abrir-NFSe.ps1'; Pastas = @($desktop, $menu) },
        @{ Nome = 'Parar o NFS-e'; Arquivo = 'Parar-NFSe.ps1'; Pastas = @($menu) },
        @{ Nome = 'Cópia de segurança do NFS-e'; Arquivo = 'Copia-de-seguranca.ps1'; Pastas = @($menu) },
        @{ Nome = 'Restaurar cópia do NFS-e'; Arquivo = 'Restaurar-copia.ps1'; Pastas = @($menu) },
        @{ Nome = 'Desinstalar o NFS-e'; Arquivo = 'Desinstalar-NFSe.ps1'; Pastas = @($menu) }
    )
    $criados = 0
    foreach ($i in $itens) {
        foreach ($pasta in $i.Pastas) {
            $alvo = Join-Path $C.Bin $i.Arquivo
            if (Criar-Atalho (Join-Path $pasta "$($i.Nome).lnk") $ps "$comum `"$alvo`"" $C.Bin) { $criados++ }
        }
    }
    if ($Java) {
        $args = "-cp `"$(Join-Path $C.Agente 'classes')`" ProvarHandshakeMTLSGui"
        foreach ($pasta in @($desktop, $menu)) { if (Criar-Atalho (Join-Path $pasta 'Teste de certificado NFS-e.lnk') $Java.Javaw $args $C.Agente) { $criados++ } }
    }
    return $criados
}

function Principal {
    $base = if ($env:NFSE_BASE) { $env:NFSE_BASE } else { Base-Padrao }
    $C = Caminhos-Nfse $base
    foreach ($d in @($C.Logs, $C.Cache, $C.Config)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
    $script:ArquivoLog = Join-Path $C.Logs 'instalacao.log'
    Dizer ("=== Instalação do NFS-e em {0:dd/MM/yyyy HH:mm} ===" -f (Get-Date))

    $problemas = Problemas-De-Requisitos $base
    if ($problemas.Count -gt 0) { throw ($problemas -join "`n") }
    $instalador = $env:NFSE_INSTALADOR
    if (-not $instalador -or -not (Test-Path -LiteralPath $instalador)) {
        throw 'Não foi possível localizar o instalador. Abra o arquivo Instalar-NFSe.bat diretamente.'
    }

    Dizer '1/7 Preparando o código do sistema...'
    Instalar-Codigo $C $instalador
    $pins = Ler-Pins (Join-Path $C.Codigo 'app\instalador\pins.json')
    $versoes = Ler-Json (Join-Path $C.Config 'versoes.json')

    Dizer '2/7 Python...'
    $whl = Instalar-Python $C $pins $versoes
    $hashLock = Instalar-Dependencias $C $whl $versoes

    Dizer '3/7 Banco de dados (PostgreSQL)...'
    Instalar-Postgres $C $pins $versoes
    Garantir-Runtime-Vc $C

    Dizer '4/7 Senhas e portas...'
    $seg = Garantir-Segredos (Join-Path $C.Config 'segredos.json')
    $cfg = Garantir-Config (Join-Path $C.Config 'config.json')
    Inicializar-Cluster $C $seg $cfg

    Dizer '5/7 Iniciando e preparando o banco...'
    Preparar-Banco $C $seg $cfg

    Dizer '6/7 Iniciando o sistema...'
    Iniciar-Api $C $seg $cfg
    if (-not (Esperar-Api $cfg.porta_api 90)) {
        throw "O sistema não respondeu a tempo. Veja $(Join-Path $C.Logs 'api-erro.log')."
    }

    Salvar-Json (Join-Path $C.Config 'versoes.json') ([pscustomobject]@{
        python = $pins.python.versao; pip = $pins.pip.versao; postgres = $pins.postgres.versao; lock_sha256 = $hashLock })

    Dizer '7/7 Teste de certificado e atalhos...'
    $java = $null
    try {
        $java = Garantir-Java $C
        if ($java) { Compilar $java.Javac $C.Agente }
    } catch {
        Dizer "  O teste de certificado não pôde ser instalado ($($_.Exception.Message)). O resto do sistema está funcionando."
        $java = $null
    }
    $n = Criar-Atalhos $C $java
    Dizer "  $n atalho(s) criado(s) (Área de Trabalho e Menu Iniciar)."

    $url = Url-Inicial $C $seg $cfg
    Dizer ''
    Dizer 'Pronto! Abrindo o NFS-e no navegador...'
    Dizer "  $url"
    Start-Process $url
}

if ($env:NFSE_SOMENTE_FUNCOES -ne '1' -and $MyInvocation.InvocationName -ne '.') {
    try { Principal }
    catch {
        Write-Host ''
        Write-Host "Não foi possível concluir a instalação:`n$($_.Exception.Message)"
        if ($script:ArquivoLog) { Write-Host "`nO registro completo está em $script:ArquivoLog. Envie esse arquivo para quem cuida do sistema." }
        exit 1
    }
}
