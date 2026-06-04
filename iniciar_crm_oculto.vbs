Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projectPath = fso.GetParentFolderName(WScript.ScriptFullName)
batchPath = projectPath & "\iniciar_crm.bat"
shell.Run """" & batchPath & """", 0, False
