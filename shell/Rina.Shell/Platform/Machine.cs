using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Rina.Shell.Platform;

/// <summary>
/// Системные действия: громкость, медиа, питание, снимок экрана.
/// </summary>
/// <remarks>
/// <para>
/// Задачи плана <c>4.0-G01</c>, <c>G02</c>, <c>G03</c>. Решение —
/// [ADR 0009](../../../docs/adr/0009-system-layer.md): машину трогает
/// оболочка, а решает, что с ней сделать, ядро.
/// </para>
/// <para>
/// <b>Список закрыт и назван заранее.</b> Действие приходит по имени из
/// этой таблицы; ничего похожего на «выполни строку» здесь нет и не
/// появится. Именно этим системные действия отличаются от канала актуации
/// (§12): «прибавить громкость» нельзя направить не туда.
/// </para>
/// <para>
/// <b>Слова говорит ядро.</b> Отсюда наружу уходит факт — получилось или
/// нет; «Прибавила громкость» составит ядро, потому что это реплика Рины
/// ([ADR 0007](../../../docs/adr/0007-localisation.md)), а не отчёт
/// системы.
/// </para>
/// <para>
/// <b>Клавиши, а не микшер.</b> Громкость и медиа делаются теми же
/// сообщениями, что шлёт мультимедийная клавиатура: они уходят активному
/// приложению и работают одинаково с чем угодно — от плеера до браузера.
/// Управление громкостью через микшер трогало бы только собственный
/// сеанс Рины, у которой звука нет вовсе.
/// </para>
/// </remarks>
public static class Machine
{
    // Виртуальные коды мультимедийных клавиш.
    private const byte VkVolumeMute = 0xAD;
    private const byte VkVolumeDown = 0xAE;
    private const byte VkVolumeUp = 0xAF;
    private const byte VkMediaNext = 0xB0;
    private const byte VkMediaPrev = 0xB1;
    private const byte VkMediaPlayPause = 0xB3;

    private const uint KeyEventKeyUp = 0x0002;

    [DllImport("user32.dll")]
    private static extern void keybd_event(byte key, byte scan, uint flags,
                                           UIntPtr extra);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool LockWorkStation();

    /// <summary>Что оболочка умеет сделать с машиной.</summary>
    /// <remarks>
    /// Имена те же, что в <c>voice/system_control.py</c> версии 3.1.0:
    /// это одни и те же умения, переехавшие через границу процессов, и
    /// переименование стоило бы правки распознавания на пустом месте.
    /// </remarks>
    public static readonly string[] Actions =
    [
        "volume_up", "volume_down", "volume_mute",
        "media_next", "media_prev", "media_play_pause",
        "lock", "sleep", "shutdown", "restart", "screenshot",
    ];

    /// <summary>
    /// Сделать названное. Возвращает, получилось ли, и подробность.
    /// </summary>
    /// <remarks>
    /// Незнакомое имя — не исключение, а «нет такого действия»: ядро может
    /// оказаться новее оболочки, и падать из-за этого нельзя.
    /// </remarks>
    public static (bool Ok, string Detail) Do(string action)
    {
        try
        {
            switch (action)
            {
                case "volume_up": Tap(VkVolumeUp); return (true, "");
                case "volume_down": Tap(VkVolumeDown); return (true, "");
                case "volume_mute": Tap(VkVolumeMute); return (true, "");
                case "media_next": Tap(VkMediaNext); return (true, "");
                case "media_prev": Tap(VkMediaPrev); return (true, "");
                case "media_play_pause": Tap(VkMediaPlayPause); return (true, "");

                case "lock":
                    return LockWorkStation() ? (true, "")
                        : (false, "система не дала заблокировать");

                // Питание — через штатные средства Windows, а не через
                // ExitWindowsEx: те же права, то же поведение с открытыми
                // документами, и никакого своего обхода.
                case "sleep":
                    return Run("rundll32.exe", "powrprof.dll,SetSuspendState 0,1,0");
                case "shutdown":
                    return Run("shutdown.exe", "/s /t 0");
                case "restart":
                    return Run("shutdown.exe", "/r /t 0");

                case "screenshot":
                    var path = Screen.Grab();
                    return path.Length > 0 ? (true, path)
                        : (false, "не вышло снять экран");

                default:
                    return (false, "нет такого действия");
            }
        }
        catch (Exception error)
        {
            return (false, error.Message);
        }
    }

    /// <summary>Нужно ли подтверждение — по мнению оболочки.</summary>
    /// <remarks>
    /// Спрашивает всё равно ядро (§11): подтверждение — часть разговора, а
    /// не системного вызова. Здесь список нужен затем, чтобы оболочка
    /// могла отказать необратимому, пришедшему без подтверждения, — второй
    /// замок на случай, если первый однажды забудут повесить.
    /// </remarks>
    public static readonly HashSet<string> Irreversible =
        ["sleep", "shutdown", "restart"];

    private static void Tap(byte key)
    {
        keybd_event(key, 0, 0, UIntPtr.Zero);
        keybd_event(key, 0, KeyEventKeyUp, UIntPtr.Zero);
    }

    private static (bool Ok, string Detail) Run(string file, string arguments)
    {
        var started = Process.Start(new ProcessStartInfo
        {
            FileName = file,
            Arguments = arguments,
            UseShellExecute = false,
            CreateNoWindow = true,
        });
        return started is null ? (false, "процесс не запустился") : (true, "");
    }
}
