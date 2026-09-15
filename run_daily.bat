@echo off
REM Double-click this file to check for new bookings and, if there are any,
REM generate today's Booking Quality Log workbook.
REM Also what the daily scheduled task (see setup_daily_task.bat) runs.

REM --- Edit this path if you ever move the output folder ---
set OUTPUT_DIR=C:\Users\telti\Documents\Airbnb Pricing Revenue Management\Daily - Booked Reservations Review

cd /d "%~dp0"
python run.py --output-dir "%OUTPUT_DIR%"

echo.
echo Done. Press any key to close this window.
pause >nul
