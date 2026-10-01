function Assert-FileoraStopped {
    param([string]$Repo)

    # Windows holds a running console-script executable open. Check before uv
    # starts changing the environment, including servers using another catalog.
    $executable = Join-Path $Repo '.venv\Scripts\fileora.exe'
    if (Test-Path -LiteralPath $executable) {
        try {
            $handle = [System.IO.File]::Open($executable, [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read, [System.IO.FileShare]::None)
            $handle.Dispose()
        } catch [System.IO.IOException] {
            throw 'Fileora is already running from this environment. Stop it with Ctrl+C in its terminal before running setup or starting another server. Your files and index are unchanged.'
        }
    }

    # A lock file can remain after a normal exit; only the live OS lock matters.
    $lockPath = Join-Path $Repo '.fileora\instance.lock'
    if (Test-Path -LiteralPath $lockPath) {
        $handle = $null
        try {
            $handle = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::ReadWrite)
            $handle.Lock(0, 1)
            $handle.Unlock(0, 1)
        } catch [System.IO.IOException] {
            throw 'The Fileora catalog is already in use. Stop the existing server with Ctrl+C in its terminal before running setup or starting another server. Your files and index are unchanged.'
        } finally {
            if ($null -ne $handle) { $handle.Dispose() }
        }
    }
}
