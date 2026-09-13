using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace SodaPromptHub.ComputeWorker;

internal sealed class ShellForm : Form
{
    private static readonly Size DesignClientSize = new(860, 600);
    private static readonly Size DesignMinimumSize = new(776, 579);
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly WorkerHost host = new();
    private readonly WebView2 webView = new() { Dock = DockStyle.Fill };
    private readonly Icon brandIcon = BrandIcon.Create();
    private readonly NotifyIcon trayIcon;
    private readonly System.Windows.Forms.Timer statusTimer = new() { Interval = 2500 };
    private readonly SemaphoreSlim refreshGate = new(1, 1);
    private bool allowClose;
    private bool webReady;
    private bool trayHintShown;
    private bool exitRequested;

    internal ShellForm()
    {
        Text = "Soda Compute Worker";
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = DesignClientSize;
        MinimumSize = DesignMinimumSize;
        BackColor = Color.FromArgb(23, 24, 21);
        Icon = brandIcon;
        webView.DefaultBackgroundColor = Color.FromArgb(23, 24, 21);
        Controls.Add(webView);

        var trayMenu = new ContextMenuStrip();
        trayMenu.Items.Add("打开控制台", null, (_, _) => RestoreFromTray());
        trayMenu.Items.Add(new ToolStripSeparator());
        trayMenu.Items.Add("启动 Worker", null, async (_, _) => await RunTrayCommandAsync(host.StartAsync));
        trayMenu.Items.Add("停止 Worker", null, async (_, _) => await RunTrayCommandAsync(host.StopAsync));
        trayMenu.Items.Add("运行自检", null, async (_, _) => await RunTrayCommandAsync(host.SelfTestAsync));
        trayMenu.Items.Add(new ToolStripSeparator());
        trayMenu.Items.Add("打开日志", null, (_, _) => RunNativeAction(host.OpenLogs));
        trayMenu.Items.Add("导出诊断包", null, async (_, _) => await RunTrayExportDiagnosticsAsync());
        trayMenu.Items.Add("打开配置", null, (_, _) => RunNativeAction(host.OpenConfig));
        trayMenu.Items.Add(new ToolStripSeparator());
        trayMenu.Items.Add("退出控制台（Worker 继续）", null, (_, _) => ExitShell());
        trayMenu.Items.Add("退出并停止 Worker", null, async (_, _) => await ExitAndStopAsync());

        trayIcon = new NotifyIcon
        {
            Text = "Soda Compute Worker",
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
                "WorkerShell",
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
                var startupStatus = await host.GetStatusAsync();
                if (startupStatus.TryGetValue("canPrimary", out var canStart) && canStart is true
                    && Convert.ToString(startupStatus["primaryCommand"]) == "startWorker")
                {
                    await host.StartAsync();
                    await PushStatusAsync();
                }
            };
            core.Navigate("https://soda.local/index.html?product=worker");
        }
        catch (Exception error) when (error is WebView2RuntimeNotFoundException or InvalidOperationException or IOException)
        {
            ShowInitializationError($"无法启动图形界面。请安装 Microsoft Edge WebView2 Runtime。\n\n{error.Message}");
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
                case "startWorker":
                    payload = StatusPayload(await host.StartAsync());
                    break;
                case "stopWorker":
                    payload = StatusPayload(await host.StopAsync());
                    break;
                case "selfTestWorker":
                    payload = StatusPayload(await host.SelfTestAsync());
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
                    host.OpenBridge();
                    payload = StatusPayload(await host.GetStatusAsync());
                    break;
                case "openConfig":
                    host.OpenConfig();
                    payload = StatusPayload(await host.GetStatusAsync());
                    break;
                case "getWorkerConfig":
                    payload = new Dictionary<string, object?> { ["config"] = host.GetEditableConfig() };
                    break;
                case "chooseFolder":
                    var initial = parameters.ValueKind == JsonValueKind.Object
                        && parameters.TryGetProperty("initial", out var initialValue)
                        ? initialValue.GetString() ?? string.Empty
                        : string.Empty;
                    payload = new Dictionary<string, object?> { ["path"] = ChooseFolder(initial) };
                    break;
                case "getPairingInfo":
                    payload = await Task.Run(host.GetPairingInfo);
                    break;
                case "openShareFolder":
                    host.OpenShareFolder();
                    payload = new { message = "已打开待共享文件夹。请右键此文件夹 → 属性 → 共享，由你确认权限。" };
                    break;
                case "copyPairingAddress":
                    var pairing = await Task.Run(host.GetPairingInfo);
                    var addresses = (List<string>)pairing["addresses"]!;
                    if (addresses.Count == 0) throw new InvalidOperationException("尚未检测到可复制的共享地址。");
                    Clipboard.SetText(addresses[0]);
                    payload = new { message = "连接地址已复制，不含账号密码。" };
                    break;
                case "saveWorkerConfig":
                    if (parameters.ValueKind != JsonValueKind.Object
                        || !parameters.TryGetProperty("config", out var configValue)
                        || configValue.ValueKind != JsonValueKind.Object)
                    {
                        throw new InvalidOperationException("图形配置数据无效。");
                    }
                    host.SaveConfig(configValue);
                    payload = StatusPayload(await host.StartAsync());
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
        catch (Exception error) when (error is JsonException or KeyNotFoundException or IOException or InvalidOperationException or System.ComponentModel.Win32Exception)
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

    private Task ResolveAsync(string id, object payload)
    {
        return ExecuteDesktopFunctionAsync("resolve", id, payload);
    }

    private Task RejectAsync(string id, string message)
    {
        return ExecuteDesktopFunctionAsync("reject", id, message);
    }

    private static Dictionary<string, object?> StatusPayload(Dictionary<string, object?> status)
    {
        return new Dictionary<string, object?> { ["status"] = status };
    }

    private string? ChooseFolder(string initial)
    {
        using var dialog = new FolderBrowserDialog
        {
            Description = "选择 Soda Compute Worker 使用的目录",
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
        catch (Exception error)
        {
            MessageBox.Show(this, error.Message, "Soda Compute Worker", MessageBoxButtons.OK, MessageBoxIcon.Warning);
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
            MessageBox.Show(this, error.Message, "Soda Compute Worker", MessageBoxButtons.OK, MessageBoxIcon.Warning);
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
            MessageBox.Show(this, error.Message, "Soda Compute Worker", MessageBoxButtons.OK, MessageBoxIcon.Warning);
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
                "Soda Compute Worker",
                "控制台已收起。Worker 会继续在后台运行。",
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
        if (host.HasActiveTask())
        {
            MessageBox.Show(
                this,
                "任务正在执行，未停止 Worker。请等待结果回传后再退出并停止。",
                "Soda Compute Worker",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            return;
        }
        await host.StopAsync();
        if (host.IsOwnedProcessRunning())
        {
            RestoreFromTray();
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
            ForeColor = Color.FromArgb(244, 237, 223),
            BackColor = Color.FromArgb(23, 24, 21),
            Font = new Font("Microsoft YaHei UI", 11),
            Padding = new Padding(48),
            TextAlign = ContentAlignment.MiddleCenter,
            Text = message,
        });
    }
}
