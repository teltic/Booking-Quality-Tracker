@echo off
REM Double-click this file to check for new bookings and, if there are any,
REM generate today's Booking Quality Log workbook.
REM Also what the daily scheduled task (see setup_daily_task.bat) runs.

REM --- Edit this path if you ever move the output folder ---
REM This is the ONLY place this path is set -- NOT in .env. (.env only
REM holds PRICELABS_API_KEY.) If you edit .env expecting it to change
REM where files get saved, it won't -- edit the line below instead.
set OUTPUT_DIR=C:\Users\telti\Documents\Airbnb Pricing Revenue Management\Mesquite\Daily - Booked Reservations Review

cd /d "%~dp0"
python run.py --output-dir "%OUTPUT_DIR%"

echo.
echo Done. Press any key to close this window.
pause >nul
