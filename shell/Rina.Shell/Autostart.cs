using Microsoft.Win32;

namespace Rina.Shell;

/// <summary>
/// Запуск при входе в систему.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-F05</c>.
/// </para>
/// <para>
/// <b>Ветка текущего пользователя, а не машины.</b> `HKCU` не требует прав
/// администратора и не касается других людей за этим компьютером: Рина —
/// личный помощник, и заводить её всем сразу никто не просил.
/// </para>
/// <para>
/// <b>Своё имя записи, и чужих мы не трогаем.</b> Запись называется так же,
/// как программа; всё остальное в этой ветке принадлежит другим программам,
/// и перебирать её в поисках «похожего на нас» — способ однажды удалить
/// чужое.
/// </para>
/// <para>
/// Настройка живёт в ядре (`autostart`), а исполняет её оболочка: реестр —
/// система, а системный слой в 4.0 принадлежит оболочке. Ядро хранит
/// намерение, оболочка приводит систему в соответствие.
/// </para>
/// </remarks>
public static class Autostart
{
    private const string Branch =
        @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string Name = "RinaAssistant";

    /// <summary>Стоит ли запись сейчас.</summary>
    public static bool Enabled
    {
        get
        {
            try
            {
                using var key = Registry.CurrentUser.OpenSubKey(Branch);
                return key?.GetValue(Name) is not null;
            }
            catch
            {
                return false;
            }
        }
    }

    /// <summary>Что именно будет запущено.</summary>
    public static string Command
    {
        get
        {
            var exe = Environment.ProcessPath ?? "";
            // Кавычки обязательны: путь почти наверняка содержит пробел, и
            // без них система запустит «C:\Program».
            return exe.Length > 0 ? $"\"{exe}\"" : "";
        }
    }

    /// <summary>Привести систему в соответствие настройке. `true` — получилось.</summary>
    public static bool Apply(bool wanted)
    {
        try
        {
            using var key = Registry.CurrentUser.CreateSubKey(Branch, true);
            if (key is null) return false;

            if (wanted)
            {
                if (Command.Length == 0) return false;
                key.SetValue(Name, Command, RegistryValueKind.String);
            }
            else if (key.GetValue(Name) is not null)
            {
                key.DeleteValue(Name, throwOnMissingValue: false);
            }
            return true;
        }
        catch
        {
            // Групповая политика может запретить запись. Молчать нельзя, но
            // и падать не за чем: вызывающий покажет, что не вышло.
            return false;
        }
    }
}
