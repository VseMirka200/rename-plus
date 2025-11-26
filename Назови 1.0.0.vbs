' Скрипт для запуска программы "Назови" без консоли
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Получаем путь к папке со скриптом
scriptPath = fso.GetParentFolderName(WScript.ScriptFullName)

' Пробуем запустить pythonw.exe
On Error Resume Next

' Сначала пробуем запустить pythonw.exe из текущей папки
pythonwPath = scriptPath & "\pythonw.exe"
If fso.FileExists(pythonwPath) Then
    ' Запускаем скрыто (0 = скрыто)
    WshShell.Run """" & pythonwPath & """ """ & scriptPath & "\file_renamer.py""", 0, False
Else
    ' Если не найден, пробуем системный pythonw.exe
    WshShell.Run "pythonw.exe """ & scriptPath & "\file_renamer.py""", 0, False
End If

' Проверяем, произошла ли ошибка через небольшую задержку
WScript.Sleep 500
If Err.Number <> 0 Then
    ' Показываем сообщение об ошибке
    MsgBox "Ошибка запуска!" & vbCrLf & vbCrLf & "Проверьте, что Python установлен." & vbCrLf & vbCrLf & "Ошибка: " & Err.Description, vbCritical, "Ошибка"
End If

On Error Goto 0
WScript.Quit
