@echo off
REM One-click setup + run for Windows (creates venv, installs all libraries, starts the app)
cd /d "%~dp0"
if not exist venv (python -m venv venv)
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
streamlit run app.py
