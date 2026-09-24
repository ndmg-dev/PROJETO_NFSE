# Roda os dois conjuntos de testes do Windows e soma os códigos de saída.
$codigo = 0
foreach ($teste in 'iniciar.tests.ps1', 'agente.tests.ps1') {
    & (Join-Path $PSScriptRoot $teste)
    $codigo += $LASTEXITCODE
}
exit $codigo
