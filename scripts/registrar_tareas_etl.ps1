<#
.SYNOPSIS
    Crea (o deshabilita) en el Programador de tareas las tareas ETL que dependen del
    servidor 172.17.0.162.

.DESCRIPTION
    Las tareas se crean en la carpeta \ETL\ con los mismos horarios, acciones y limites
    de ejecucion que tenian en el equipo original. Todos los horarios son de lunes a
    viernes, salvo "ETL Seguimiento Mantener Indice" (primer lunes de cada mes).

    Las tareas que NO dependen del servidor (ETL Bot Salesforce SharePoint y
    ETL Trafico 01 Servidor Chile) no se incluyen.

.PARAMETER BasePath
    Carpeta donde se clono BPO_CHILE en el equipo nuevo.

.PARAMETER PythonExe
    python.exe del equipo nuevo. Lo usan directamente las tareas "ETL Trafico ..."; los
    .cmd de las demas tareas traen escrita la ruta del equipo original (ver
    -ActualizarPython).

.PARAMETER RunAsUser
    Cuenta con la que correran las tareas (por defecto, el usuario que ejecuta el script).

.PARAMETER PedirPassword
    Pide la contrasena de RunAsUser y registra las tareas con "Ejecutar tanto si el
    usuario inicio sesion como si no". Sin este modo, las tareas solo corren con la
    sesion de RunAsUser abierta.

.PARAMETER ActualizarPython
    Reemplaza, en los .cmd de BasePath, la ruta de python.exe del equipo original por
    PythonExe.

.PARAMETER Reemplazar
    Sobrescribe las tareas que ya existan. Sin esta opcion se omiten.

.PARAMETER SoloDeshabilitar
    No crea nada: deshabilita las tareas de esta lista que existan en TaskPath (para
    usarlo en el equipo original).

