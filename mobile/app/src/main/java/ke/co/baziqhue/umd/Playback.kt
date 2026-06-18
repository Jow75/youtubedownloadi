package ke.co.baziqhue.umd

import android.content.ComponentName
import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.MoreExecutors
import java.io.File
import kotlin.math.abs

/**
 * Compose-friendly wrapper around a Media3 MediaController connected to
 * [PlaybackService]. Exposes observable playback state + commands for the
 * mini-player, the audio player, and the video player.
 */
object Playback {

    private val VIDEO_EXTS = setOf("mp4", "mkv", "webm", "mov", "avi", "m4v")
    private val SPEEDS = listOf(1f, 1.25f, 1.5f, 2f, 0.75f)

    private var controller: MediaController? = null
    private val handler = Handler(Looper.getMainLooper())
    private var sleepRunnable: Runnable? = null

    var ready by mutableStateOf(false); private set
    var hasItem by mutableStateOf(false); private set
    var isPlaying by mutableStateOf(false); private set
    var title by mutableStateOf(""); private set
    var currentPath by mutableStateOf(""); private set
    var isVideo by mutableStateOf(false); private set
    var showVideo by mutableStateOf(false)              // UI-settable: show the video screen
    var shuffle by mutableStateOf(false); private set
    var repeatMode by mutableStateOf(Player.REPEAT_MODE_OFF); private set
    var speed by mutableStateOf(1f); private set
    var sleepMinutes by mutableStateOf(0); private set  // 0 = off

    /** The underlying Player, for binding a video PlayerView. */
    fun player(): Player? = controller

    private val listener = object : Player.Listener {
        override fun onEvents(player: Player, events: Player.Events) = sync()
    }

    fun init(context: Context) {
        if (controller != null) return
        val app = context.applicationContext
        val token = SessionToken(app, ComponentName(app, PlaybackService::class.java))
        val future = MediaController.Builder(app, token).buildAsync()
        future.addListener({
            try {
                controller = future.get().also { it.addListener(listener) }
                ready = true
                sync()
            } catch (_: Exception) {
            }
        }, MoreExecutors.directExecutor())
    }

    private fun sync() {
        val c = controller ?: return
        hasItem = c.mediaItemCount > 0 && c.currentMediaItem != null
        isPlaying = c.isPlaying
        title = c.currentMediaItem?.mediaMetadata?.title?.toString() ?: ""
        currentPath = c.currentMediaItem?.mediaId.orEmpty()
        isVideo = File(currentPath).extension.lowercase() in VIDEO_EXTS
        shuffle = c.shuffleModeEnabled
        repeatMode = c.repeatMode
        speed = c.playbackParameters.speed
    }

    /** Replace the queue with [files] and start at [startIndex]. */
    fun play(files: List<File>, startIndex: Int = 0) {
        val c = controller ?: return
        if (files.isEmpty()) return
        val items = files.map { f ->
            MediaItem.Builder()
                .setMediaId(f.absolutePath)
                .setUri(Uri.fromFile(f))
                .setMediaMetadata(MediaMetadata.Builder().setTitle(f.nameWithoutExtension).build())
                .build()
        }
        val idx = startIndex.coerceIn(0, items.lastIndex)
        c.setMediaItems(items, idx, 0L)
        c.prepare()
        c.play()
        val startVideo = files[idx].extension.lowercase() in VIDEO_EXTS
        isVideo = startVideo
        showVideo = startVideo
    }

    fun playPause() {
        val c = controller ?: return
        if (c.isPlaying) c.pause() else c.play()
    }

    /** Fully close the session: stop, clear the queue, drop the notification + UI. */
    fun stop() {
        val c = controller ?: return
        scheduleSleep(0)
        c.stop()
        c.clearMediaItems()
        showVideo = false
        sync()
    }

    fun next() { controller?.seekToNextMediaItem() }
    fun prev() { controller?.seekToPreviousMediaItem() }
    fun seekTo(ms: Long) { controller?.seekTo(ms.coerceAtLeast(0)) }
    fun toggleShuffle() { controller?.let { it.shuffleModeEnabled = !it.shuffleModeEnabled } }

    fun cycleRepeat() {
        val c = controller ?: return
        c.repeatMode = when (c.repeatMode) {
            Player.REPEAT_MODE_OFF -> Player.REPEAT_MODE_ALL
            Player.REPEAT_MODE_ALL -> Player.REPEAT_MODE_ONE
            else -> Player.REPEAT_MODE_OFF
        }
    }

    fun cycleSpeed() {
        val c = controller ?: return
        val cur = c.playbackParameters.speed
        val i = SPEEDS.indexOfFirst { abs(it - cur) < 0.01f }
        val next = SPEEDS[(if (i < 0) 0 else i + 1) % SPEEDS.size]
        c.setPlaybackSpeed(next)
        speed = next
    }

    /** Pause playback after [minutes] (0 cancels). */
    fun scheduleSleep(minutes: Int) {
        sleepRunnable?.let { handler.removeCallbacks(it) }
        sleepMinutes = minutes.coerceAtLeast(0)
        if (sleepMinutes == 0) { sleepRunnable = null; return }
        val r = Runnable {
            controller?.pause()
            sleepMinutes = 0
            sleepRunnable = null
        }
        sleepRunnable = r
        handler.postDelayed(r, sleepMinutes * 60_000L)
    }

    fun position(): Long = controller?.currentPosition?.coerceAtLeast(0) ?: 0L
    fun duration(): Long = (controller?.duration ?: 0L).coerceAtLeast(0L)
}
