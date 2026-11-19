using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Guard.App;

internal sealed class WorkerJob : IDisposable
{
    private SafeFileHandle? handle;
    [StructLayout(LayoutKind.Sequential)] private struct Basic
    {
        public long ProcessTime, JobTime;
        public uint Flags;
        public UIntPtr MinimumWorkingSet, MaximumWorkingSet;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)] private struct Counters { public ulong ReadOperations, WriteOperations, OtherOperations, ReadBytes, WriteBytes, OtherBytes; }
    [StructLayout(LayoutKind.Sequential)] private struct Extended
    {
        public Basic Basic;
        public Counters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern SafeFileHandle CreateJobObject(IntPtr attributes, string? name);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool SetInformationJobObject(SafeFileHandle job, int infoClass, ref Extended info, int size);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool AssignProcessToJobObject(SafeFileHandle job, IntPtr process);

    public WorkerJob(Process worker)
    {
        handle = CreateJobObject(IntPtr.Zero, null);
        var info = new Extended { Basic = new Basic { Flags = 0x2000 } };
        if (handle.IsInvalid || !SetInformationJobObject(handle, 9, ref info, Marshal.SizeOf<Extended>()) || !AssignProcessToJobObject(handle, worker.Handle))
        {
            Log.Write("Worker job unavailable: " + Marshal.GetLastWin32Error());
            Dispose();
        }
    }
    public void Dispose() { handle?.Dispose(); handle = null; }
}
