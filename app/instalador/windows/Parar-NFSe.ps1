# Desliga o sistema e o banco (sem apagar nada). Abrir o atalho "NFS-e" liga de novo.
$ErrorActionPreference = 'Stop'
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $aqui 'lib_windows.ps1'); . (Join-Path $aqui 'comum_nfse.ps1')
try {
    $C = Caminhos-Nfse (Split-Path -Parent $aqui)
    Parar-Api $C
    Parar-Postgres $C
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show('O NFS-e foi desligado. Para usar de novo, abra o atalho "NFS-e".', 'NFS-e')
} catch { Mostrar-Erro "Não foi possível desligar o NFS-e.`n`n$($_.Exception.Message)"; exit 1 }
