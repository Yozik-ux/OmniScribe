; OmniScribe — NSIS-скрипт інсталятора для Windows.
; Збирається через: makensis packaging\windows\installer.nsi
; Очікує, що PyInstaller уже поклав зібраний застосунок у dist\OmniScribe\
; (packaging\windows\build.bat або CI-крок windows робить це перед цим кроком).

!ifndef VERSION
  !define VERSION "0.1.0"
!endif

!include "MUI2.nsh"

Name "OmniScribe"
OutFile "..\..\dist\OmniScribe-Setup-${VERSION}.exe"
InstallDir "$PROGRAMFILES64\OmniScribe"
InstallDirRegKey HKCU "Software\OmniScribe" "InstallDir"
RequestExecutionLevel admin
Unicode true

!define MUI_ABORTWARNING

!if /FileExists "..\..\assets\logo.ico"
  !define MUI_ICON "..\..\assets\logo.ico"
  !define MUI_UNICON "..\..\assets\logo.ico"
!endif

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Ukrainian"
!insertmacro MUI_LANGUAGE "English"

Section "OmniScribe" SecMain
  SetOutPath "$INSTDIR"
  File /r "..\..\dist\OmniScribe\*.*"

  WriteRegStr HKCU "Software\OmniScribe" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\OmniScribe"
  CreateShortCut "$SMPROGRAMS\OmniScribe\OmniScribe.lnk" "$INSTDIR\OmniScribe.exe"
  CreateShortCut "$SMPROGRAMS\OmniScribe\Видалити OmniScribe.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortCut "$DESKTOP\OmniScribe.lnk" "$INSTDIR\OmniScribe.exe"

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OmniScribe" \
    "DisplayName" "OmniScribe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OmniScribe" \
    "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OmniScribe" \
    "DisplayVersion" "${VERSION}"
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\OmniScribe\OmniScribe.lnk"
  Delete "$SMPROGRAMS\OmniScribe\Видалити OmniScribe.lnk"
  RMDir "$SMPROGRAMS\OmniScribe"
  Delete "$DESKTOP\OmniScribe.lnk"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OmniScribe"
  DeleteRegKey HKCU "Software\OmniScribe"
SectionEnd
