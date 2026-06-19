package ke.co.baziqhue.umd

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** One queued/running download, observable by the UI. */
class DlTask(val id: Long, val label: String, val audio: Boolean) {
    var status by mutableStateOf("queued")   // queued | running | done | failed
    var progress by mutableStateOf(0f)
    var detail by mutableStateOf("")
    var filePath by mutableStateOf<String?>(null)   // set on success → play/artwork
}

/**
 * App-wide download manager. Runs on an application-lifetime coroutine scope (NOT
 * a screen's scope), so downloads keep going no matter where the user navigates —
 * Download, Channel, History, Library, Assistant. The UI just observes [tasks].
 *
 * Downloads run one-at-a-time (a Mutex gate) to stay light; queue many and they
 * process in order.
 */
object Downloads {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val gate = Mutex()

    val tasks = mutableStateListOf<DlTask>()
    val activeCount: Int get() = tasks.count { it.status == "queued" || it.status == "running" }

    fun enqueue(ctx: Context, url: String, audio: Boolean, quality: String, label: String): DlTask {
        val app = ctx.applicationContext
        val t = DlTask(System.nanoTime(), label.ifBlank { url }, audio)
        tasks.add(0, t)
        scope.launch {
            gate.withLock {
                t.status = "running"; t.detail = "Starting…"
                val res = Downloader.download(app, url, audio, quality) { p, line ->
                    t.progress = if (p < 0) 0f else p / 100f
                    if (line.isNotBlank()) t.detail = line.take(90)
                }
                res.fold(
                    onSuccess = { out ->
                        out.file?.let { f ->
                            History.add(HistoryEntry(
                                f.nameWithoutExtension, url, audio, f.absolutePath, f.length(),
                                System.currentTimeMillis()))
                            t.filePath = f.absolutePath
                        }
                        t.status = "done"; t.progress = 1f
                        t.detail = out.file?.nameWithoutExtension ?: "Saved"
                    },
                    onFailure = { t.status = "failed"; t.detail = it.message ?: "Failed" }
                )
            }
        }
        return t
    }

    fun clearFinished() { tasks.removeAll { it.status == "done" || it.status == "failed" } }
}
