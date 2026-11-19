using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Media;
using Forms = System.Windows.Forms;

namespace Guard.App;

public partial class MainWindow : Window
{
    private readonly Settings settings;
    private EngineClient? engine;
    private Forms.NotifyIcon? tray;
    private Forms.ToolStripMenuItem? trayToggle;
    private bool ready;
    private bool busy;
    private bool exiting;
    private bool finalExit;
    private bool initializing = true;
    private bool changingStartup;
    public bool TrayReady => tray != null;

    public MainWindow()
    {
        InitializeComponent();
        settings = Settings.Load(out var warning);
        ProtectionToggle.IsChecked = settings.DesiredProtectionEnabled;
        TrayToggle.IsChecked = settings.CloseToTray;
        if (warning != null) SettingsMessage.Text = warning;
        if (Settings.IsPortable)
        {
            StartupToggle.IsEnabled = false;
            StartupToggle.Content = "免安装版不提供开机自启";
        }
        else
        {
            try { StartupRegistration.RepairPath(); StartupToggle.IsChecked = StartupRegistration.Read() != null; }
            catch (Exception ex) { SettingsMessage.Text = ex.Message; }
        }
        try
        {
            tray = new Forms.NotifyIcon { Icon = new System.Drawing.Icon(Path.Combine(AppContext.BaseDirectory,"App.ico")), Text = "微信防降音助手 · 正在连接", Visible = true };
            Icon = System.Windows.Interop.Imaging.CreateBitmapSourceFromHIcon(tray.Icon.Handle,Int32Rect.Empty,System.Windows.Media.Imaging.BitmapSizeOptions.FromEmptyOptions());
            var menu = new Forms.ContextMenuStrip();
            menu.Items.Add("打开窗口", null, (_, _) => Dispatcher.Invoke(OpenWindow));
            trayToggle = new Forms.ToolStripMenuItem("启用防降音", null, async (_, _) => await Dispatcher.InvokeAsync(() => SetProtectionAsync(!settings.DesiredProtectionEnabled)).Task.Unwrap());
            menu.Items.Add(trayToggle);
            menu.Items.Add(new Forms.ToolStripSeparator());
            menu.Items.Add("退出", null, async (_, _) => await Dispatcher.InvokeAsync(ExitAsync).Task.Unwrap());
            tray.ContextMenuStrip = menu;
            tray.DoubleClick += (_, _) => Dispatcher.Invoke(OpenWindow);
        }
        catch { tray?.Dispose(); tray = null; SettingsMessage.Text = "无法创建托盘图标，窗口将保持可见。"; }
        UpdateFooter();
        initializing = false;
    }

    public async Task StartAsync()
    {
        var current = new EngineClient();
        engine = current;
        current.State += state => Dispatcher.BeginInvoke(() => { if (ReferenceEquals(engine, current) && !finalExit) ApplyState(state); });
        current.Fault += message => Dispatcher.BeginInvoke(() => {
            if (ReferenceEquals(engine,current) && !finalExit)
            {
                ready=false; ProtectionToggle.IsEnabled=false; ShowFault(message);
            }
        });
        try
        {
            await current.StartAsync(settings.DesiredProtectionEnabled);
            ready = true;
            ProtectionToggle.IsEnabled = true;
        }
        catch (Exception ex)
        {
            ShowFault("无法启动防护引擎：" + ex.Message);
            ProtectionToggle.IsEnabled = false;
            await current.DisposeAsync();
            engine = null;
        }
    }

