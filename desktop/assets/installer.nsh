!macro customUnInstall
  ; Remove this app's optional login entry while retaining all user data.
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "GoogleUnlimited"
!macroend
