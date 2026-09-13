using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using SodaPromptHub.ComputeWorker;

namespace SodaPromptHub.Desktop;

internal sealed class ShellForm : Form
{
    private static readonly Size DesignClientSize = new(860, 600);
    private static readonly Size DesignMinimumSize = new(776, 579);
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly DesktopHost host = new();
    private readonly WebView2 webView = new() { Dock = DockStyle.Fill };
    private readonly Icon brandIcon = BrandIcon.Create();
    private readonly NotifyIcon trayIcon;
    private readonly System.Windows.Forms.Timer statusTimer = new() { Interval = 2500 };
    private readonly SemaphoreSlim refreshGate = new(1, 1);
    private bool allowClose;
    private bool webReady;
    private bool trayHintShown;
    private bool workspaceOpened;
    private bool exitRequested;

    internal ShellForm()
    {
        Text = "Soda Prompt Hub";
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = DesignClientSize;
        MinimumSize = DesignMinimumSize;
        BackColor = Color.FromArgb(236, 232, 220);
        Icon = brandIcon;
        webView.DefaultBackgroundColor = Color.FromArgb(236, 232, 220);
        Controls.Add(webView);

        var trayMenu = new ContextMenuStrip();
        trayMenu.Items.Add("打开启动台", null, (_, _) => RestoreFromTray());
        trayMenu.Items.Add("打开工作台", null, async (_, _) => await RunNativeActionAsync(host.OpenWorkspaceAsync));
        trayMenu.Items.Add(new ToolStripSeparator());
        trayMenu.Items.Add("启动 Core", null, async (_, _) => await RunTrayCommandAsync(host.StartCoreAsync));
        trayMenu.Items.Add("重新启动 Core", null, async (_, _) => await RunTrayCommandAsync(host.RestartCoreAsync));
        trayMenu.Items.Add("切换本机 Worker", null, async (_, _) => await RunTrayCommandAsync(host.ToggleLocalWorkerAsync));
        trayMenu.Items.Add(new ToolStripSeparator());
        trayMenu.Items.Add("打开日志", null, (_, _) => RunNativeAction(host.OpenLogs));
        trayMenu.Items.Add("导出诊断包", null, async (_, _) => await RunTrayExportDiagnosticsAsync());
        trayMenu.Items.Add("打开数据目录", null, (_, _) => RunNativeAction(host.OpenDataFolder));
        trayMenu.Items.Add(new ToolStripSeparator());
        trayMenu.Items.Add("退出启动器（服务继续）", null, (_, _) => ExitShell());
        trayMenu.Items.Add("退出并停止本机服务", null, async (_, _) => await ExitAndStopAsync());

        trayIcon = new NotifyIcon
        {
            Text = "Soda Prompt Hub",
            Icon = brandIcon,
            ContextMenuStrip = trayMenu,
            Visible = true,
        };
        trayIcon.DoubleClick += (_, _) => RestoreFromTray();

        Load += (_, _) => ApplyInitialDpiSize();
        DpiChanged += (_, eventArgs) => MinimumSize = ScaleForDpi(DesignMinimumSize, eventArgs.DeviceDpiNew);
        Shown += async (_, _) => await InitializeWebViewAsync();
        FormClosing += OnFormClosing;
        host.StatusChanged += OnHostStatusChanged;
        statusTimer.Tick += async (_, _) => await PushStatusAsync();
    }

    private void ApplyInitialDpiSize()
    {
        ClientSize = ScaleForDpi(DesignClientSize, DeviceDpi);
        MinimumSize = ScaleForDpi(DesignMinimumSize, DeviceDpi);
        CenterToScreen();
    }

    private static Size ScaleForDpi(Size designSize, int dpi)
    {
        var scale = Math.Max(dpi, 96) / 96F;
        return new Size(
            (int)Math.Round(designSize.Width * scale),
            (int)Math.Round(designSize.Height * scale));
    }

