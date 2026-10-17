using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Windows.Forms;

static class Launcher
{
    const string Title = "VRChat Translator";
    const string Payload = "payload.zip";

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--extract-only")
            return Extract(args[1]) ? 0 : 1;

        string dir = AppDomain.CurrentDomain.BaseDirectory;
        if (!File.Exists(Path.Combine(dir, "app.py")))
        {
            string home = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                                       "VRChat Translator");
            if (!HasPayload())
            {
                MessageBox.Show("Рядом с этим файлом нет app.py.\n\nЗапускайте exe из папки переводчика " +
                                "(или через ярлык на него), не копируйте его отдельно.",
                                Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
            if (!Extract(home))
                return 1;
            dir = home;
        }
        Run(dir);
        return 0;
    }

    static bool HasPayload()
    {
        return Assembly.GetExecutingAssembly().GetManifestResourceInfo(Payload) != null;
    }

    static byte[] ReadPayload()
    {
        using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream(Payload))
        using (var m = new MemoryStream())
        {
            s.CopyTo(m);
            return m.ToArray();
        }
    }

    static bool Extract(string dir)
    {
        try
        {
            byte[] zip = ReadPayload();
            string version;
            using (var sha = SHA256.Create())
                version = BitConverter.ToString(sha.ComputeHash(zip)).Replace("-", "");
            string mark = Path.Combine(dir, "payload.version");
            if (File.Exists(mark) && File.ReadAllText(mark).Trim() == version && File.Exists(Path.Combine(dir, "app.py")))
                return true;
            Directory.CreateDirectory(dir);
            string root = Path.GetFullPath(dir + Path.DirectorySeparatorChar);
            using (var archive = new ZipArchive(new MemoryStream(zip), ZipArchiveMode.Read))
            {
                foreach (var entry in archive.Entries)
                {
                    string target = Path.GetFullPath(Path.Combine(dir, entry.FullName));
                    if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        continue;
                    if (entry.FullName.EndsWith("/"))
                    {
                        Directory.CreateDirectory(target);
                        continue;
                    }
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    entry.ExtractToFile(target, true);
                }
            }
            File.WriteAllText(mark, version);
            return true;
        }
        catch (Exception e)
        {
            MessageBox.Show("Не удалось распаковать переводчик в\n" + dir + "\n\n" + e.Message, Title,
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            return false;
        }
    }

    static void Run(string dir)
    {
        string app = Path.Combine(dir, "app.py");
        string pythonw = Path.Combine(dir, @".venv\Scripts\pythonw.exe");
        string install = Path.Combine(dir, "install.bat");

        if (!File.Exists(pythonw))
        {
            var answer = MessageBox.Show(
                "Первый запуск: нужно один раз скачать компоненты — Python (если его нет) и нейросети " +
                "для распознавания и перевода (около 3 ГБ, 5–15 минут, нужен интернет).\n\n" +
                "Установить сейчас?", Title, MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (answer != DialogResult.Yes)
                return;
            var setup = Process.Start(new ProcessStartInfo("cmd.exe", "/c \"\"" + install + "\"\"")
            {
                WorkingDirectory = dir,
                UseShellExecute = false,
            });
            setup.WaitForExit();
            if (!File.Exists(pythonw))
            {
                MessageBox.Show("Установка не завершилась. Посмотрите сообщения в окне установки и попробуйте ещё раз.",
                                Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
        }

        try
        {
            Process.Start(new ProcessStartInfo(pythonw, "\"" + app + "\"")
            {
                WorkingDirectory = dir,
                UseShellExecute = false,
            });
        }
        catch (Exception e)
        {
            MessageBox.Show("Не удалось запустить переводчик:\n\n" + e.Message, Title,
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
