# Restaura uma cópia de segurança. O que existia antes NÃO é apagado: fica ao lado, com o
# nome pg.antes-<data>, para dar para voltar se a cópia escolhida estiver errada.
$ErrorActionPreference = 'Stop'
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $aqui 'lib_windows.ps1'); . (Join-Path $aqui 'comum_nfse.ps1')
try {
    Add-Type -AssemblyName System.Windows.Forms
    $C = Caminhos-Nfse (Split-Path -Parent $aqui)
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = 'Escolha a cópia de segurança do NFS-e'
    $dlg.Filter = 'Cópia do NFS-e (*.zip)|*.zip'
    $dlg.InitialDirectory = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'NFSe-copias'
    if ($dlg.ShowDialog() -ne 'OK') { exit 0 }
    $ok = [System.Windows.Forms.MessageBox]::Show("Restaurar esta cópia?`n`n$($dlg.FileName)`n`nOs dados atuais serão guardados ao lado, não apagados.", 'NFS-e', 'YesNo', 'Question')
    if ($ok -ne 'Yes') { exit 0 }
    Restaurar-Copia $C $dlg.FileName
    $estado = Ligar-Sistema $C
    [void][System.Windows.Forms.MessageBox]::Show('Cópia restaurada. O NFS-e foi ligado de novo.', 'NFS-e')
    Start-Process "http://localhost:$($estado.Config.porta_api)/"
} catch { Mostrar-Erro "Não foi possível restaurar a cópia.`n`n$($_.Exception.Message)"; exit 1 }