    internal void RestoreFromTray()
    {
        if (IsDisposed)
        {
            return;
        }
        if (InvokeRequired)
        {
            BeginInvoke(new Action(RestoreFromTray));
            return;
        }
        Show();
        WindowState = FormWindowState.Normal;
        Activate();
        BringToFront();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            exitRequested = true;
            statusTimer.Stop();
            statusTimer.Dispose();
            trayIcon.Visible = false;
            trayIcon.Dispose();
            brandIcon.Dispose();
            refreshGate.Dispose();
            host.Dispose();
            webView.Dispose();
        }
        base.Dispose(disposing);
    }

    private async Task InitializeWebViewAsync()
    {
        var indexPath = Path.Combine(host.UiRoot, "index.html");
        if (!File.Exists(indexPath))
        {
            ShowInitializationError($"Desktop UI 资源不完整：\n{indexPath}");
            return;
        }
        try
        {
            var userDataRoot = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Soda Prompt Hub",
                "DesktopShell",
                "WebView2");
            Directory.CreateDirectory(userDataRoot);
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: userDataRoot);
            await webView.EnsureCoreWebView2Async(environment);
            var core = webView.CoreWebView2;
            core.Settings.AreBrowserAcceleratorKeysEnabled = false;
            core.Settings.AreDefaultContextMenusEnabled = false;
            core.Settings.AreDevToolsEnabled = false;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.IsZoomControlEnabled = false;
            core.SetVirtualHostNameToFolderMapping(
                "soda.local",
                host.UiRoot,
                CoreWebView2HostResourceAccessKind.DenyCors);
            core.NavigationStarting += (_, eventArgs) =>
            {
                if (!Uri.TryCreate(eventArgs.Uri, UriKind.Absolute, out var uri)
                    || !string.Equals(uri.Host, "soda.local", StringComparison.OrdinalIgnoreCase))
                {
                    eventArgs.Cancel = true;
                }
            };
            core.NewWindowRequested += (_, eventArgs) => eventArgs.Handled = true;
            core.WebMessageReceived += OnWebMessageReceived;
            core.NavigationCompleted += async (_, eventArgs) =>
            {
                if (!eventArgs.IsSuccess)
                {
                    ShowInitializationError($"Desktop UI 加载失败：{eventArgs.WebErrorStatus}");
                    return;
                }
                webReady = true;
                statusTimer.Start();
                await PushStatusAsync();
                _ = StartCoreAfterUiReadyAsync();
            };
            core.Navigate("https://soda.local/index.html?product=desktop");
        }
        catch (Exception error) when (error is WebView2RuntimeNotFoundException or InvalidOperationException or IOException)
        {
            ShowInitializationError($"无法启动图形界面。请安装 Microsoft Edge WebView2 Runtime。\n\n{error.Message}");
        }
    }

    private async Task StartCoreAfterUiReadyAsync()
    {
        var status = await host.StartCoreAsync();
        await host.StartLocalWorkspaceAsync();
        await PushStatusAsync();
        if (!workspaceOpened
            && status.TryGetValue("phase", out var phase)
            && string.Equals(Convert.ToString(phase), "ready", StringComparison.Ordinal))
        {
            workspaceOpened = true;
            await RunNativeActionAsync(host.OpenWorkspaceAsync);
        }
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs eventArgs)
    {
        string id = string.Empty;
        try
        {
            using var message = JsonDocument.Parse(eventArgs.WebMessageAsJson);
            var root = message.RootElement;
            id = root.GetProperty("id").GetString() ?? string.Empty;
            var method = root.GetProperty("method").GetString() ?? string.Empty;
            if (string.IsNullOrWhiteSpace(id))
            {
                return;
            }
            var parameters = root.TryGetProperty("params", out var parameterValue)
                && parameterValue.ValueKind == JsonValueKind.Object
                ? parameterValue
                : default;
            object payload;
            switch (method)
            {
                case "getStatus":
                    payload = StatusPayload(await host.GetStatusAsync());
                    break;
                case "openWorkspace":
                    await host.OpenWorkspaceAsync();
                    payload = StatusPayload(await host.GetStatusAsync());
                    break;
                case "retryCore":
                    payload = StatusPayload(await host.StartCoreAsync());
                    break;
                case "restartCore":
                    payload = StatusPayload(await host.RestartCoreAsync());
                    break;
                case "openLogs":
                    host.OpenLogs();
                    payload = StatusPayload(await host.GetStatusAsync());
                    break;
                case "exportDiagnostics":
                    var diagnosticsPath = await host.ExportDiagnosticsAsync();
                    payload = new Dictionary<string, object?>
                    {
                        ["path"] = diagnosticsPath,
                        ["message"] = "诊断包已保存到 Downloads，请在分享前检查内容。",
                    };
                    break;
                case "openDataFolder":
                    host.OpenDataFolder();
                    payload = StatusPayload(await host.GetStatusAsync());
                    break;
                case "toggleLocalWorker":
                    payload = StatusPayload(await host.ToggleLocalWorkerAsync());
                    break;
                case "openConfig":
                    host.OpenWorkerConfig();
                    payload = StatusPayload(await host.GetStatusAsync());
                    break;
                case "getWorkerConfig":
                    payload = new Dictionary<string, object?> { ["config"] = host.GetEditableWorkerConfig() };
                    break;
                case "chooseFolder":
                    var initial = parameters.ValueKind == JsonValueKind.Object
                        && parameters.TryGetProperty("initial", out var initialValue)
                        ? initialValue.GetString() ?? string.Empty
                        : string.Empty;
                    payload = new Dictionary<string, object?> { ["path"] = ChooseFolder(initial) };
                    break;
                case "saveWorkerConfig":
                    if (parameters.ValueKind != JsonValueKind.Object
                        || !parameters.TryGetProperty("config", out var configValue)
                        || configValue.ValueKind != JsonValueKind.Object)
                    {
                        throw new InvalidOperationException("图形配置数据无效。");
                    }
                    payload = StatusPayload(await host.SaveLocalWorkerConfigAsync(configValue));
                    break;
                case "hideWindow":
                    HideToTray();
                    payload = StatusPayload(await host.GetStatusAsync());
                    break;
                default:
                    throw new InvalidOperationException($"不支持的宿主操作：{method}");
            }
            await ResolveAsync(id, payload);
        }
        catch (Exception error) when (error is JsonException or KeyNotFoundException or IOException or InvalidOperationException or HttpRequestException or System.ComponentModel.Win32Exception)
        {
            if (!string.IsNullOrWhiteSpace(id))
            {
                await RejectAsync(id, error.Message);
            }
        }
    }

    private async Task PushStatusAsync()
    {
        if (exitRequested || !webReady || !await refreshGate.WaitAsync(0))
        {
            return;
        }
        try
        {
            var status = await host.GetStatusAsync();
            if (!exitRequested && !IsDisposed)
            {
                await ExecuteDesktopFunctionAsync("receiveStatus", status);
            }
        }
        catch (Exception error) when (exitRequested
            && error is ObjectDisposedException or InvalidOperationException)
        {
            // A status refresh may finish while the shell is shutting down.
        }
        finally
        {
            refreshGate.Release();
        }
    }

    private Task ResolveAsync(string id, object payload) => ExecuteDesktopFunctionAsync("resolve", id, payload);
    private Task RejectAsync(string id, string message) => ExecuteDesktopFunctionAsync("reject", id, message);

    private static Dictionary<string, object?> StatusPayload(Dictionary<string, object?> status)
    {
        return new Dictionary<string, object?> { ["status"] = status };
    }

    private string? ChooseFolder(string initial)
    {
        using var dialog = new FolderBrowserDialog
        {
            Description = "选择本机 ComfyUI 使用的模型目录",
            ShowNewFolderButton = true,
            UseDescriptionForTitle = true,
        };
        if (Directory.Exists(initial))
        {
            dialog.InitialDirectory = initial;
        }
        return dialog.ShowDialog(this) == DialogResult.OK ? dialog.SelectedPath : null;
    }

    private async Task ExecuteDesktopFunctionAsync(string method, params object[] arguments)
    {
        if (exitRequested || !webReady || webView.CoreWebView2 is null)
        {
            return;
        }
        var serialized = string.Join(",", arguments.Select(argument => JsonSerializer.Serialize(argument, JsonOptions)));
        await webView.CoreWebView2.ExecuteScriptAsync($"window.SodaDesktop?.{method}({serialized});");
    }

    private async Task RunTrayCommandAsync(Func<Task<Dictionary<string, object?>>> command)
    {
        try
        {
            await command();
            await PushStatusAsync();
        }
        catch (Exception error) when (error is IOException or InvalidOperationException or HttpRequestException or System.ComponentModel.Win32Exception)
        {
            MessageBox.Show(this, error.Message, "Soda Prompt Hub", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }

    private async Task RunNativeActionAsync(Func<Task> action)
    {
        try
        {
            await action();
        }
        catch (Exception error) when (error is IOException or InvalidOperationException or HttpRequestException or System.ComponentModel.Win32Exception)
        {
            if (!exitRequested && !IsDisposed)
            {
                MessageBox.Show(this, error.Message, "Soda Prompt Hub", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }
    }

    private void RunNativeAction(Action action)
    {
        try
        {
            action();
        }
        catch (Exception error) when (error is IOException or InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            MessageBox.Show(this, error.Message, "Soda Prompt Hub", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }

    private async Task RunTrayExportDiagnosticsAsync()
    {
        try
        {
            _ = await host.ExportDiagnosticsAsync();
        }
        catch (Exception error) when (error is IOException or InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            MessageBox.Show(this, error.Message, "Soda Prompt Hub", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }

    private void OnHostStatusChanged(object? sender, EventArgs eventArgs)
    {
        if (!exitRequested && !IsDisposed && IsHandleCreated)
        {
            BeginInvoke(new Action(async () => await PushStatusAsync()));
        }
    }

    private void OnFormClosing(object? sender, FormClosingEventArgs eventArgs)
    {
        if (allowClose || eventArgs.CloseReason == CloseReason.WindowsShutDown)
        {
            return;
        }
        eventArgs.Cancel = true;
        HideToTray();
    }

    private void HideToTray()
    {
        if (exitRequested)
        {
            return;
        }
        Hide();
        if (!trayHintShown)
        {
            trayHintShown = true;
            trayIcon.ShowBalloonTip(
                2500,
                "Soda Prompt Hub",
                "启动台已收起。Core 与本机 Worker 会继续在后台运行。",
                ToolTipIcon.Info);
        }
    }

    private void ExitShell()
    {
        if (exitRequested)
        {
            return;
        }
        exitRequested = true;
        allowClose = true;
        webReady = false;
        statusTimer.Stop();
        trayIcon.ContextMenuStrip?.Close();
        _ = Task.Run(async () =>
        {
            await Task.Delay(TimeSpan.FromSeconds(3));
            Environment.Exit(0);
        });
        BeginInvoke(new Action(() =>
        {
            Close();
            Application.ExitThread();
        }));
    }

    private async Task ExitAndStopAsync()
    {
        if (!await host.StopOwnedServicesAsync())
        {
            MessageBox.Show(
                this,
                "本机 Worker 正在执行任务，未停止任何服务。请等待结果回传后再退出并停止。",
                "Soda Prompt Hub",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            return;
        }
        ExitShell();
    }

    private void ShowInitializationError(string message)
    {
        webReady = false;
        statusTimer.Stop();
        webView.Visible = false;
        Controls.Add(new Label
        {
            Dock = DockStyle.Fill,
            ForeColor = Color.FromArgb(23, 24, 21),
            BackColor = Color.FromArgb(236, 232, 220),
            Font = new Font("Microsoft YaHei UI", 11),
            Padding = new Padding(48),
            TextAlign = ContentAlignment.MiddleCenter,
            Text = message,
        });
    }
}
