@echo off
title Google Unlimited Photos Auto-Sync
cd /d "%~dp0"

set "PS_CMD=powershell.exe -NoProfile -ExecutionPolicy Bypass"
where pwsh.exe >nul 2>&1
if %ERRORLEVEL% equ 0 set "PS_CMD=pwsh.exe -NoProfile -ExecutionPolicy Bypass"

set "IS_MENU=0"
if "%~1"=="" (
    set "IS_MENU=1"
    goto menu
) else (
    goto handle_arg
)

:menu
cls
echo ==========================================================
echo   *  Google Unlimited Photos Auto-Sync (Windows)
echo ==========================================================
echo   [1] Start Live Watcher (Interactive progress)
echo   [2] Start Background Watcher (Silent, zero window)
echo   [3] Check Backup Status
echo   [4] View Activity Logs
echo   [5] Enable Auto-Start on Windows Boot
echo   [6] Disable Auto-Start on Windows Boot
echo   [7] Stop Background Watcher
echo   [8] Manage Watched Folders (Add/List custom folders)
echo   [9] Manage Google Accounts (List/Switch account)
echo   [10] Force Re-scan ^& Sync All Media
echo   [0] Exit
echo ==========================================================
set "choice="
set /p "choice=Select an option [1-10, Default: 1]: "
if "%choice%"=="" set "choice=1"
if "%choice%"=="1" goto run_watcher
if "%choice%"=="2" goto run_silent
if "%choice%"=="3" goto check_status
if "%choice%"=="4" goto view_logs
if "%choice%"=="5" goto enable_startup
if "%choice%"=="6" goto disable_startup
if "%choice%"=="7" goto stop_watcher
if "%choice%"=="8" goto manage_folders
if "%choice%"=="9" goto manage_account
if "%choice%"=="10" goto force_resync
if "%choice%"=="0" exit /b 0
echo Invalid option.
timeout /t 2 >nul 2>&1 || ping -n 3 127.0.0.1 >nul
goto menu

:handle_arg
set "arg=%~1"
if /i "%arg%"=="watch" goto run_watcher_arg
if /i "%arg%"=="run" goto run_watcher_arg
if /i "%arg%"=="1" goto run_watcher_arg
if /i "%arg%"=="silent" goto run_silent
if /i "%arg%"=="bg" goto run_silent
if /i "%arg%"=="2" goto run_silent
if /i "%arg%"=="status" goto check_status
if /i "%arg%"=="3" goto check_status
if /i "%arg%"=="logs" goto view_logs
if /i "%arg%"=="log" goto view_logs
if /i "%arg%"=="4" goto view_logs
if /i "%arg%"=="enable" goto enable_startup
if /i "%arg%"=="enable-startup" goto enable_startup
if /i "%arg%"=="5" goto enable_startup
if /i "%arg%"=="disable" goto disable_startup
if /i "%arg%"=="disable-startup" goto disable_startup
if /i "%arg%"=="6" goto disable_startup
if /i "%arg%"=="stop" goto stop_watcher
if /i "%arg%"=="7" goto stop_watcher
if /i "%arg%"=="dirs" goto manage_folders
if /i "%arg%"=="folders" goto manage_folders
if /i "%arg%"=="8" goto manage_folders
if /i "%arg%"=="account" goto manage_account
if /i "%arg%"=="creds" goto manage_account
if /i "%arg%"=="9" goto manage_account
if /i "%arg%"=="resync" goto force_resync
if /i "%arg%"=="force" goto force_resync
if /i "%arg%"=="10" goto force_resync
echo Unknown argument: %arg%
echo Usage: GoogleUnlimited.bat [watch^|silent^|status^|logs^|enable^|disable^|stop^|dirs^|account^|resync]
exit /b 1

:run_watcher
if "%IS_MENU%"=="1" cls
%PS_CMD% -File "%~dp0WatchAndUpload.ps1"
if "%IS_MENU%"=="1" (pause & goto menu)
exit /b %ERRORLEVEL%

:run_watcher_arg
set "EXTRA_ARGS="
:strip_loop
shift
if "%~1"=="" goto run_watcher_exec
if not defined EXTRA_ARGS (
    set "EXTRA_ARGS="%~1""
) else (
    set "EXTRA_ARGS=%EXTRA_ARGS% "%~1""
)
goto strip_loop

:run_watcher_exec
if defined EXTRA_ARGS (
    %PS_CMD% -File "%~dp0WatchAndUpload.ps1" %EXTRA_ARGS%
) else (
    %PS_CMD% -File "%~dp0WatchAndUpload.ps1"
)
exit /b %ERRORLEVEL%


