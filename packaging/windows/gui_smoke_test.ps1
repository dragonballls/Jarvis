$ErrorActionPreference = 'Stop'

$build = Join-Path $PSScriptRoot '..\..\build\windows'
$exe = Join-Path $build 'Jarvis.exe'
$log = Join-Path $build 'jarvis.log'

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Missing packaged executable: $exe"
}
Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue

$smokeHome = Join-Path ([System.IO.Path]::GetTempPath()) ("Jarvis-Gui-Smoke-" + [guid]::NewGuid().ToString('N'))
$selfCodingHome = Join-Path $smokeHome 'Jarvis-SelfCoding-Workspace'
New-Item -ItemType Directory -Path (Join-Path $selfCodingHome '.git') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $selfCodingHome 'agent') -Force | Out-Null

Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class JarvisGuiWin32
{
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool IsWindow(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool MoveWindow(IntPtr hWnd, int x, int y, int width, int height, bool repaint);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool IsIconic(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern IntPtr SendMessageTimeout(
        IntPtr hWnd,
        uint Msg,
        UIntPtr wParam,
        IntPtr lParam,
        uint fuFlags,
        uint uTimeout,
        out UIntPtr lpdwResult);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool PostMessage(IntPtr hWnd, uint Msg, UIntPtr wParam, IntPtr lParam);

    public const int SW_MINIMIZE = 6;
    public const int SW_RESTORE = 9;
    public const uint WM_CLOSE = 0x0010;
    public const uint WM_NULL = 0x0000;
    public const uint SMTO_ABORTIFHUNG = 0x0002;
}
'@

function Get-JarvisWindowHandle([System.Diagnostics.Process] $process) {
    $process.Refresh()
    if ($process.MainWindowHandle -ne [IntPtr]::Zero) {
        return $process.MainWindowHandle
    }
    $found = [JarvisGuiWin32]::FindWindow($null, 'Jarvis')
    if ($found -ne [IntPtr]::Zero) {
        return $found
    }
    return [IntPtr]::Zero
}

if ($env:GITHUB_WORKSPACE -and (Test-Path -LiteralPath (Join-Path $env:GITHUB_WORKSPACE 'desktop\dist\index.html'))) {
    $env:JARVIS_WORKSPACE = $env:GITHUB_WORKSPACE
}
$env:USERPROFILE = $smokeHome
$env:HOME = $smokeHome
$env:JARVIS_SMOKE_TEST = '1'
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--disable-gpu'

$process = Start-Process -FilePath $exe -WorkingDirectory $build -PassThru
$handle = [IntPtr]::Zero

try {
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        if ($process.HasExited) {
            throw "Jarvis.exe exited before its GUI became available (code $($process.ExitCode))."
        }
        $handle = Get-JarvisWindowHandle $process
        if ($handle -ne [IntPtr]::Zero -and [JarvisGuiWin32]::IsWindow($handle)) {
            break
        }
        Start-Sleep -Milliseconds 500
    }

    if ($handle -eq [IntPtr]::Zero -or -not [JarvisGuiWin32]::IsWindow($handle)) {
        if (Test-Path -LiteralPath $log) {
            Write-Host '----- packaged Jarvis GUI startup log -----'
            Get-Content -LiteralPath $log -Raw | Write-Host
            Write-Host '----- end packaged Jarvis GUI startup log -----'
        } else {
            Write-Host 'Packaged Jarvis produced no jarvis.log before the GUI timeout.'
        }
        $process.Refresh()
        throw "The packaged Jarvis executable did not create a real top-level Jarvis window within 90 seconds. PID=$($process.Id), HasExited=$($process.HasExited), ExitCode=$($process.ExitCode)."
    }

    [UIntPtr]$result = [UIntPtr]::Zero
    $probe = [JarvisGuiWin32]::SendMessageTimeout(
        $handle,
        [JarvisGuiWin32]::WM_NULL,
        [UIntPtr]::Zero,
        [IntPtr]::Zero,
        [JarvisGuiWin32]::SMTO_ABORTIFHUNG,
        3000,
        [ref]$result)
    if ($probe -eq [IntPtr]::Zero) {
        throw 'The real Jarvis window did not respond to a Win32 responsiveness probe.'
    }
    Write-Host 'GUI lifecycle: responsive'

    [JarvisGuiWin32]::SetForegroundWindow($handle) | Out-Null
    $before = [JarvisGuiWin32+RECT]::new()
    if (-not [JarvisGuiWin32]::GetWindowRect($handle, [ref]$before)) {
        throw 'Could not read the Jarvis window rectangle before moving it.'
    }

    $width = [Math]::Max(900, $before.Right - $before.Left)
    $height = [Math]::Max(650, $before.Bottom - $before.Top)
    $targetX = $before.Left + 40
    $targetY = $before.Top + 40
    if (-not [JarvisGuiWin32]::MoveWindow($handle, $targetX, $targetY, $width, $height, $true)) {
        throw 'Win32 MoveWindow failed for the packaged Jarvis window.'
    }
    Start-Sleep -Milliseconds 500
    $after = [JarvisGuiWin32+RECT]::new()
    [JarvisGuiWin32]::GetWindowRect($handle, [ref]$after) | Out-Null
    if ([Math]::Abs($after.Left - $targetX) -gt 20 -or [Math]::Abs($after.Top - $targetY) -gt 20) {
        throw "Jarvis window did not move as requested. Expected approximately ($targetX,$targetY), got ($($after.Left),$($after.Top))."
    }
    Write-Host 'GUI lifecycle: move'

    [JarvisGuiWin32]::ShowWindow($handle, [JarvisGuiWin32]::SW_MINIMIZE) | Out-Null
    Start-Sleep -Milliseconds 500
    if (-not [JarvisGuiWin32]::IsIconic($handle)) {
        throw 'Jarvis window did not minimize.'
    }
    Write-Host 'GUI lifecycle: minimize'

    [JarvisGuiWin32]::ShowWindow($handle, [JarvisGuiWin32]::SW_RESTORE) | Out-Null
    Start-Sleep -Milliseconds 500
    if ([JarvisGuiWin32]::IsIconic($handle)) {
        throw 'Jarvis window did not restore from minimized state.'
    }
    $probe = [JarvisGuiWin32]::SendMessageTimeout(
        $handle,
        [JarvisGuiWin32]::WM_NULL,
        [UIntPtr]::Zero,
        [IntPtr]::Zero,
        [JarvisGuiWin32]::SMTO_ABORTIFHUNG,
        3000,
        [ref]$result)
    if ($probe -eq [IntPtr]::Zero) {
        throw 'Jarvis window was not responsive after restore.'
    }
    Write-Host 'GUI lifecycle: restore'

    if (-not [JarvisGuiWin32]::PostMessage($handle, [JarvisGuiWin32]::WM_CLOSE, [UIntPtr]::Zero, [IntPtr]::Zero)) {
        throw 'Could not send WM_CLOSE to the packaged Jarvis window.'
    }
    if (-not $process.WaitForExit(20 * 1000)) {
        throw 'Jarvis.exe did not exit within 20 seconds after closing the real GUI window.'
    }
    if ($process.ExitCode -ne 0) {
        throw "Jarvis.exe exited with code $($process.ExitCode) after a normal GUI close."
    }
    Write-Host 'GUI lifecycle: close and clean process exit'
    Write-Host 'Jarvis packaged GUI lifecycle test passed.'
}
finally {
    if ($handle -ne [IntPtr]::Zero -and [JarvisGuiWin32]::IsWindow($handle)) {
        [JarvisGuiWin32]::PostMessage($handle, [JarvisGuiWin32]::WM_CLOSE, [UIntPtr]::Zero, [IntPtr]::Zero) | Out-Null
    }
    if (-not $process.HasExited) {
        try { $process.Kill() } catch { }
        try { $process.WaitForExit(5000) } catch { }
    }
    $process.Dispose()
    Remove-Item -LiteralPath $smokeHome -Recurse -Force -ErrorAction SilentlyContinue
}
