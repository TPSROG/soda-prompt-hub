using System.Threading;

namespace SodaPromptHub.ComputeWorker;

internal static class Program
{
    private const string InstanceEventName = @"Local\SodaPromptHub.ComputeWorker.Show";

    [STAThread]
    private static void Main()
    {
        using var instanceEvent = new EventWaitHandle(
            false,
            EventResetMode.AutoReset,
            InstanceEventName,
            out var isFirstInstance);
        if (!isFirstInstance)
        {
            instanceEvent.Set();
            return;
        }

        ApplicationConfiguration.Initialize();
        using var shell = new ShellForm();
        var restoreRegistration = ThreadPool.RegisterWaitForSingleObject(
            instanceEvent,
            (_, _) =>
            {
                if (shell.IsHandleCreated && !shell.IsDisposed)
                {
                    shell.BeginInvoke(new Action(shell.RestoreFromTray));
                }
            },
            null,
            Timeout.Infinite,
            false);
        try
        {
            Application.Run(shell);
        }
        finally
        {
            restoreRegistration.Unregister(null);
        }
    }
}
