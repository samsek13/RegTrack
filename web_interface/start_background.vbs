' RegTracker Web Interface Background Launcher

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "d:\plusDrei\LT3\regtracker\web_interface"

' Run the batch file
WshShell.Run "start_server.bat", 0, False

' Wait 5 seconds for service to start
WScript.Sleep 5000

' Check if port 5000 is listening
Set shell = CreateObject("WScript.Shell")
Set exec = shell.Exec("cmd /c netstat -ano | findstr :5000")
output = exec.StdOut.ReadAll

If InStr(output, "LISTENING") > 0 Then
    MsgBox "RegTracker Web Interface Started" & vbCrLf & vbCrLf & "Visit: http://127.0.0.1:5000", 64, "RegTracker"
Else
    MsgBox "Failed to start service." & vbCrLf & "Please run 'python app.py' in cmd to check errors.", 16, "RegTracker"
End If