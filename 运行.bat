@echo off
REM -----------------------------------------------------------
REM run_main.bat
REM 先检查依赖，然后静默启动 Main.py（无控制台窗口）
REM -----------------------------------------------------------

REM 1) 运行依赖检测脚本（使用普通 python.exe，窗口会短暂出现并自动关闭）
python "%~dp0requirementsAndRun"

REM 2) 静默启动 Main.py —— 使用 pythonw.exe + start /b
REM    %~dp0 表示当前批处理文件所在的目录。
start "" /b pythonw "%~dp0Main.py"

REM 3) 立即结束批处理（窗口瞬间关闭）
exit
