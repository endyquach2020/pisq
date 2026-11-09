param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$word = $null
$document = $null

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0

    $officeSupportBitness = if ($word.Bitness -eq 64) { "64" } else { "32" }
    $programRoots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}) |
        Where-Object { $_ } |
        Select-Object -Unique
    $templateNames = @(
        "MathType Commands 2016.dotm",
        "MathType Commands 2013.dotm",
        "MathType Commands 2010.dotm",
        "MathType Commands.dotm"
    )
    $templatePath = $null
    foreach ($root in $programRoots) {
        foreach ($templateName in $templateNames) {
            $candidate = Join-Path $root "MathType\Office Support\$officeSupportBitness\$templateName"
            if (Test-Path $candidate) {
                $templatePath = $candidate
                break
            }
        }
        if ($templatePath) {
            break
        }
    }

    if (-not $templatePath) {
        throw "MathType Word command template not found for $officeSupportBitness-bit Word."
    }

    $null = $word.AddIns.Add($templatePath, $true)
    $document = $word.Documents.Open($SourcePath, $false, $false, $false)
    $convertedCount = 0

    for ($index = $document.InlineShapes.Count; $index -ge 1; $index--) {
        $shape = $document.InlineShapes.Item($index)
        $isMathType = $false
        try {
            $isMathType = $shape.OLEFormat.ProgID -eq "Equation.DSMT4"
        }
        catch {
            continue
        }

        if (-not $isMathType) {
            continue
        }

        $beforeCount = $document.InlineShapes.Count
        $paragraph = $shape.Range.Paragraphs.Item(1)
        $textBefore = $document.Range($paragraph.Range.Start, $shape.Range.Start).Text -replace '[\x01\r\a]', ''
        $textAfter = $document.Range($shape.Range.End, $paragraph.Range.End).Text -replace '[\x01\r\a]', ''
        $isDisplayEquation = (
            $paragraph.Range.ParagraphFormat.Alignment -eq 1 -and
            [string]::IsNullOrWhiteSpace($textBefore) -and
            [string]::IsNullOrWhiteSpace($textAfter)
        )
        $shape.Range.Select()
        $word.Run("MTCommand_TeXToggle")

        if ($document.InlineShapes.Count -ne $beforeCount - 1) {
            throw "MathType did not convert equation $($convertedCount + 1) to LaTeX."
        }

        $convertedText = $word.Selection.Range.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($convertedText) -or $convertedText.Contains([char]1)) {
            throw "MathType did not produce LaTeX text for equation $($convertedCount + 1)."
        }

        if (
            ($convertedText.StartsWith('\(') -and $convertedText.EndsWith('\)')) -or
            ($convertedText.StartsWith('\[') -and $convertedText.EndsWith('\]'))
        ) {
            $convertedText = $convertedText.Substring(2, $convertedText.Length - 4)
        }
        elseif ($convertedText.StartsWith('$$') -and $convertedText.EndsWith('$$')) {
            $convertedText = $convertedText.Substring(2, $convertedText.Length - 4)
        }
        elseif ($convertedText.StartsWith('$') -and $convertedText.EndsWith('$')) {
            $convertedText = $convertedText.Substring(1, $convertedText.Length - 2)
        }

        $delimiters = if ($isDisplayEquation) { '$$' } else { '$' }
        $word.Selection.Range.Text = $delimiters + $convertedText + $delimiters

        $convertedCount++
    }

    $document.SaveAs2([IO.Path]::GetFullPath($OutputPath), 16)
    Write-Output "ConvertedCount=$convertedCount"
}
finally {
    if ($document -ne $null) {
        $document.Close(0)
    }
    if ($word -ne $null) {
        $word.Quit()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
