# ECOQUILLA Installer Build

## Requisitos

- Inno Setup 6 instalado
- Ejecutable ya generado en `dist\ECOQUILLA.exe`
- Icono disponible en `ecoquilla.ico`

## Archivos de packaging

- `ECOQUILLA.iss`
- `build_installer.ps1`

## Compilar el instalador

Desde PowerShell, en la raíz del proyecto:

```powershell
powershell -ExecutionPolicy Bypass -File ".\build_installer.ps1"
```

Si `ISCC.exe` no está en una ruta estándar, puedes pasar la ruta manualmente:

```powershell
powershell -ExecutionPolicy Bypass -File ".\build_installer.ps1" -IsccPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

## Resultado esperado

El instalador final quedará en:

```text
installer\ECOQUILLA_Setup.exe
```

## Qué incluye

- Instalación en `Program Files\ECOQUILLA`
- Acceso directo en menú Inicio
- Acceso directo opcional en escritorio
- Acceso a desinstalación desde menú Inicio
- Icono `ecoquilla.ico`