:run_silent
if "%IS_MENU%"=="1" cls
echo Launching Google Photos watcher in silent background mode...
wscript.exe "%~dp0StartPhotosWatcher.vbs"
echo [OK] Background watcher launched.
if "%IS_MENU%"=="1" ((timeout /t 3 >nul 2>&1 || ping -n 4 127.0.0.1 >nul) & goto menu)
exit /b 0

:check_status
if "%IS_MENU%"=="1" cls
%PS_CMD% -File "%~dp0WatchAndUpload.ps1" -StatusOnly
if "%IS_MENU%"=="1" (pause & goto menu)
exit /b %ERRORLEVEL%

:view_logs
if "%IS_MENU%"=="1" cls
%PS_CMD% -File "%~dp0WatchAndUpload.ps1" -ShowLogs
if "%IS_MENU%"=="1" (pause & goto menu)
exit /b %ERRORLEVEL%

:enable_startup
if "%IS_MENU%"=="1" cls
%PS_CMD% -File "%~dp0WatchAndUpload.ps1" -EnableStartup
if "%IS_MENU%"=="1" (pause & goto menu)
exit /b %ERRORLEVEL%

:disable_startup
if "%IS_MENU%"=="1" cls
%PS_CMD% -File "%~dp0WatchAndUpload.ps1" -DisableStartup
if "%IS_MENU%"=="1" (pause & goto menu)
exit /b %ERRORLEVEL%

:stop_watcher
if "%IS_MENU%"=="1" cls
%PS_CMD% -File "%~dp0WatchAndUpload.ps1" -StopWatcher
if "%IS_MENU%"=="1" (pause & goto menu)
exit /b %ERRORLEVEL%

:manage_folders
cls
echo ==========================================================
echo   *  Manage Watched Folders
echo ==========================================================
set "WATCH_CONF=%~dp0watch_dirs.txt"
if exist "%WATCH_CONF%" (
    echo Current custom watch folders in watch_dirs.txt:
    type "%WATCH_CONF%"
)
if not exist "%WATCH_CONF%" (
    echo No custom folders configured yet [using standard user and cloud folders].
)
echo.
echo Options:
echo   [1] Add a custom folder path to watch
echo   [2] Clear all custom folders
echo   [0] Back to main menu
echo ==========================================================
set "fchoice="
set /p "fchoice=Select an option [0-2]: "
if "%fchoice%"=="1" goto add_watch_folder
if "%fchoice%"=="2" goto clear_watch_folders
if "%fchoice%"=="0" goto menu
echo Invalid option.
timeout /t 2 >nul 2>&1 || ping -n 3 127.0.0.1 >nul
goto manage_folders

:add_watch_folder
echo.
set "newdir="
set /p "newdir=Enter full path of folder to watch: "
if not "%newdir%"=="" (
    >>"%WATCH_CONF%" echo %newdir%
    echo [OK] Added folder: %newdir%
)
timeout /t 2 >nul 2>&1 || ping -n 3 127.0.0.1 >nul
goto manage_folders

:clear_watch_folders
if exist "%WATCH_CONF%" del "%WATCH_CONF%"
echo [OK] Custom watch folders cleared.
timeout /t 2 >nul 2>&1 || ping -n 3 127.0.0.1 >nul
goto manage_folders

:manage_account
cls
echo ==========================================================
echo   *  Google Photos Account Management
echo ==========================================================
if exist "%~dp0gotohp-cli-x64.exe" (
    "%~dp0gotohp-cli-x64.exe" --config "%~dp0gotohp.config" creds list
)
if not exist "%~dp0gotohp-cli-x64.exe" (
    echo gotohp-cli-x64.exe not found.
)
echo.
echo Options:
echo   [1] Switch active account
echo   [2] Add account via GUI (gotohp-x64.exe)
echo   [0] Back to main menu
echo ==========================================================
set "acchoice="
set /p "acchoice=Select an option [0-2]: "
if "%acchoice%"=="1" goto switch_account
if "%acchoice%"=="2" goto open_account_gui
if "%acchoice%"=="0" goto menu
echo Invalid option.
timeout /t 2 >nul 2>&1 || ping -n 3 127.0.0.1 >nul
goto manage_account

:switch_account
echo.
set "acemail="
set /p "acemail=Enter email address to set active: "
if not "%acemail%"=="" (
    "%~dp0gotohp-cli-x64.exe" --config "%~dp0gotohp.config" creds set %acemail%
)
pause
goto manage_account

:open_account_gui
if exist "%~dp0gotohp-x64.exe" start "" "%~dp0gotohp-x64.exe"
pause
goto manage_account

:force_resync
if "%IS_MENU%"=="1" cls
echo Starting full scan ^& force re-sync of all media...
%PS_CMD% -File "%~dp0WatchAndUpload.ps1" -ForceResync
if "%IS_MENU%"=="1" (pause & goto menu)
exit /b %ERRORLEVEL%
