# Windows built-in OCR (Windows.Media.Ocr, offline, en-US) for desktop frames.
# Usage: powershell -NoProfile -File ocr_win.ps1 <out.json> <image1.png> [<image2.png> ...]
# Output: [{"image": path, "lines": [{"text": "...", "words": [{"t": "...", "x": .., "y": .., "w": .., "h": ..}]}]}]
param([string]$Out, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Images)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait() | Out-Null; $task.Result }
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("en-US"))
$res = @()
foreach ($img in $Images) {
    $f = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $img).Path)) ([Windows.Storage.StorageFile])
    $s = Await ($f.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($s)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $r = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
    $lines = @(foreach ($l in $r.Lines) {
        @{ text = $l.Text; words = @(foreach ($w in $l.Words) { $b = $w.BoundingRect; @{ t = $w.Text; x = [int]$b.X; y = [int]$b.Y; w = [int]$b.Width; h = [int]$b.Height } }) } })
    $res += @{ image = $img; lines = $lines }
    $s.Dispose()
}
ConvertTo-Json -InputObject @($res) -Depth 6 -Compress | Out-File -Encoding utf8 $Out
