package ke.co.baziqhue.umd

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters

/**
 * Periodic background check (WorkManager, ~every 12h) for new uploads from the
 * channels the user follows. Cheap (2 quota units per channel, cached). Notifies
 * when a followed artist drops something new — the real "alert" for the follow
 * feature. Runs independently of the UI.
 */
class FollowWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        if (!Discover.hasKey()) return Result.success()
        Follows.ensureLoaded()
        val follows = Follows.all()
        if (follows.isEmpty()) return Result.success()

        val news = ArrayList<Pair<String, String>>()   // artist title -> new video title
        for (f in follows) {
            val ups = Discover.latestUploads(f.channelId).getOrNull()?.takeIf { it.isNotEmpty() } ?: continue
            val topId = ups.first().videoId
            when (val last = Follows.lastSeen(f.channelId)) {
                null -> Follows.setLastSeen(f.channelId, topId)        // baseline — no alert on first run
                topId -> { /* nothing new */ }
                else -> { Follows.setLastSeen(f.channelId, topId); news.add(f.title to ups.first().title) }
            }
        }
        if (news.isNotEmpty()) {
            val title = if (news.size == 1) "🆕 New from ${news[0].first}"
            else "🆕 ${news.size} new uploads from artists you follow"
            val text = news.take(4).joinToString(" · ") { "${it.first}: ${it.second}" }
            Notifications.followNotice(applicationContext, title, text)
        }
        return Result.success()
    }
}
