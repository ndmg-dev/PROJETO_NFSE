# Instalador da ferramenta de teste de certificado (versão de validação do agente).
#
# NÃO é para executar direto: este texto é embutido no Instalar-Agente-NFSe.bat, que o
# servidor gera em /instalar, depois da biblioteca lib_windows.ps1. Compatível com o
# Windows PowerShell 5.1.
#
# O que faz, sem perguntar nada:
#   1. extrai os fontes (que vêm dentro do próprio .bat) para %LOCALAPPDATA%\nfse-agente;
#   2. acha um Java 17+ ou, se não houver, baixa uma cópia portátil da Adoptium e
#      confere o SHA-256 antes de usá-la;
#   3. compila, cria um atalho na Área de Trabalho e abre a janela do teste.
# Nada é instalado no sistema e não pede permissão de administrador.

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

    $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Teste de certificado NFS-e.lnk'
    if (Criar-Atalho $lnk $java.Javaw "-cp `"$app\classes`" ProvarHandshakeMTLSGui" $app) {
        Dizer 'Atalho criado na Área de Trabalho: "Teste de certificado NFS-e".'
    }
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
