#Requires -Version 5.1
param([switch]$NonInteractive, [int]$ExpectedByte = -1,
      [int]$FileIndex = 0, [switch]$RequireAsync, [switch]$Background)
# Run on the destination PC. No administrator rights, config changes or clipboard writes.
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Threading;
public static class AspiaClipboardProbe {
    [ComImport, Guid("3D8B0590-F691-11d2-8EA9-006097DF5BD4"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IDataObjectAsyncCapability {
        [PreserveSig] int SetAsyncMode([MarshalAs(UnmanagedType.Bool)] bool enabled);
        [PreserveSig] int GetAsyncMode([MarshalAs(UnmanagedType.Bool)] out bool enabled);
        [PreserveSig] int StartOperation(IntPtr context);
        [PreserveSig] int InOperation([MarshalAs(UnmanagedType.Bool)] out bool active);
        [PreserveSig] int EndOperation(int result, IntPtr context, uint effect);
    }
    [DllImport("ole32.dll")] public static extern int OleInitialize(IntPtr reserved);
    [DllImport("ole32.dll")] public static extern void OleUninitialize();
    [DllImport("ole32.dll")] public static extern int OleGetClipboard(out IDataObject data);
    [DllImport("ole32.dll")] public static extern void ReleaseStgMedium(ref STGMEDIUM medium);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern uint RegisterClipboardFormat(string name);
    [DllImport("kernel32.dll")] public static extern IntPtr GlobalLock(IntPtr memory);
    [DllImport("kernel32.dll")] public static extern bool GlobalUnlock(IntPtr memory);
    public static void Run(int expectedByte, int fileIndex, bool requireAsync) {
        Environment.ExitCode = 1;
        int init = OleInitialize(IntPtr.Zero);
        Console.WriteLine("OleInitialize: 0x{0:X8}", init);
        if (init < 0) return;
        IDataObject data = null;
        IDataObjectAsyncCapability asynchronous = null;
        bool started = false;
        try {
            int hr = OleGetClipboard(out data);
            Console.WriteLine("OleGetClipboard: 0x{0:X8}", hr);
            if (hr < 0 || data == null) return;
            if (requireAsync) {
                asynchronous = (IDataObjectAsyncCapability)data;
                bool enabled, active;
                Marshal.ThrowExceptionForHR(asynchronous.GetAsyncMode(out enabled));
                Console.WriteLine("Asynchronous extraction enabled: {0}", enabled);
                if (!enabled) throw new InvalidOperationException("Asynchronous extraction is disabled");
                Marshal.ThrowExceptionForHR(asynchronous.StartOperation(IntPtr.Zero));
                started = true;
                Marshal.ThrowExceptionForHR(asynchronous.InOperation(out active));
                if (!active) throw new InvalidOperationException("StartOperation did not activate extraction");
            }
            FORMATETC format = new FORMATETC {
                cfFormat = unchecked((short)RegisterClipboardFormat("FileGroupDescriptorW")),
                dwAspect = DVASPECT.DVASPECT_CONTENT, lindex = -1, tymed = TYMED.TYMED_HGLOBAL
            };
            Console.WriteLine("Descriptor QueryGetData: 0x{0:X8}", data.QueryGetData(ref format));
            STGMEDIUM medium;
            Console.WriteLine("Descriptor GetData...");
            data.GetData(ref format, out medium);
            try {
                Console.WriteLine("Descriptor medium: {0}", medium.tymed);
                if (medium.tymed != TYMED.TYMED_HGLOBAL) return;
                IntPtr pointer = GlobalLock(medium.unionmember);
                if (pointer == IntPtr.Zero) throw new InvalidOperationException("GlobalLock failed");
                try { Console.WriteLine("Descriptor entries: {0}", Marshal.ReadInt32(pointer)); }
                finally { GlobalUnlock(medium.unionmember); }
            } finally { ReleaseStgMedium(ref medium); }
            format.cfFormat = unchecked((short)RegisterClipboardFormat("FileContents"));
            format.tymed = TYMED.TYMED_ISTREAM;
            format.lindex = fileIndex; // Default: ONE regular nonempty file. CI also tests a folder child.
            Console.WriteLine("Contents QueryGetData: 0x{0:X8}", data.QueryGetData(ref format));
            Console.WriteLine("Contents GetData...");
            data.GetData(ref format, out medium);
            try {
                Console.WriteLine("Contents medium: {0}", medium.tymed);
                if (medium.tymed != TYMED.TYMED_ISTREAM) return;
                object streamObject = Marshal.GetObjectForIUnknown(medium.unionmember);
                try {
                    IStream stream = (IStream)streamObject;
                    System.Runtime.InteropServices.ComTypes.STATSTG stat;
                    stream.Stat(out stat, 1);
                    Console.WriteLine("Stream Stat: size={0}", stat.cbSize);
                    IntPtr count = Marshal.AllocCoTaskMem(4);
                    try {
                        Marshal.WriteInt32(count, 0);
                        Console.WriteLine("Stream Read: requesting first byte (up to 30 seconds)...");
                        byte[] buffer = new byte[1];
                        stream.Read(buffer, 1, count);
                        if (Marshal.ReadInt32(count) == 1 && (expectedByte < 0 || buffer[0] == expectedByte))
                            Environment.ExitCode = 0;
                        Console.WriteLine("Stream Read: success, bytes={0}", Marshal.ReadInt32(count));
                    } finally { Marshal.FreeCoTaskMem(count); }
                } finally { Marshal.ReleaseComObject(streamObject); }
            } finally { ReleaseStgMedium(ref medium); }
        } catch (Exception error) {
            Console.WriteLine("ERROR: {0}; HRESULT=0x{1:X8}; {2}", error.GetType().Name, error.HResult, error.Message);
        } finally {
            if (started) {
                int end = asynchronous.EndOperation(Environment.ExitCode == 0 ? 0 : unchecked((int)0x80004004),
                                                     IntPtr.Zero, Environment.ExitCode == 0 ? 1u : 0u);
                Console.WriteLine("EndOperation: 0x{0:X8}", end);
                if (end < 0) Environment.ExitCode = 1;
            }
            if (data != null) Marshal.ReleaseComObject(data);
            OleUninitialize();
        }
    }
    public static void RunInBackground(int expectedByte, int fileIndex, bool requireAsync) {
        // A separate STA consumer, while the parent test process pumps the
        // producer's STA. This exercises cross-process COM, not Explorer's UI.
        Thread worker = new Thread(delegate() { Run(expectedByte, fileIndex, requireAsync); });
        worker.SetApartmentState(ApartmentState.STA);
        worker.IsBackground = true;
        worker.Start();
        if (!worker.Join(40000)) {
            Console.WriteLine("ERROR: background clipboard consumer timed out");
            Environment.ExitCode = 1;
        }
    }
}
'@
if (!$NonInteractive) {
    Write-Host 'On the SOURCE PC, select ONE nonempty ordinary file and press Ctrl+C now.'
    Write-Host 'Keep the Aspia session connected. Do not copy any commands/text after the file.'
    [void](Read-Host 'Then return here and press Enter (this PC is the paste destination)')
}
if ($Background) {
    [AspiaClipboardProbe]::RunInBackground($ExpectedByte, $FileIndex, $RequireAsync.IsPresent)
} else {
    [AspiaClipboardProbe]::Run($ExpectedByte, $FileIndex, $RequireAsync.IsPresent)
}
if ($NonInteractive) { exit [Environment]::ExitCode }
[void](Read-Host 'Take a screenshot or copy this output AFTER the check. Press Enter to close')