    private void ApplyState(JsonElement value)
    {
        var state = value.GetProperty("state").GetString() ?? "Error";
        string reason = value.TryGetProperty("reasonCode", out var r) && r.ValueKind == JsonValueKind.String ? r.GetString()! : "";
        var wechat = value.GetProperty("wechat");
        var running = wechat.GetProperty("running").GetBoolean();
        RunningText.Text = running ? "正在运行" : "尚未检测到微信";
        VersionText.Text = running ? wechat.GetProperty("fileVersion").GetString() +
            (wechat.GetProperty("support").GetString() == "Supported" ? " · 已匹配支持项" : " · 需要适配") : "尚未检测";
        var hook = value.GetProperty("hook");
        var armed = hook.GetProperty("armed").GetBoolean();
        if (state == "Enabled" && (!armed || !hook.GetProperty("attached").GetBoolean())) { ShowFault("引擎就绪信息不一致。"); return; }
        var (title, detail) = state switch
        {
            "Disabled" => ("已停用", "当前未拦截微信的设备音量调用。"),
            "WaitingForWeixin" => ("等待微信启动", "防护意愿已开启，检测到受支持微信后会自动检查。"),
            "CheckingCompatibility" => ("正在检查微信", "正在校验主进程、版本和 DLL 文件。"),
            "WaitingForAudioDevice" => ("等待输出设备", "连接可用的系统输出设备后自动重试。"),
            "WaitingForRecordingIdle" => ("等待音频空闲", "等待当前录音及音量恢复结束。请等到“已启用”后再开始下一段录音。"),
            "Attaching" => ("正在启用", "版本已通过，正在检查并挂接音频接口。"),
            "Enabled" => ("已启用", "目标接口已挂接并获得有效授权，其他调用继续执行。"),
            "RecheckingAudio" => ("正在重新检查音频环境", "音频设备或连接发生变化，防护尚未重新确认。"),
            "Unsupported" => ("当前版本或环境需要适配", Reason(reason)),
            "CleaningUp" => ("正在停用", "正在撤销拦截，请稍候。"),
            _ => ("防护发生错误", Reason(reason))
        };
        StatusTitle.Text = title;
        StatusDetail.Text = detail;
        ProtectionText.Text = state == "Enabled" ? "已挂接 · 授权有效" : title;
        StatusIcon.Foreground = state == "Enabled" ? new SolidColorBrush(System.Windows.Media.Color.FromRgb(16, 142, 85)) :
            state == "Error" ? new SolidColorBrush(System.Windows.Media.Color.FromRgb(204, 65, 65)) : Foreground;
        long count = hook.TryGetProperty("blockedCount", out var c) ? c.GetInt64() : 0;
        CountText.Text = $"本次挂接已拦截 {count} 次";
        if (tray != null) tray.Text = "微信防降音助手 · " + title;
        if (trayToggle != null) trayToggle.Text = settings.DesiredProtectionEnabled ? "停用防降音" : "启用防降音";
    }

    private static string Reason(string code) => code switch
    {
        "UnknownDllHash" => "DLL 哈希没有匹配已验证文件，本次不会挂接。",
        "UnsupportedWeixinVersion" => "当前微信版本不在支持范围，请等待适配。",
        "UnsupportedArchitecture" => "首版仅支持 Windows 与微信 x64。",
        "ProcessAccessDenied" => "无法访问微信进程。请确认微信与本程序都以普通当前用户运行。",
        "PublisherUnverified" => "无法确认微信发布者签名，未挂接。",
        "AmbiguousMainProcess" => "检测到多个主进程候选，无法安全确认目标。",
        "ModuleNotLoaded" => "微信尚未加载所需模块，正在等待。",
        "ModuleChanged" => "微信模块发生变化，请等待重新检查。",
        "AudioImplementationUnsupported" => "当前 Core Audio 实现不符合已验证条件，未启用。",
        "AudioProbeFailed" or "CaptureStateUnknown" => "无法确认音频设备或录音会话状态，未启用。",
        "CleanupUnconfirmed" => "停用未确认。可重试；关闭微信也会结束该进程内的拦截。",
        _ => "引擎未确认有效防护。请重试；若持续失败，请查看本地日志。" + (code.Length > 0 ? "（" + code + "）" : "")
    };

    private void ShowFault(string text)
    {
        StatusTitle.Text = "防护未确认";
        StatusDetail.Text = text;
        ProtectionText.Text = "错误";
        if (tray != null) tray.Text = "微信防降音助手 · 错误";
    }

