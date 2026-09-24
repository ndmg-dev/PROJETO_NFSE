# Remove o NFS-e deste computador. ANTES, salva uma cópia de segurança em
# Documentos\NFSe-copias, para os dados não se perderem por engano.
$ErrorActionPreference = 'Stop'
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $aqui 'lib_windows.ps1'); . (Join-Path $aqui 'comum_nfse.ps1')
try {
    Add-Type -AssemblyName System.Windows.Forms
    $C = Caminhos-Nfse (Split-Path -Parent $aqui)
    $ok = [System.Windows.Forms.MessageBox]::Show("Remover o NFS-e deste computador?`n`nUma cópia de segurança dos seus dados será salva em Documentos\NFSe-copias antes.", 'NFS-e', 'YesNo', 'Warning')
    if ($ok -ne 'Yes') { exit 0 }
    $copia = $null
    if (Test-Path -LiteralPath $C.Dados) { $copia = Fazer-Copia $C (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'NFSe-copias') }
    Parar-Api $C; Parar-Postgres $C
    Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Programs')) 'NFS-e') -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'NFS-e.lnk') -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Teste de certificado NFS-e.lnk') -Force -ErrorAction SilentlyContinue
    # Este script roda de dentro da pasta que vai ser apagada: a remoção é feita por um cmd
    # separado, depois de uma pausa, quando este processo já terminou.
    $apagar = 'ping -n 4 127.0.0.1 > nul & rmdir /s /q "' + $C.Base + '"'
    Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', $apagar) -WindowStyle Hidden
    $msg = 'O NFS-e foi removido.'
    if ($copia) { $msg += "`n`nSeus dados estão na cópia:`n$($copia.Arquivo)" }
    [void][System.Windows.Forms.MessageBox]::Show($msg, 'NFS-e')
} catch { Mostrar-Erro "Não foi possível desinstalar.`n`n$($_.Exception.Message)"; exit 1 }
