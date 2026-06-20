package ke.co.baziqhue.umd

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

/** Notification channels + builders for downloads and follow-upload alerts. */
object Notifications {

    const val CH_DOWNLOADS = "umd_downloads"
    const val CH_FOLLOWS = "umd_follows"
    const val ID_DOWNLOAD = 1001
    const val ID_FOLLOW = 1002

    fun ensureChannels(ctx: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = ctx.getSystemService(NotificationManager::class.java) ?: return
        nm.createNotificationChannel(NotificationChannel(CH_DOWNLOADS, "Downloads",
            NotificationManager.IMPORTANCE_LOW).apply { description = "Download progress" })
        nm.createNotificationChannel(NotificationChannel(CH_FOLLOWS, "New uploads",
            NotificationManager.IMPORTANCE_DEFAULT).apply { description = "New uploads from artists you follow" })
    }

    private fun openApp(ctx: Context): PendingIntent {
        val i = ctx.packageManager.getLaunchIntentForPackage(ctx.packageName)
            ?: Intent(ctx, MainActivity::class.java)
        return PendingIntent.getActivity(ctx, 0, i,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    /** The ongoing notification for the download foreground service. */
    fun downloadOngoing(ctx: Context, active: Int, label: String, progress: Int): Notification {
        ensureChannels(ctx)
        return NotificationCompat.Builder(ctx, CH_DOWNLOADS)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle("Universal Media Downloader")
            .setContentText(if (active <= 1) label else "Downloading $active files — $label")
            .setProgress(100, progress.coerceIn(0, 100), progress <= 0)
            .setOngoing(true).setOnlyAlertOnce(true)
            .setContentIntent(openApp(ctx))
            .build()
    }

    @SuppressLint("MissingPermission")
    fun downloadComplete(ctx: Context, count: Int) {
        ensureChannels(ctx)
        val n = NotificationCompat.Builder(ctx, CH_DOWNLOADS)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle("Downloads complete")
            .setContentText("$count file(s) saved to your library")
            .setAutoCancel(true).setContentIntent(openApp(ctx))
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(ID_DOWNLOAD, n) }
    }

    @SuppressLint("MissingPermission")
    fun followNotice(ctx: Context, title: String, text: String) {
        ensureChannels(ctx)
        val n = NotificationCompat.Builder(ctx, CH_FOLLOWS)
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle(title).setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setAutoCancel(true).setContentIntent(openApp(ctx))
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(ID_FOLLOW, n) }
    }
}
