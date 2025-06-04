@echo off
REM 文字コードをUTF-8に変更 (文字化け対策)
chcp 65001 > nul

REM バッチファイルが存在するディレクトリに移動
cd /d "%~dp0"

REM Pythonスクリプトのファイル名を指定 (拡張子 .py を含める)
set SCRIPT_NAME=insta360convert.py

REM --- 起動メッセージを表示 ---
echo %SCRIPT_NAME% を起動しています...
echo GUIウィンドウが表示されます。
echo (このコンソールウィンドウは自動的に閉じます)
REM --------------------------

REM startコマンドとpyw.exeを使ってGUIを起動し、バッチファイルは待機せずに終了する
start "" pyw "%SCRIPT_NAME%"

REM --- 終了メッセージやpauseは不要 ---
