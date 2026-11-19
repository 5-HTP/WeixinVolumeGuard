using System.IO;
using System.Text.Json;
using Microsoft.Win32;

namespace Guard.App;

public sealed class Settings
{
    public int SchemaVersion { get; set; } = 1;
    public bool DesiredProtectionEnabled { get; set; }
    public bool CloseToTray { get; set; } = true;
    internal static bool IsPortable => File.Exists(Path.Combine(AppContext.BaseDirectory, "portable-mode.ini"));
    public static string DataDirectory => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        IsPortable ? "WeixinVolumeGuard.Portable" : "WeixinVolumeGuard");
    public static string FilePath => Path.Combine(DataDirectory, "settings.json");

    public static Settings Load(out string? warning)
        => LoadFrom(FilePath,out warning);

    public static Settings LoadFrom(string path,out string? warning)
    {
        warning = null;
        if (!File.Exists(path)) return new();
        try
        {
            var value = JsonSerializer.Deserialize<Settings>(File.ReadAllText(path), Options) ?? throw new JsonException();
            if (value.SchemaVersion != 1) throw new JsonException();
            return value;
        }
        catch
        {
            warning = "设置文件无法读取，已使用默认设置，防护保持关闭。";
            try { File.Copy(path, path + ".invalid-" + DateTime.Now.ToString("yyyyMMdd-HHmmss")); } catch { }
            return new();
        }
    }

    public void Save()
        => SaveTo(FilePath);

    public void SaveTo(string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string temp = path + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(this, Options));
        if (File.Exists(path)) File.Replace(temp, path, path + ".bak");
        else File.Move(temp, path);
    }

    private static readonly JsonSerializerOptions Options = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true };
}

public static class StartupRegistration
{
    private const string Run = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string Name = "WeixinVolumeGuard";
    public static string Command => $"\"{Environment.ProcessPath}\" --background";
    public static string? Read() { using var key = Registry.CurrentUser.OpenSubKey(Run); return key?.GetValue(Name) as string; }
    public static bool Owned(string value) => value.StartsWith('"') && value.EndsWith("\\WeixinVolumeGuard.exe\" --background", StringComparison.OrdinalIgnoreCase);
    public static void Set(bool enabled)
    {
        using var key = Registry.CurrentUser.CreateSubKey(Run, true);
        var current = key.GetValue(Name) as string;
        if (current != null && !Owned(current)) throw new InvalidOperationException("检测到同名的其他启动项，未覆盖。");
        if (enabled)
        {
            if (Command.Length > 260) throw new InvalidOperationException("安装路径过长，无法登记登录启动。");
            key.SetValue(Name, Command, RegistryValueKind.String);
        }
        else key.DeleteValue(Name, false);
        if (Read() != (enabled ? Command : null)) throw new IOException("启动项读回不一致。");
    }
    public static void RepairPath()
    {
        var current = Read();
        if (current != null && current != Command && Owned(current))
        {
            var old = current.Split('"')[1];
            using var installed = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\WeixinVolumeGuard");
            var location = installed?.GetValue("InstallLocation") as string;
            var isCurrentInstall = location != null && string.Equals(Path.GetFullPath(location).TrimEnd('\\'), AppContext.BaseDirectory.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase);
            if (!File.Exists(old) || isCurrentInstall) Set(true);
        }
    }
}

public static class Log
{
    private static readonly object Gate = new();
    public static void Write(string message)
    {
        try
        {
            lock (Gate)
            {
                var directory = Path.Combine(Settings.DataDirectory, "Logs");
                Directory.CreateDirectory(directory);
                var file = Path.Combine(directory, "app.log");
                if (File.Exists(file) && new FileInfo(file).Length > 524288) File.Move(file, file + ".1", true);
                File.AppendAllText(file, DateTimeOffset.Now.ToString("O") + " " + message + Environment.NewLine);
            }
        }
        catch { }
    }
}
