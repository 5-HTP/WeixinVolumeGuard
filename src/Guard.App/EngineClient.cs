using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;

namespace Guard.App;

public sealed class EngineClient : IAsyncDisposable
{
    private Process? process;
    private readonly string runId = Guid.NewGuid().ToString("N");
    private readonly SemaphoreSlim writer = new(1);
    private readonly CancellationTokenSource stop = new();
    private readonly TaskCompletionSource<bool> hello = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource<bool> clean = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private Task? readerTask;
    private Task? beatTask;
    private WorkerJob? job;
    private DateTime lastMessage = DateTime.UtcNow;
    private long sequence = -1;
    private bool shuttingDown;
    public event Action<JsonElement>? State;
    public event Action<string>? Fault;
    public bool IsRunning => process != null && !process.HasExited;

    public async Task StartAsync(bool desired)
    {
        var executable = Path.Combine(AppContext.BaseDirectory, "Engine", "WeixinVolumeGuard.Engine.exe");
        process = new Process { StartInfo = new ProcessStartInfo(executable) {
            WorkingDirectory = Path.GetDirectoryName(executable)!, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8
        }, EnableRaisingEvents = true };
        process.StartInfo.Environment["WVG_DATA_DIRECTORY"] = Settings.DataDirectory;
        process.Exited += (_, _) => { if (!shuttingDown) Fault?.Invoke("工作进程已退出，防护未确认。"); };
        if (!process.Start()) throw new IOException("无法启动工作进程。");
        job = new WorkerJob(process);
        _ = Task.Run(async () => { while (await process.StandardError.ReadLineAsync() is { } line) Log.Write("engine: " + line[..Math.Min(line.Length, 500)]); });
        readerTask = ReadAsync();
        await SendAsync(new { kind = "hello", parentPid = Environment.ProcessId,
            parentCreated = Process.GetCurrentProcess().StartTime.ToUniversalTime().ToFileTimeUtc().ToString(), desiredEnabled = desired });
        beatTask = HeartbeatAsync();
        if (!await hello.Task.WaitAsync(TimeSpan.FromSeconds(10))) throw new IOException("工作进程握手失败。");
    }

    public async Task SetDesiredAsync(bool enabled) => await SendAsync(new { kind = "setDesiredEnabled", value = enabled });

    private async Task SendAsync(object message)
    {
        await writer.WaitAsync();
        try
        {
            var node = JsonSerializer.SerializeToElement(message);
            var values = new Dictionary<string, object?> { ["protocol"] = 1, ["runId"] = runId, ["requestId"] = Guid.NewGuid().ToString("N") };
            foreach (var field in node.EnumerateObject()) values[field.Name] = field.Value;
            if (process == null || process.HasExited) throw new IOException("工作进程未运行。");
            await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(values));
            await process.StandardInput.FlushAsync();
        }
        finally { writer.Release(); }
    }

    private async Task ReadAsync()
    {
        try
        {
            while (await process!.StandardOutput.ReadLineAsync(stop.Token) is { } line)
            {
                if (line.Length > 65536) throw new IOException("引擎消息过长。");
                using var doc = JsonDocument.Parse(line);
                var root = doc.RootElement;
                if (root.GetProperty("runId").GetString() != runId || root.GetProperty("protocol").GetInt32() != 1) continue;
                lastMessage = DateTime.UtcNow;
                switch (root.GetProperty("kind").GetString())
                {
                    case "hello": hello.TrySetResult(true); break;
                    case "state":
                        var next = root.GetProperty("sequence").GetInt64();
                        if (next > sequence) { sequence = next; State?.Invoke(root.Clone()); }
                        break;
                    case "shutdown": clean.TrySetResult(root.GetProperty("cleanupConfirmed").GetBoolean()); break;
                    case "error": if (!shuttingDown) Fault?.Invoke("工作进程报告错误：" + root.GetProperty("reasonCode").GetString()); break;
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex) { Log.Write("reader: " + ex.GetType().Name); if (!shuttingDown) Fault?.Invoke("工作进程连接中断，防护未确认。"); }
    }

    private async Task HeartbeatAsync()
    {
        try
        {
            using var timer = new PeriodicTimer(TimeSpan.FromSeconds(1));
            while (await timer.WaitForNextTickAsync(stop.Token))
            {
                if (!shuttingDown && DateTime.UtcNow - lastMessage > TimeSpan.FromSeconds(3))
                {
                    Fault?.Invoke("工作进程响应超时，正在中止授权，防护未确认。");
                    process?.StandardInput.Close();
                    break;
                }
                await SendAsync(new { kind = "heartbeat" });
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex) { Log.Write("heartbeat: " + ex.GetType().Name); }
    }

    public async Task<bool> ShutdownAsync()
    {
        if (process == null) return true;
        shuttingDown = true;
        try
        {
            if (!process.HasExited) await SendAsync(new { kind = "shutdown" });
            var confirmed = await clean.Task.WaitAsync(TimeSpan.FromSeconds(8));
            await process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(2));
            return confirmed;
        }
        catch { return false; }
        finally { stop.Cancel(); }
    }

    public async ValueTask DisposeAsync()
    {
        stop.Cancel();
        // Closing stdin also triggers worker cleanup. Only this owned worker may be ended.
        try { process?.StandardInput.Close(); } catch { }
        if (process != null && !process.HasExited)
        {
            try { await process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(6)); }
            catch { try { process.Kill(); } catch { } }
        }
        process?.Dispose();
        job?.Dispose();
    }
}
