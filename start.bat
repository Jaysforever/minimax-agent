@echo off
chcp 65001 >nul
cd /d "%~dp0"
call conda activate agent
streamlit run app.py
pause
