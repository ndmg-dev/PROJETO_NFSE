# Cópia de segurança dos dados (empresas, notas, usuários) em Documentos\NFSe-copias.
# É uma cópia a frio: o sistema é desligado por alguns segundos e volta sozinho.
# O arquivo leva também as senhas (sem elas o banco restaurado ficaria inacessível):
# guarde-o em lugar seguro.
$ErrorActionPreference = 'Stop'
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $aqui 'lib_windows.ps1'); . (Join-Path $aqui 'comum_nfse.ps1')
try {
    $C = Caminhos-Nfse (Split-Path -Parent $aqui)
    $pasta = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'NFSe-copias'
    $copia = Fazer-Copia $C $pasta
    if ($copia.EstavaLigado) { [void](Ligar-Sistema $C) }
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show("Cópia salva em:`n$($copia.Arquivo)`n`nO arquivo contém as senhas do sistema: guarde-o em lugar seguro.", 'NFS-e')
} catch { Mostrar-Erro "Não foi possível fazer a cópia.`n`n$($_.Exception.Message)"; exit 1 }