.EXAMPLE
    .\registrar_tareas_etl.ps1 -BasePath 'E:\BPO_CHILE' -PythonExe 'C:\Python312\python.exe' `
        -RunAsUser 'DOMINIO\svc_etl' -PedirPassword -ActualizarPython -WhatIf

.EXAMPLE
    .\registrar_tareas_etl.ps1 -SoloDeshabilitar
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$BasePath = 'D:\dev\BPO_CHILE',
    [string]$PythonExe = 'C:\Users\miguel.paredes\AppData\Local\Programs\Python\Python312\python.exe',
    [string]$TaskPath = '\ETL\',
    [string]$RunAsUser = "$env:USERDOMAIN\$env:USERNAME",
    [switch]$PedirPassword,
    [switch]$ActualizarPython,
    [switch]$Reemplazar,
    [switch]$SoloDeshabilitar
)

$ErrorActionPreference = 'Stop'
$PythonOriginal = 'C:\Users\miguel.paredes\AppData\Local\Programs\Python\Python312\python.exe'
$BasePath = $BasePath.TrimEnd('\')
if (-not $TaskPath.EndsWith('\')) { $TaskPath += '\' }
$termometro = '10_campa' + [char]0x00F1 + 'a_termometro'   # carpeta con enie, sin acentos en este archivo

# Tipo: Cmd = cmd.exe /c call "<Base>\<Script>"  |  Py = python.exe main.py en la carpeta del proyecto
# Horas = inicios (L-V). Intervalo/Duracion = repeticion desde la primera hora. Limite = tiempo maximo.
$tareas = @(
    @{ Nombre='ETL Correos Chile';                       Tipo='Cmd'; Script='11_correos\scripts\ejecutar_correos.cmd';                          Dir='11_correos';                 Horas=@('06:30','12:30'); Limite='PT1H'  }
    @{ Nombre='ETL Volumetria Gerencia';                 Tipo='Cmd'; Script='16_Gerencia\scripts\ejecutar_gerencia.cmd';                         Dir='16_Gerencia';                Horas=@('06:40'); Intervalo='PT3H';    Duracion='PT10H20M'; Limite='PT0S' }
    @{ Nombre='ETL Historial Contactos';                 Tipo='Cmd'; Script='06_sf_historial_contactos\scripts\ejecutar_historial_contactos.cmd'; Dir='';                         Horas=@('06:45'); Intervalo='PT1H30M'; Duracion='PT9H';     Limite='PT4H' }
    @{ Nombre='ETL SF Descripcion';                      Tipo='Cmd'; Script='07_sf_descripcion\scripts\ejecutar_descripcion.cmd';                 Dir='';                         Horas=@('06:45'); Intervalo='PT1H30M'; Duracion='PT9H';     Limite='PT4H' }
    @{ Nombre='ETL Seguimiento Chile';                   Tipo='Cmd'; Script='17_seguimiento\scripts\ejecutar_seguimiento.cmd';                   Dir='17_seguimiento';             Horas=@('07:00'); Intervalo='PT3H';    Duracion='PT9H30M';  Limite='PT0S' }
    @{ Nombre='ETL_Ventas_Senalizaciones_Chile';         Tipo='Cmd'; Script='02_ventas\scripts\ejecutar_ventas.cmd';                              Dir='02_ventas';                  Horas=@('07:00'); Intervalo='PT3H';    Duracion='PT9H15M';  Limite='PT1H' }
    @{ Nombre='ETL Campana Termometro';                  Tipo='Cmd'; Script="$termometro\scripts\ejecutar_termometro.cmd";                        Dir='';                         Horas=@('07:15'); Intervalo='PT1H30M'; Duracion='PT9H';     Limite='PT4H' }
    @{ Nombre='ETL Puntualidad Chile';                   Tipo='Cmd'; Script='18_puntualidad\scripts\ejecutar_puntualidad.cmd'; ArgsExtra=' --destino produccion'; Dir='18_puntualidad'; Horas=@('07:15'); Intervalo='PT3H'; Duracion='PT9H30M'; Limite='PT0S' }
    @{ Nombre='ETL Trafico 12 Trafico';                  Tipo='Py';  Dir='12_trafico';                Horas=@('10:40'); Limite='PT2H' }
    @{ Nombre='ETL Trafico 13 FCR';                      Tipo='Py';  Dir='13_fcr';                    Horas=@('10:45'); Limite='PT2H' }
    @{ Nombre='ETL Trafico 14 EPA WSP';                  Tipo='Py';  Dir='14_EPA_WSP';                Horas=@('10:50'); Limite='PT2H' }
    @{ Nombre='ETL Trafico 04 Usuarios y Retenciones';   Tipo='Py';  Dir='04_usuarios_y_retenciones'; Horas=@('11:00'); Limite='PT2H' }
    @{ Nombre='ETL Logueo Chile';                        Tipo='Cmd'; Script='15_Logueo\scripts\ejecutar_con_bot_portal.cmd';                      Dir='15_Logueo';                  Horas=@('11:45'); Limite='PT0S' }
    @{ Nombre='ETL Seguimiento Mantener Indice';         Tipo='Cmd'; Script='17_seguimiento\scripts\mantener_indice.cmd';                         Dir='17_seguimiento';             Horas=@('06:00'); Mensual=$true; Limite='PT72H' }
)

function Esc([string]$s) { [Security.SecurityElement]::Escape($s) }

function New-TaskXml($t, [string]$user, [string]$logonType) {
    if ($t.Tipo -eq 'Py') {
        $cmd = $PythonExe
        $argumentos = 'main.py'
    } else {
        $cmd = 'cmd.exe'
        $argumentos = '/c call "' + "$BasePath\$($t.Script)" + '"' + $t.ArgsExtra
    }
    $dir = if ($t.Dir) { "$BasePath\$($t.Dir)" } else { '' }

    $repeticion = ''
    if ($t.Intervalo) {
        $repeticion = "<Repetition><Interval>$($t.Intervalo)</Interval><Duration>$($t.Duracion)</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>"
    }
    $disparadores = foreach ($h in $t.Horas) {
        if ($t.Mensual) {
            $meses = ('January','February','March','April','May','June','July','August','September','October','November','December' | ForEach-Object { "<$_ />" }) -join ''
            "<CalendarTrigger><StartBoundary>2026-01-01T${h}:00</StartBoundary><Enabled>true</Enabled><ScheduleByMonthDayOfWeek><Weeks><Week>1</Week></Weeks><DaysOfWeek><Monday /></DaysOfWeek><Months>$meses</Months></ScheduleByMonthDayOfWeek></CalendarTrigger>"
        } else {
            "<CalendarTrigger><StartBoundary>2026-01-01T${h}:00</StartBoundary>$repeticion<Enabled>true</Enabled><ScheduleByWeek><DaysOfWeek><Monday /><Tuesday /><Wednesday /><Thursday /><Friday /></DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek></CalendarTrigger>"
        }
    }
    $workDir = if ($dir) { "<WorkingDirectory>$(Esc $dir)</WorkingDirectory>" } else { '' }
    $desc = if ($t.Tipo -eq 'Py') { "Proyecto $($t.Dir)" } else { "Ejecuta $($t.Script)" }

    @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>$(Esc $desc)</Description></RegistrationInfo>
  <Principals><Principal id="Author"><UserId>$(Esc $user)</UserId><LogonType>$logonType</LogonType></Principal></Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>$($t.Limite)</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Enabled>true</Enabled>
  </Settings>
  <Triggers>$($disparadores -join '')</Triggers>
  <Actions Context="Author"><Exec><Command>$(Esc $cmd)</Command><Arguments>$(Esc $argumentos)</Arguments>$workDir</Exec></Actions>
</Task>
"@
}

# --- Solo deshabilitar (equipo original) ---------------------------------------------
if ($SoloDeshabilitar) {
    foreach ($t in $tareas) {
        $x = Get-ScheduledTask -TaskPath $TaskPath -TaskName $t.Nombre -ErrorAction SilentlyContinue
        if (-not $x) { Write-Host "[no existe]   $($t.Nombre)"; continue }
        if ($PSCmdlet.ShouldProcess($t.Nombre, 'Deshabilitar')) {
            Disable-ScheduledTask -TaskPath $TaskPath -TaskName $t.Nombre | Out-Null
            Write-Host "[deshabilitada] $($t.Nombre)"
        }
    }
    return
}

# --- Validaciones --------------------------------------------------------------------
if (-not (Test-Path $BasePath)) { throw "No existe BasePath: $BasePath" }
if (-not (Test-Path $PythonExe)) { Write-Warning "No existe PythonExe: $PythonExe (las tareas ETL Trafico fallaran hasta corregirlo)" }

$password = $null
$logonType = 'InteractiveToken'
if ($PedirPassword) {
    $cred = Get-Credential -UserName $RunAsUser -Message 'Cuenta con la que correran las tareas ETL'
    $RunAsUser = $cred.UserName
    $password = $cred.GetNetworkCredential().Password
    $logonType = 'Password'
}

# --- Ruta de python.exe dentro de los .cmd -------------------------------------------
if ($ActualizarPython) {
    Get-ChildItem $BasePath -Recurse -Filter *.cmd -File |
        Where-Object { $_.FullName -notmatch '\\(\.venv|venv|node_modules)\\' } |
        ForEach-Object {
            $txt = [IO.File]::ReadAllText($_.FullName)
            if ($txt.Contains($PythonOriginal) -and $PSCmdlet.ShouldProcess($_.FullName, "Cambiar ruta de python.exe por $PythonExe")) {
                [IO.File]::WriteAllText($_.FullName, $txt.Replace($PythonOriginal, $PythonExe), (New-Object Text.UTF8Encoding($false)))
                Write-Host "[python actualizado] $($_.FullName)"
            }
        }
}

# --- Registro de tareas --------------------------------------------------------------
foreach ($t in $tareas) {
    $faltan = @()
    if ($t.Tipo -eq 'Cmd' -and -not (Test-Path "$BasePath\$($t.Script)")) { $faltan += "$BasePath\$($t.Script)" }
    if ($t.Tipo -eq 'Py'  -and -not (Test-Path "$BasePath\$($t.Dir)\main.py")) { $faltan += "$BasePath\$($t.Dir)\main.py" }
    if ($faltan) { Write-Warning "$($t.Nombre): no existe $($faltan -join ', ') (se registra igual)" }

    $existe = Get-ScheduledTask -TaskPath $TaskPath -TaskName $t.Nombre -ErrorAction SilentlyContinue
    if ($existe -and -not $Reemplazar) { Write-Host "[ya existe, se omite] $($t.Nombre)"; continue }

    $xml = New-TaskXml $t $RunAsUser $logonType
    if ($PSCmdlet.ShouldProcess("$TaskPath$($t.Nombre)", 'Registrar tarea')) {
        $p = @{ TaskPath = $TaskPath; TaskName = $t.Nombre; Xml = $xml; Force = $true }
        if ($password) { $p.User = $RunAsUser; $p.Password = $password }
        Register-ScheduledTask @p | Out-Null
        Write-Host "[registrada] $($t.Nombre)  ($($t.Horas -join ', ')$(if ($t.Intervalo) { " cada $($t.Intervalo)" }))"
    }
}

Write-Host ''
Get-ScheduledTask -TaskPath $TaskPath | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    '{0,-42} {1,-9} proxima: {2}' -f $_.TaskName, $_.State, $i.NextRunTime
}
