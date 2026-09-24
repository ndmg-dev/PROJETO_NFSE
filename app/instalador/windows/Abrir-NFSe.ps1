# Atalho "NFS-e": liga o que estiver desligado (banco e sistema) e abre o navegador.
$ErrorActionPreference = 'Stop'
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $aqui 'lib_windows.ps1'); . (Join-Path $aqui 'comum_nfse.ps1')
try {
    $C = Caminhos-Nfse (Split-Path -Parent $aqui)
    $script:ArquivoLog = Join-Path $C.Logs 'uso.log'
    $estado = Ligar-Sistema $C
    Start-Process (Url-Inicial $C $estado.Segredos $estado.Config)
} catch {
    Mostrar-Erro "Não foi possível abrir o NFS-e.`n`n$($_.Exception.Message)"
    exit 1
}
