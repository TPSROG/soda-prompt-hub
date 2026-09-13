namespace SodaPromptHub.ComputeWorker;

internal static class BrandIcon
{
    internal static Icon Create()
    {
        using var stream = typeof(BrandIcon).Assembly.GetManifestResourceStream("PromptHub.AppIcon")
            ?? throw new InvalidOperationException("Missing Prompt Hub application icon.");
        using var icon = new Icon(stream, 32, 32);
        return (Icon)icon.Clone();
    }

}
