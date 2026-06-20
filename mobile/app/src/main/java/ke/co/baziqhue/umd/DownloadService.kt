package ke.co.baziqhue.umd

import android.app.Notification
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.compose.runtime.snapshotFlow
import androidx.core.app.NotificationManagerCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Foreground service that keeps the process (and therefore the [Downloads] queue
 * coroutines) alive while downloads are running — so they survive the screen going
 * off, app switching, and the app being swiped away. Shows a progress notification
 * ("Downloading N files…") and stops itself the moment the queue is empty, so it
 * never lingers or drains battery.
 */
class DownloadService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var observing = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForegroundCompat(
            Notifications.downloadOngoing(this, Downloads.activeCount, runningLabel(), runningProgress()))
        if (!observing) { observing = true; observe() }
        return START_STICKY
    }

    private fun runningTask() = Downloads.tasks.firstOrNull { it.status == "running" }
    private fun runningLabel() = runningTask()?.label ?: "Preparing…"
    private fun runningProgress() = ((runningTask()?.progress ?: 0f) * 100).toInt()

    private fun observe() {
        scope.launch {
            snapshotFlow { Triple(Downloads.activeCount, runningLabel(), runningProgress()) }
                .collect { (active, label, prog) ->
                    if (active == 0) {
                        val done = Downloads.tasks.count { it.status == "done" }
                        if (done > 0) Notifications.downloadComplete(this@DownloadService, done)
                        stopForeground(STOP_FOREGROUND_REMOVE)
                        stopSelf()
                    } else {
                        runCatching {
                            NotificationManagerCompat.from(this@DownloadService).notify(
                                Notifications.ID_DOWNLOAD,
                                Notifications.downloadOngoing(this@DownloadService, active, label, prog))
                        }
                    }
                }
        }
    }

    private fun startForegroundCompat(n: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
            startForeground(Notifications.ID_DOWNLOAD, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else
            startForeground(Notifications.ID_DOWNLOAD, n)
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
