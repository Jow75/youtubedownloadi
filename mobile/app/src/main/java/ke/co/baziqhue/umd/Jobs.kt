package ke.co.baziqhue.umd

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

enum class JobStatus { RUNNING, DONE, FAILED }

/** One background AI/processing job, observable by the UI. */
class Job(val id: Long, val label: String) {
    var status by mutableStateOf(JobStatus.RUNNING)
    var progress by mutableStateOf(-1f)   // -1 = indeterminate
    var detail by mutableStateOf("")
}

/**
 * App-wide background-work engine. Runs on an application-lifetime coroutine scope
 * (NOT a screen's scope), so AI analysis, playlist building, duplicate scans and
 * channel triage KEEP RUNNING no matter where the user navigates — or even if they
 * leave the screen entirely. Results land in the observable holders below, so the
 * screen shows them again when the user comes back.
 *
 * This mirrors the download manager [Downloads]; the two together mean nothing the
 * app starts is tied to the visible screen.
 */
object Jobs {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    val items = mutableStateListOf<Job>()
    val activeCount: Int get() = items.count { it.status == JobStatus.RUNNING }

    /** Launch [block] on the app scope, tracked as a [Job]. Survives navigation. */
    fun launch(label: String, block: suspend (Job) -> Unit): Job {
        val job = Job(System.nanoTime(), label)
        items.add(0, job)
        scope.launch {
            try {
                block(job)
                if (job.status == JobStatus.RUNNING) job.status = JobStatus.DONE
            } catch (e: Exception) {
                job.status = JobStatus.FAILED
                job.detail = e.message ?: "Failed"
            }
        }
        return job
    }

    fun clearFinished() { items.removeAll { it.status != JobStatus.RUNNING } }
}

// --------------------------------------------------------------------------- //
// App-level result holders. Because these are singletons (not composable state),
// the work writes here and the screens read here — so navigating away and back
// never loses an in-flight or finished AI result.
// --------------------------------------------------------------------------- //

/** One AI rename suggestion for the Title clean-up tool. */
class CleanupSuggestion(
    val path: String,
    val from: String,
    val suggested: String,
    val category: String,
) {
    var selected by mutableStateOf(true)
    var done by mutableStateOf(false)
}

/** Title clean-up results + progress, survives tab switches. */
object CleanupJob {
    var running by mutableStateOf(false)
    var status by mutableStateOf("")
    val results = mutableStateListOf<CleanupSuggestion>()
    fun reset() { results.clear(); status = "" }
}

/** Duplicate-scan results + progress, survives tab switches. */
object DedupJob {
    var running by mutableStateOf(false)
    var scanned by mutableStateOf(false)
    var status by mutableStateOf("")
    val groups = mutableStateListOf<DupGroup>()
}

/** Auto-playlist (genre/language/mood) build progress, survives tab switches. */
object AutoPlaylistJob {
    var running by mutableStateOf(false)
    var status by mutableStateOf("")
}

/** Channel AI triage results — title -> category / is-official, survives tab switches. */
object ChannelTriage {
    var running by mutableStateOf(false)
    var status by mutableStateOf("")
    var classified by mutableStateOf(0)
    var total by mutableStateOf(0)
    val categories = mutableStateMapOf<String, String>()    // entry title -> category
    val official = mutableStateMapOf<String, Boolean>()     // entry title -> is official release
    fun reset() { categories.clear(); official.clear(); status = ""; classified = 0; total = 0 }
}
