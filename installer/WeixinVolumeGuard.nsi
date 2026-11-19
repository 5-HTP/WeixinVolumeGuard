Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!include "FileFunc.nsh"

!ifndef PAYLOAD
 !error "Pass /DPAYLOAD=<published app directory>"
!endif
!ifndef OUTPUT
 !define OUTPUT "WeixinVolumeGuard-Setup-0.1.0-x64.exe"
!endif

Name "微信防降音助手"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\WeixinVolumeGuard"
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show
!define MUI_ABORTWARNING
!define MUI_ICON "..\src\Guard.App\Assets\App.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Var OldInstall
Var OldStartup
Var HadProduct
Var BackupDir

Function .onInit
 SetShellVarContext current
 SetRegView 64
 ${IfNot} ${RunningX64}
  MessageBox MB_ICONSTOP "首版仅支持 Windows x64。"
  Abort
 ${EndIf}
 ${IfNot} ${AtLeastWin10}
  MessageBox MB_ICONSTOP "需要 Windows 10 或更新版本；当前正式实测范围请参阅兼容说明。"
  Abort
 ${EndIf}
 ReadRegStr $OldInstall HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard" "InstallLocation"
 ReadRegStr $OldStartup HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WeixinVolumeGuard"
FunctionEnd

Function .onVerifyInstDir
 ${If} $INSTDIR == ""
  Abort
 ${EndIf}
 ${GetRoot} "$INSTDIR" $0
 ${If} $INSTDIR == $0
  Abort
 ${EndIf}
 ${If} $INSTDIR == "$WINDIR"
  Abort
 ${EndIf}
 ${If} $INSTDIR == "$PROGRAMFILES"
  Abort
 ${EndIf}
FunctionEnd

Section "安装" SEC_MAIN
 SetShellVarContext current
 SetRegView 64
 StrCpy $HadProduct "0"
 IfFileExists "$INSTDIR\product-install.ini" 0 checkExisting
 ReadINIStr $0 "$INSTDIR\product-install.ini" "Product" "Id"
 StrCmp $0 "WeixinVolumeGuard" 0 invalidDirectory
 StrCpy $HadProduct "1"
 Goto shutdownOld
 checkExisting:
 IfFileExists "$INSTDIR\*.*" invalidDirectory shutdownOld
 invalidDirectory:
 MessageBox MB_ICONSTOP "该目录含有不属于本产品的内容，请选择一个空目录或本产品安装目录。"
 Abort
 shutdownOld:
 IfFileExists "$OldInstall\WeixinVolumeGuard.exe" 0 shutdownHere
 ReadINIStr $0 "$OldInstall\product-install.ini" "Product" "Id"
 StrCmp $0 "WeixinVolumeGuard" 0 shutdownHere
 ExecWait '"$OldInstall\WeixinVolumeGuard.exe" --shutdown' $0
 StrCmp $0 0 shutdownHere
 MessageBox MB_ICONSTOP "旧程序未确认安全退出。请在程序中退出后重试安装。"
 Abort
 shutdownHere:
 IfFileExists "$INSTDIR\WeixinVolumeGuard.exe" 0 backup
 ExecWait '"$INSTDIR\WeixinVolumeGuard.exe" --shutdown' $0
 StrCmp $0 0 backup
 MessageBox MB_ICONSTOP "程序未确认安全退出，请退出后重试。"
 Abort
 backup:
 ${If} $HadProduct == "1"
  ${GetTime} "" "L" $0 $1 $2 $3 $4 $5 $6
  StrCpy $BackupDir "$INSTDIR.previous-$2$1$0-$4$5$6"
  IfFileExists "$BackupDir\*.*" backupExists 0
  CreateDirectory "$BackupDir"
  ClearErrors
  CopyFiles /SILENT "$INSTDIR\*.*" "$BackupDir"
  IfErrors backupFailed copyNew
  backupExists:
  MessageBox MB_ICONSTOP "本次升级备份目录已存在，请稍后重试。"
  Abort
  backupFailed:
  MessageBox MB_ICONSTOP "无法备份旧文件，安装已停止。"
  Abort
 ${EndIf}
 copyNew:
 SetOutPath "$INSTDIR"
 ClearErrors
 File /r "${PAYLOAD}\*.*"
 IfErrors installFailed 0
 WriteINIStr "$INSTDIR\product-install.ini" "Product" "Id" "WeixinVolumeGuard"
 WriteINIStr "$INSTDIR\product-install.ini" "Product" "Version" "0.1.0"
 WriteUninstaller "$INSTDIR\Uninstall.exe"
 CreateDirectory "$SMPROGRAMS\微信防降音助手"
 CreateShortcut "$SMPROGRAMS\微信防降音助手\微信防降音助手.lnk" "$INSTDIR\WeixinVolumeGuard.exe"
 CreateShortcut "$SMPROGRAMS\微信防降音助手\卸载.lnk" "$INSTDIR\Uninstall.exe"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard" "DisplayName" "微信防降音助手"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard" "DisplayVersion" "0.1.0"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard" "InstallLocation" "$INSTDIR"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard" "UninstallString" '"$INSTDIR\Uninstall.exe"'
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard" "NoModify" 1
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard" "NoRepair" 1
 StrCmp $OldStartup '"$OldInstall\WeixinVolumeGuard.exe" --background' 0 done
 StrCmp $OldInstall "" done
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WeixinVolumeGuard" '"$INSTDIR\WeixinVolumeGuard.exe" --background'
 Goto done
 installFailed:
 MessageBox MB_ICONSTOP "安装文件失败。旧文件备份（若存在）位于 $BackupDir，未报告安装成功。"
 SetErrorLevel 2
 Abort
 done:
SectionEnd

Function un.onInit
 SetShellVarContext current
 SetRegView 64
 ReadINIStr $0 "$INSTDIR\product-install.ini" "Product" "Id"
 StrCmp $0 "WeixinVolumeGuard" valid
 MessageBox MB_ICONSTOP "无法确认安装目录，本次不删除文件。"
 Abort
 valid:
FunctionEnd

Section "Uninstall"
 ExecWait '"$INSTDIR\WeixinVolumeGuard.exe" --shutdown' $0
 StrCmp $0 0 cleanup
 MessageBox MB_ICONSTOP "程序未确认安全停用，请先在程序中退出，再重试卸载。"
 Abort
 cleanup:
 ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WeixinVolumeGuard"
 StrCmp $0 '"$INSTDIR\WeixinVolumeGuard.exe" --background' 0 shortcuts
 DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WeixinVolumeGuard"
 shortcuts:
 Delete "$SMPROGRAMS\微信防降音助手\微信防降音助手.lnk"
 Delete "$SMPROGRAMS\微信防降音助手\卸载.lnk"
 RMDir "$SMPROGRAMS\微信防降音助手"
 DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard"
 !include "${PAYLOAD}\uninstall-files.nsh"
 Delete "$INSTDIR\product-install.ini"
 Delete "$INSTDIR\Uninstall.exe"
 RMDir "$INSTDIR"
 IfSilent keepData
 MessageBox MB_YESNO|MB_DEFBUTTON2 "是否同时移除个人设置和日志？" IDNO keepData
 Delete "$LOCALAPPDATA\WeixinVolumeGuard\settings.json"
 Delete "$LOCALAPPDATA\WeixinVolumeGuard\settings.json.bak"
 Delete "$LOCALAPPDATA\WeixinVolumeGuard\settings.json.invalid-*"
 Delete "$LOCALAPPDATA\WeixinVolumeGuard\Logs\app.log*"
 Delete "$LOCALAPPDATA\WeixinVolumeGuard\Logs\engine.log*"
 RMDir "$LOCALAPPDATA\WeixinVolumeGuard\Logs"
 RMDir "$LOCALAPPDATA\WeixinVolumeGuard"
 keepData:
SectionEnd
