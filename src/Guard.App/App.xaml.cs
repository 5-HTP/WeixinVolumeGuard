using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Security.Principal;
using System.Text;
using System.Windows;

namespace Guard.App;

public partial class App : System.Windows.Application
{
    private Mutex? mutex;
    private bool ownsMutex;
    private readonly CancellationTokenSource stop = new();
    private MainWindow? window;
    private static string PipeId => "WeixinVolumeGuard-" + WindowsIdentity.GetCurrent().User!.Value + "-" + Process.GetCurrentProcess().SessionId;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        DispatcherUnhandledException += (_, args) =>
        {
            Log.Write("UI error: " + args.Exception.GetType().Name);
            System.Windows.MessageBox.Show("程序发生错误，防护状态需要重新确认。请退出后重新打开。", "微信防降音助手");
            args.Handled = true;
        };
        var command = e.Args.Contains("--shutdown") ? "shutdown" : "open";
        mutex = new Mutex(true, @"Local\" + PipeId, out ownsMutex);
        if (!ownsMutex)
        {
            try
            {
                using var client = new NamedPipeClientStream(".", PipeId, PipeDirection.InOut, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await client.ConnectAsync(3000);
                using var writer = new StreamWriter(client, new UTF8Encoding(false), leaveOpen: true) { AutoFlush = true };
                using var reader = new StreamReader(client, Encoding.UTF8, leaveOpen: true);
                await writer.WriteLineAsync(command);
                var response = await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(12));
                Shutdown(command == "shutdown" && response != "ok" ? 2 : 0);
            }
            catch { Shutdown(2); }
            return;
        }
        if (command == "shutdown") { Shutdown(); return; }
        _ = ServeAsync();
        window = new MainWindow();
        MainWindow = window;
        window.ShowActivated = false;
        if (!e.Args.Contains("--background") || !window.TrayReady) window.Show();
        await window.StartAsync();
    }

    private async Task ServeAsync()
    {
        while (!stop.IsCancellationRequested)
        {
            try
            {
                using var server = new NamedPipeServerStream(PipeId, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
                    PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await server.WaitForConnectionAsync(stop.Token);
                using var reader = new StreamReader(server, Encoding.UTF8, leaveOpen: true);
                using var writer = new StreamWriter(server, new UTF8Encoding(false), leaveOpen: true) { AutoFlush = true };
                var command = await reader.ReadLineAsync(stop.Token).AsTask().WaitAsync(TimeSpan.FromSeconds(3));
                if (command == "open")
                {
                    await Dispatcher.InvokeAsync(() => window?.OpenWindow());
                    await writer.WriteLineAsync("ok");
                }
                else if (command == "shutdown")
                {
                    var clean = window == null || await window.PrepareExitAsync();
                    await writer.WriteLineAsync(clean ? "ok" : "cleanup-unconfirmed");
                    if (clean) await Dispatcher.InvokeAsync(() => window?.FinishExit());
                }
                else await writer.WriteLineAsync("unknown");
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex) { Log.Write("IPC: " + ex.GetType().Name); }
        }
    }

    protected override void OnExit(ExitEventArgs e)
    {
        stop.Cancel();
        if (ownsMutex) mutex?.ReleaseMutex();
        mutex?.Dispose();
        base.OnExit(e);
    }
}
