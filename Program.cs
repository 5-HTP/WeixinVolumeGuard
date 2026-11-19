using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Text.Json;
using System.Windows.Threading;
#pragma warning disable WPF0001

internal static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        var app = new Guard.App.App();
        app.InitializeComponent();
        var window = new Guard.App.MainWindow();
        window.ShowActivated = false;
        window.ShowInTaskbar = false;
        window.Show();
        var root = (FrameworkElement)window.Content;
        var tabs = Descendants(root).OfType<TabControl>().First();
        var output = Path.GetFullPath(args.Length > 0 ? args[0] : "artifacts/evidence/layout");
        Directory.CreateDirectory(output);
        var checks = new List<object>();
        foreach (var theme in new[] { ThemeMode.Light, ThemeMode.Dark })
        {
            window.ThemeMode = theme;
            foreach (int page in new[] { 0, 1, 2 })
            foreach (int percent in new[] { 100, 150, 200 })
            {
                tabs.SelectedIndex = page;
                window.Width = 680; window.Height = 540;
                window.UpdateLayout();
                root.Measure(new Size(664, 500)); root.Arrange(new Rect(0, 0, 664, 500)); root.UpdateLayout();
                app.Dispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
                window.UpdateLayout();
                var dpi = 96d * percent / 100;
                var bitmap = new RenderTargetBitmap((int)Math.Ceiling(root.ActualWidth * percent / 100), (int)Math.Ceiling(root.ActualHeight * percent / 100), dpi, dpi, PixelFormats.Pbgra32);
                var visual = new DrawingVisual();
                using (var drawing = visual.RenderOpen())
                {
                    var rectangle = new Rect(0,0,root.ActualWidth,root.ActualHeight);
                    drawing.DrawRectangle(theme == ThemeMode.Dark ? new SolidColorBrush(Color.FromRgb(32,32,32)) : new SolidColorBrush(Color.FromRgb(243,243,243)),null,rectangle);
                    drawing.DrawRectangle(new VisualBrush(root),null,rectangle);
                }
                bitmap.Render(visual);
                var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
                var file = Path.Combine(output, $"{theme}-page{page}-{percent}.png");
                using (var stream = File.Create(file)) encoder.Save(stream);
                var overlaps = Descendants(root).OfType<TextBlock>().Where(t => t.IsVisible && t.ActualWidth <= 0 && !string.IsNullOrEmpty(t.Text)).Count();
                checks.Add(new { theme = theme.ToString(), page, percent, zeroWidthVisibleText = overlaps, file });
            }
        }
        var retry = (Button)window.FindName("RetryButton");
        var details = Descendants(retry).Select(x => x.GetType().FullName).ToArray();
        File.WriteAllText(Path.Combine(output,"results.json"),JsonSerializer.Serialize(new { highContrast = SystemParameters.HighContrast, theme = window.ThemeMode.ToString(), buttonTree = details, checks },new JsonSerializerOptions { WriteIndented=true }));
        Console.WriteLine("Rendered 18 layout images. HighContrast=" + SystemParameters.HighContrast);
        window.FinishExit();
    }

    static IEnumerable<DependencyObject> Descendants(DependencyObject root)
    {
        for (int i=0;i<VisualTreeHelper.GetChildrenCount(root);i++)
        {
            var child = VisualTreeHelper.GetChild(root,i); yield return child;
            foreach (var descendant in Descendants(child)) yield return descendant;
        }
    }
}
