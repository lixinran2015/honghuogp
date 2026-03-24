param(
    [string]$InputFile,
    [string]$OutputFile,
    [switch]$AddDropTables
)

$content = Get-Content $InputFile -Encoding UTF8 | Where-Object { $_ -notmatch '^\\restrict' } | ForEach-Object { $_ -replace 'OWNER TO wuyanze', 'OWNER TO postgres' }

if ($AddDropTables) {
    # 从备份文件中提取所有表名
    $tables = @()
    $content | ForEach-Object {
        if ($_ -match 'CREATE TABLE public\.(\w+)') {
            $tables += $matches[1]
        }
    }
    $tables = $tables | Sort-Object -Unique
    
    # 生成 DROP TABLE 语句（按相反顺序，先删除依赖表）
    $drop = $tables | ForEach-Object { "DROP TABLE IF EXISTS public.$_ CASCADE;" }
    $result = $drop + $content
} else {
    $result = $content
}

# 使用 UTF8NoBOM 编码保存，避免 BOM 导致 PostgreSQL 报错
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($OutputFile, $result, $utf8NoBom)

