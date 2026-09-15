@echo off
REM Run this ONCE (double-click it) to register a Windows Scheduled Task
REM that runs run_daily.bat automatically every day.
REM
REM Safe to run again later -- it overwrites the existing task rather than
REM creating a duplicate, so re-running this after editing the time below
REM (or after moving this folder) updates the schedule in place.

REM --- Edit this to change what time it runs each day (24-hour HH:MM) ---
set RUN_TIME=07:00

schtasks /create /tn "Airbnb Booking Quality Log" /tr "\"%~dp0run_daily.bat\"" /sc daily /st %RUN_TIME% /f

echo.
echo Scheduled task created: runs run_daily.bat every day at %RUN_TIME%.
echo To change the time later, either edit RUN_TIME above and rerun this
echo file, or open Windows "Task Scheduler", find "Airbnb Booking Quality
echo Log" under the Task Scheduler Library, and edit its trigger.
echo.
echo Each day it checks PriceLabs for brand-new confirmed bookings. If there
echo are none since the last file it wrote, it skips writing anything that
echo day -- so an empty-looking run in Task Scheduler's history is normal,
echo not a failure.
echo.
echo Note: this only runs while your computer is on (and, depending on your
echo power settings, may need it to be awake/plugged in) at %RUN_TIME%. If
echo it's asleep at that time, Task Scheduler can optionally run it as soon
echo as the computer wakes up -- ask if you want that configured too.
pause
