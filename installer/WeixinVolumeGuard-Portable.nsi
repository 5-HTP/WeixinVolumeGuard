Unicode true
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!ifndef PAYLOAD
 !error "Pass /DPAYLOAD=<published app directory>"
!endif
!ifndef OUTPUT
 !error "Pass /DOUTPUT=<portable executable>"
!endif

Name "微信防降音助手 免安装版"
OutFile "${OUTPUT}"
Icon "..\src\Guard.App\Assets\App.ico"
RequestExecutionLevel user
SilentInstall silent
SetCompressor /SOLID lzma

Section
 ${IfNot} ${IsNativeAMD64}
 ${OrIfNot} ${AtLeastWin10}
  MessageBox MB_ICONSTOP "需要 Windows 10 或更新的 x64 系统。"
  SetErrorLevel 2
  Quit
 ${EndIf}
 InitPluginsDir
 SetOutPath "$PLUGINSDIR\WeixinVolumeGuard"
 ClearErrors
 File /r /x "uninstall-files.nsh" /x "*.pdb" "${PAYLOAD}\*"
 ${If} ${Errors}
  MessageBox MB_ICONSTOP "无法解包，请检查临时目录的权限和可用空间。"
  SetErrorLevel 2
  Quit
 ${EndIf}
 ClearErrors
 WriteINIStr "$OUTDIR\portable-mode.ini" "Product" "Mode" "Portable"
 ${If} ${Errors}
  MessageBox MB_ICONSTOP "无法初始化免安装版。"
  SetErrorLevel 2
  Quit
 ${EndIf}
 ExecWait '"$OUTDIR\WeixinVolumeGuard.exe"' $0
 ${If} ${Errors}
  MessageBox MB_ICONSTOP "无法启动微信防降音助手。"
  SetErrorLevel 2
 ${Else}
  SetErrorLevel $0
 ${EndIf}
 SetOutPath "$TEMP"
SectionEnd
