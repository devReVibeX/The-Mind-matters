@echo off
echo ==========================================
echo   YouTube Permanent Block Script (ADB)
echo ==========================================

echo Uninstalling YouTube for user 0...
adb shell pm uninstall --user 0 com.google.android.youtube

echo Disabling YouTube package so it cannot be re-installed...
adb shell pm disable-user --user 0 com.google.android.youtube

echo Checking status...
adb shell pm list packages --user 0 -d | findstr youtube

echo ==========================================
echo     YouTube BLOCKED but still VISIBLE
echo ==========================================
echo Play Store will show YouTube but installation will FAIL!
pause
