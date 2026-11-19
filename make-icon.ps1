$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $root 'src\Guard.App\Assets\App.ico'
$sizes = @(16, 24, 32, 48, 64, 128, 256)
$frames = foreach ($size in $sizes) {
    $bitmap = [Drawing.Bitmap]::new($size, $size)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.ScaleTransform($size / 64.0, $size / 64.0)
    $graphics.Clear([Drawing.Color]::Transparent)
    $tile = [Drawing.Drawing2D.GraphicsPath]::new()
    $tile.AddArc(2, 2, 26, 26, 180, 90)
    $tile.AddArc(36, 2, 26, 26, 270, 90)
    $tile.AddArc(36, 36, 26, 26, 0, 90)
    $tile.AddArc(2, 36, 26, 26, 90, 90)
    $tile.CloseFigure()
    $brush = [Drawing.Drawing2D.LinearGradientBrush]::new(
        [Drawing.RectangleF]::new(0, 0, 64, 64),
        [Drawing.ColorTranslator]::FromHtml('#367EF2'),
        [Drawing.ColorTranslator]::FromHtml('#7650DC'), 48.0)
    $graphics.FillPath($brush, $tile)
    $pen = [Drawing.Pen]::new([Drawing.Color]::White, 4.8)
    $pen.StartCap = $pen.EndCap = [Drawing.Drawing2D.LineCap]::Round
    $graphics.DrawLines($pen, [Drawing.PointF[]]@(
        [Drawing.PointF]::new(12, 32), [Drawing.PointF]::new(22, 32),
        [Drawing.PointF]::new(28, 20), [Drawing.PointF]::new(36, 44),
        [Drawing.PointF]::new(42, 32), [Drawing.PointF]::new(52, 32)))
    $png = [IO.MemoryStream]::new()
    try {
        $bitmap.Save($png, [Drawing.Imaging.ImageFormat]::Png)
        if ($size -eq 128) { $bitmap.Save((Join-Path $root 'src\Guard.App\Assets\App.png'), [Drawing.Imaging.ImageFormat]::Png) }
        [pscustomobject]@{ Size = $size; Bytes = $png.ToArray() }
    } finally {
        $png.Dispose(); $pen.Dispose(); $brush.Dispose(); $tile.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
    }
}
$writer = [IO.BinaryWriter]::new([IO.File]::Create($destination))
try {
    $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]$frames.Count)
    $offset = 6 + 16 * $frames.Count
    foreach ($frame in $frames) {
        $writer.Write([byte]($frame.Size % 256)); $writer.Write([byte]($frame.Size % 256))
        $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]32)
        $writer.Write([uint32]$frame.Bytes.Length); $writer.Write([uint32]$offset)
        $offset += $frame.Bytes.Length
    }
    foreach ($frame in $frames) { $writer.Write([byte[]]$frame.Bytes) }
} finally { $writer.Dispose() }
