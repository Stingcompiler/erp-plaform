@echo off
cd /d C:\Users\Sting\Desktop\erp-sting\erp-platform\backend
call venv\Scripts\activate.bat
python manage.py runserver
pause