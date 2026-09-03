using System.IO;
using System.Runtime.InteropServices;

namespace Rina.Shell.Platform;

/// <summary>
/// Одна запись индекса программ.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-G09</c>. По записи должно быть видно, <b>откуда она
/// взялась и когда проверялась</b>: без этого нельзя ни предупредить о
/// неподписанном, ни вычистить устаревшее. В 3.1.0 запись состояла из
/// имени, пути, вида и источника — и всё; «откуда» было, «насколько
/// доверять» не было.
/// </para>
/// <para>
/// <b>Псевдонимы собирает оболочка, сопоставляет ядро.</b> Здесь лежат
/// только те имена, которые дала система: имя ярлыка, имя файла, название
/// из ресурсов. Разговорные («телеграм», «фотошоп») — дело ядра
/// ([ADR 0009](../../../docs/adr/0009-system-layer.md)).
/// </para>
/// </remarks>
public sealed record AppEntry
{
    /// <summary>Как программа называется для человека.</summary>
    public required string Name { get; init; }

    /// <summary>Что запускать: путь к файлу или AppID пакета.</summary>
    public required string Launch { get; init; }

    /// <summary>«file» или «uwp».</summary>
    public string Kind { get; init; } = "file";

    /// <summary>Откуда узнали: start_menu, app_paths, uwp, path, folder.</summary>
    public required string Source { get; init; }

    /// <summary>Имена от системы: ярлык, файл, ресурсы.</summary>
    public string[] Aliases { get; init; } = [];

    /// <summary>Подпись файла проверена системой и действительна.</summary>
    public bool Signed { get; init; }

    /// <summary>Когда запись проверяли в последний раз (UTC).</summary>
    public DateTime CheckedAt { get; init; } = DateTime.UtcNow;

    // --- проверка подписи ---------------------------------------------------

    private static readonly Guid VerifyAction =
        new("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");

    private const uint UiNone = 2;
    private const uint RevokeWholeChain = 1;
    private const uint ChoiceFile = 1;
    private const uint StateActionVerify = 1;
    private const uint StateActionClose = 2;
    private const uint SafeLifetimeSigning = 0x00000800;

    [StructLayout(LayoutKind.Sequential)]
    private struct FileInfoBlock
    {
        public uint Size;
        [MarshalAs(UnmanagedType.LPWStr)] public string FilePath;
        public IntPtr FileHandle;
        public IntPtr KnownSubject;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TrustData
    {
        public uint Size;
        public IntPtr PolicyCallbackData;
        public IntPtr SipClientData;
        public uint UiChoice;
        public uint RevocationChecks;
        public uint UnionChoice;
        public IntPtr FileInfoPointer;
        public uint StateAction;
        public IntPtr StateData;
        [MarshalAs(UnmanagedType.LPWStr)] public string? UrlReference;
        public uint ProviderFlags;
        public uint UiContext;
        public IntPtr SignatureSettings;
    }

