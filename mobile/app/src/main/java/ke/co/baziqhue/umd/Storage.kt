package ke.co.baziqhue.umd

import android.Manifest
import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import android.widget.Toast
import androidx.core.content.FileProvider
import java.io.File

/**
 * Where downloads live and how the user reaches them.
 *
 * Files go to the PUBLIC Downloads tree — not the app-private
 * Android/data/<pkg>/files sandbox, which modern Android (and MIUI especially)
 * hides from the Files app. The layout mirrors the desktop app so the workflow
 * feels identical across devices:
 *
 *   Download/Universal Media Downloader/
 *     ├── Music/MP3/      (audio downloads)
 *     ├── Videos/MP4/     (video downloads)
 *     ├── Downloads/      (anything else)
 *     ├── History/        (download log)
 *     ├── Metadata/
 *     └── AI Library/
 *
 * Writing directly to public storage needs "All files access" on Android 11+
 * (or WRITE_EXTERNAL_STORAGE on 8–10). See [hasAccess] / [requestAllFilesAccess].
 */
object Storage {
    const val APP_FOLDER = "Universal Media Downloader"

    private val AUDIO_EXT = setOf("mp3", "m4a", "aac", "opus", "ogg", "wav", "flac")

    private fun downloads(): File =
        @Suppress("DEPRECATION")
        Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)

    fun base(): File = File(downloads(), APP_FOLDER)

    private fun ensure(d: File): File {
        if (!d.exists()) d.mkdirs()
        return d
    }

    fun audioDir(): File = ensure(File(base(), "Music/MP3"))
    fun videoDir(): File = ensure(File(base(), "Videos/MP4"))
    fun miscDir(): File = ensure(File(base(), "Downloads"))
    fun historyDir(): File = ensure(File(base(), "History"))
    fun metadataDir(): File = ensure(File(base(), "Metadata"))
    fun aiDir(): File = ensure(File(base(), "AI Library"))

    /** Lay down the full desktop-style folder tree so it's visible & predictable. */
    fun ensureTree() {
        if (!hasAccessQuiet()) return
        audioDir(); videoDir(); miscDir(); historyDir(); metadataDir(); aiDir()
    }

    private fun hasAccessQuiet(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.R || Environment.isExternalStorageManager()

    /** Can we write to the public Downloads tree right now? */
    fun hasAccess(ctx: Context): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
            Environment.isExternalStorageManager()
        else
            ctx.checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) ==
                PackageManager.PERMISSION_GRANTED

    /** Human path like "Download/Universal Media Downloader/Music/MP3". */
    fun displayPath(dir: File): String {
        val root = Environment.getExternalStorageDirectory().absolutePath
        return dir.absolutePath.removePrefix(root).removePrefix("/").replace('\\', '/')
    }

    /** Send the user to the "Allow all files access" toggle (Android 11+). */
    fun requestAllFilesAccess(ctx: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return
        val tries = listOf(
            Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                Uri.parse("package:${ctx.packageName}")),
            Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION),
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.parse("package:${ctx.packageName}")),
        )
        for (i in tries) {
            try {
                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                ctx.startActivity(i)
                return
            } catch (_: ActivityNotFoundException) {
            }
        }
    }

    private fun authority(ctx: Context) = "${ctx.packageName}.fileprovider"

    fun uriFor(ctx: Context, file: File): Uri =
        FileProvider.getUriForFile(ctx, authority(ctx), file)

    /** Make a freshly-written file show up in Files / Gallery / music players. */
    fun scan(ctx: Context, f: File) =
        MediaScannerConnection.scanFile(ctx, arrayOf(f.absolutePath), null, null)

    private fun mimeFor(file: File): String =
        if (file.extension.lowercase() in AUDIO_EXT) "audio/*" else "video/*"

    /** Play / open the file in whatever app the user prefers. */
    fun viewFile(ctx: Context, file: File) {
        try {
            val i = Intent(Intent.ACTION_VIEW)
                .setDataAndType(uriFor(ctx, file), mimeFor(file))
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            ctx.startActivity(Intent.createChooser(i, "Open with")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            toast(ctx, "Can't open: ${e.message}")
        }
    }

    fun shareFile(ctx: Context, file: File) {
        try {
            val i = Intent(Intent.ACTION_SEND)
                .setType(mimeFor(file))
                .putExtra(Intent.EXTRA_STREAM, uriFor(ctx, file))
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            ctx.startActivity(Intent.createChooser(i, "Share")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            toast(ctx, "Can't share: ${e.message}")
        }
    }

    /**
     * Best-effort "show me the folder". Android has no universal open-folder
     * intent, so we try the system Downloads UI (our files live under Download/…)
     * and otherwise just tell the user the path.
     */
    fun openFolder(ctx: Context, dir: File) {
        val attempts = listOf(
            { Intent(DownloadManager.ACTION_VIEW_DOWNLOADS) },
            { Intent(Intent.ACTION_VIEW).setDataAndType(uriFor(ctx, dir), "resource/folder") },
        )
        for (build in attempts) {
            try {
                val i = build().addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
                )
                ctx.startActivity(i)
                return
            } catch (_: Exception) {
            }
        }
        toast(ctx, "Open your Files app → ${displayPath(dir)}")
    }

    private fun toast(ctx: Context, m: String) =
        Toast.makeText(ctx, m, Toast.LENGTH_LONG).show()
}