    private async Task SetProtectionAsync(bool enabled)
    {
        if (!ready || busy || exiting || engine == null) return;
        busy = true;
        ProtectionToggle.IsEnabled = false;
        try
        {
            settings.DesiredProtectionEnabled = enabled;
            ProtectionToggle.IsChecked = enabled;
            SaveSettings();
            await engine.SetDesiredAsync(enabled);
        }
        catch (Exception ex) { ShowFault(ex.Message); }
        finally { busy = false; ProtectionToggle.IsEnabled = ready && !exiting; }
    }

    private async void ToggleProtection(object sender, RoutedEventArgs e)
    {
        if (!initializing) await SetProtectionAsync(ProtectionToggle.IsChecked == true);
    }
    private async void Retry(object sender, RoutedEventArgs e)
    {
        if (busy || exiting) return;
        RetryButton.IsEnabled = false;
        try
        {
            if (engine == null || !engine.IsRunning || !ready)
            {
                var previous=engine; engine=null;
                if(previous!=null) { await previous.ShutdownAsync(); await previous.DisposeAsync(); }
                await StartAsync();
            }
            else await SetProtectionAsync(settings.DesiredProtectionEnabled);
        }
        finally { RetryButton.IsEnabled = true; }
    }
    private void ToggleStartup(object sender, RoutedEventArgs e)
    {
        if (initializing || changingStartup || Settings.IsPortable) return;
        changingStartup = true;
        try
        {
            StartupRegistration.Set(StartupToggle.IsChecked == true);
            SettingsMessage.Text = StartupToggle.IsChecked == true ? "已登记当前用户登录启动；任务管理器可单独停用。" : "已清理登录启动项。";
        }
        catch (Exception ex) { SettingsMessage.Text = ex.Message; }
        finally { StartupToggle.IsChecked = StartupRegistration.Read() != null; changingStartup = false; }
    }
    private void ToggleTray(object sender, RoutedEventArgs e)
    {
        if (initializing) return;
        settings.CloseToTray = TrayToggle.IsChecked == true;
        SaveSettings(); UpdateFooter();
    }
    private void SaveSettings()
    {
        try { settings.Save(); SettingsMessage.Text = "设置已保存。"; }
        catch { SettingsMessage.Text = "本次设置未保存，重新启动后可能恢复旧设置。"; }
    }
    private void UpdateFooter() => FooterText.Text = settings.CloseToTray && TrayReady ? "关闭窗口后仍在托盘运行" : "关闭窗口将停用防护并退出";
    private void OpenLogs(object sender, RoutedEventArgs e)
    {
        var directory = Path.Combine(Settings.DataDirectory, "Logs"); Directory.CreateDirectory(directory);
        Process.Start(new ProcessStartInfo("explorer.exe", directory) { UseShellExecute = true });
    }
    public void OpenWindow() { Show(); WindowState = WindowState.Normal; }
    private async void OnClosing(object? sender, CancelEventArgs e)
    {
        if (finalExit) return;
        e.Cancel = true;
        if (settings.CloseToTray && TrayReady && !exiting) Hide();
        else await ExitAsync();
    }
    private async void ExitClick(object sender, RoutedEventArgs e) => await ExitAsync();
    private async Task ExitAsync()
    {
        if (exiting) return;
        bool clean = await PrepareExitAsync();
        if (!clean)
        {
            var decision = System.Windows.MessageBox.Show("停用未确认。关闭微信可结束此进程内拦截。仍要退出本程序吗？", "退出确认", MessageBoxButton.YesNo, MessageBoxImage.Warning);
            if (decision != MessageBoxResult.Yes) { exiting = false; OpenWindow(); return; }
        }
        FinishExit();
    }
    public async Task<bool> PrepareExitAsync()
    {
        exiting = true;
        ProtectionToggle.IsEnabled = false;
        StatusTitle.Text = "正在停用";
        bool clean = engine == null || await engine.ShutdownAsync();
        if (engine != null) await engine.DisposeAsync();
        engine = null;
        ready = false;
        return clean;
    }
    public void FinishExit()
    {
        finalExit = true;
        tray?.Dispose(); tray = null;
        Close(); System.Windows.Application.Current.Shutdown();
    }
}