    [DllImport("wintrust.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int WinVerifyTrust(IntPtr window, ref Guid action,
                                             ref TrustData data);

    // --- подпись каталогом --------------------------------------------------

    private const uint ChoiceCatalog = 2;

    [StructLayout(LayoutKind.Sequential)]
    private struct CatalogInfoBlock
    {
        public uint Size;
        public uint CatalogVersion;
        [MarshalAs(UnmanagedType.LPWStr)] public string CatalogFilePath;
        [MarshalAs(UnmanagedType.LPWStr)] public string MemberTag;
        [MarshalAs(UnmanagedType.LPWStr)] public string MemberFilePath;
        public IntPtr MemberFile;
        public IntPtr CalculatedFileHash;
        public uint HashLength;
        public IntPtr CatalogContext;
        public IntPtr CatAdmin;
    }

    // CharSet обязателен: `wszCatalogFile` — широкая строка, и без этого
    // `ByValTStr` читает её как однобайтовую. Путь к каталогу приходил
    // строкой «C» — первой буквой, за которой стоял нулевой байт.
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct CatalogInfo
    {
        public uint Size;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string CatalogFile;
    }

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern bool CryptCATAdminAcquireContext2(
        out IntPtr admin, IntPtr subsystem,
        [MarshalAs(UnmanagedType.LPWStr)] string? algorithm,
        IntPtr policy, uint flags);

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern bool CryptCATAdminCalcHashFromFileHandle2(
        IntPtr admin, IntPtr file, ref uint size, byte[]? hash, uint flags);

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern IntPtr CryptCATAdminEnumCatalogFromHash(
        IntPtr admin, byte[] hash, uint hashLength, uint flags,
        IntPtr previous);

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern bool CryptCATCatalogInfoFromContext(
        IntPtr context, ref CatalogInfo info, uint flags);

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern bool CryptCATAdminReleaseCatalogContext(
        IntPtr admin, IntPtr context, uint flags);

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern bool CryptCATAdminReleaseContext(IntPtr admin,
                                                           uint flags);

    /// <summary>
    /// Подписан ли файл каталогом.
    /// </summary>
    /// <remarks>
    /// Системные файлы Windows не носят подпись внутри себя: их хэши
    /// перечислены в каталоге, а подписан каталог. Проверка только
    /// встроенной подписи объявила бы неподписанной половину системы — и
    /// научила бы человека жать «всегда доверять», не читая.
    ///
    /// Здесь ищется каталог по хэшу файла и проверяется <b>он</b> — той же
    /// `WinVerifyTrust`, только с указанием, чей это член.
    /// </remarks>
    /// <summary>Где именно проверка каталога споткнулась — для разбора.</summary>
    public static string CatalogTrace(string path)
    {
        if (!CryptCATAdminAcquireContext2(out var admin, IntPtr.Zero,
                                          "SHA256", IntPtr.Zero, 0))
            return $"acquire=fail err={Marshal.GetLastWin32Error()}";
        try
        {
            using var file = File.OpenRead(path);
            var handle = file.SafeFileHandle.DangerousGetHandle();
            uint size = 0;
            CryptCATAdminCalcHashFromFileHandle2(admin, handle, ref size, null, 0);
            if (size == 0)
                return $"hashsize=0 err={Marshal.GetLastWin32Error()}";
            var hash = new byte[size];
            if (!CryptCATAdminCalcHashFromFileHandle2(admin, handle, ref size, hash, 0))
                return $"hash=fail err={Marshal.GetLastWin32Error()}";
            var catalog = CryptCATAdminEnumCatalogFromHash(admin, hash, size, 0, IntPtr.Zero);
            if (catalog == IntPtr.Zero)
                return $"catalog=none err={Marshal.GetLastWin32Error()}";
            var info = new CatalogInfo { Size = (uint)Marshal.SizeOf<CatalogInfo>(), CatalogFile = "" };
            if (!CryptCATCatalogInfoFromContext(catalog, ref info, 0))
                return $"info=fail err={Marshal.GetLastWin32Error()}";
            CryptCATAdminReleaseCatalogContext(admin, catalog, 0);
            return $"catalog={info.CatalogFile} verify={SignedByCatalog(path)}";
        }
        finally { CryptCATAdminReleaseContext(admin, 0); }
    }

    private static bool SignedByCatalog(string path)
    {
        if (!CryptCATAdminAcquireContext2(out var admin, IntPtr.Zero,
                                          "SHA256", IntPtr.Zero, 0))
            return false;

        var catalog = IntPtr.Zero;
        try
        {
            using var file = File.OpenRead(path);
            var handle = file.SafeFileHandle.DangerousGetHandle();

            uint size = 0;
            CryptCATAdminCalcHashFromFileHandle2(admin, handle, ref size,
                                                 null, 0);
            if (size == 0) return false;

            var hash = new byte[size];
            if (!CryptCATAdminCalcHashFromFileHandle2(admin, handle, ref size,
                                                      hash, 0))
                return false;

            catalog = CryptCATAdminEnumCatalogFromHash(admin, hash, size, 0,
                                                       IntPtr.Zero);
            if (catalog == IntPtr.Zero) return false;

            var info = new CatalogInfo
            {
                Size = (uint)Marshal.SizeOf<CatalogInfo>(),
                CatalogFile = "",
            };
            if (!CryptCATCatalogInfoFromContext(catalog, ref info, 0))
                return false;

            var tag = BitConverter.ToString(hash).Replace("-", "");
            var member = new CatalogInfoBlock
            {
                Size = (uint)Marshal.SizeOf<CatalogInfoBlock>(),
                CatalogVersion = 0,
                CatalogFilePath = info.CatalogFile,
                MemberTag = tag,
                MemberFilePath = path,
                MemberFile = handle,
                CalculatedFileHash = IntPtr.Zero,
                HashLength = 0,
                CatalogContext = IntPtr.Zero,
                CatAdmin = admin,
            };

            var block = Marshal.AllocHGlobal((int)member.Size);
            try
            {
                Marshal.StructureToPtr(member, block, false);
                var data = new TrustData
                {
                    Size = (uint)Marshal.SizeOf<TrustData>(),
                    UiChoice = UiNone,
                    RevocationChecks = RevokeWholeChain,
                    UnionChoice = ChoiceCatalog,
                    FileInfoPointer = block,
                    StateAction = StateActionVerify,
                    ProviderFlags = SafeLifetimeSigning,
                };
                var action = VerifyAction;
                var verdict = WinVerifyTrust(IntPtr.Zero, ref action, ref data);

                data.StateAction = StateActionClose;
                WinVerifyTrust(IntPtr.Zero, ref action, ref data);
                return verdict == 0;
            }
            finally
            {
                Marshal.FreeHGlobal(block);
            }
        }
        catch
        {
            return false;
        }
        finally
        {
            if (catalog != IntPtr.Zero)
                CryptCATAdminReleaseCatalogContext(admin, catalog, 0);
            CryptCATAdminReleaseContext(admin, 0);
        }
    }

    /// <summary>
    /// Действительна ли подпись Authenticode у файла.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Спрашивается система (<c>WinVerifyTrust</c>), а не разбор файла
    /// своими руками: проверить подпись значит пройти цепочку доверия,
    /// сверить отзыв и учесть политику машины, — и делать это самим значит
    /// делать хуже, чем уже сделано.
    /// </para>
    /// <para>
    /// Флаг «подпись действительна и после истечения сертификата» включён
    /// нарочно: сертификат, которым подписали программу три года назад,
    /// давно истёк, а программа от этого не стала неподписанной.
    /// </para>
    /// </remarks>
    public static bool HasSignature(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return false;

        var file = new FileInfoBlock
        {
            Size = (uint)Marshal.SizeOf<FileInfoBlock>(),
            FilePath = path,
        };
        var pointer = Marshal.AllocHGlobal((int)file.Size);
        try
        {
            Marshal.StructureToPtr(file, pointer, false);
            var data = new TrustData
            {
                Size = (uint)Marshal.SizeOf<TrustData>(),
                UiChoice = UiNone,
                RevocationChecks = RevokeWholeChain,
                UnionChoice = ChoiceFile,
                FileInfoPointer = pointer,
                StateAction = StateActionVerify,
                ProviderFlags = SafeLifetimeSigning,
            };

            var action = VerifyAction;
            var verdict = WinVerifyTrust(IntPtr.Zero, ref action, ref data);

            // Закрыть состояние обязательно: иначе провайдер оставит за
            // собой память и открытый файл на каждую проверку, а их здесь
            // сотни за одну переиндексацию.
            data.StateAction = StateActionClose;
            WinVerifyTrust(IntPtr.Zero, ref action, ref data);

            // Встроенной подписи нет — файл может быть подписан каталогом.
            // Порядок именно такой: встроенная дешевле, и у большинства
            // сторонних программ она и есть.
            return verdict == 0 || SignedByCatalog(path);
        }
        catch
        {
            // Нет wintrust, отказ провайдера, файл занят — всё это один и
            // тот же ответ: подтвердить подпись не удалось.
            return false;
        }
        finally
        {
            Marshal.FreeHGlobal(pointer);
        }
    }
}
