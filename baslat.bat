@echo off
cd /d C:\Users\siska\Downloads\31e\yeni-bot
:loop
python main.py
echo Bot durdu, 5 saniye sonra yeniden baslatiliyor...
timeout /t 5
goto loop
