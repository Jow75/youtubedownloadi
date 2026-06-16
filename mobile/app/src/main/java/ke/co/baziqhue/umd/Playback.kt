package ke.co.baziqhue.umd

import android.content.ComponentName
import android.content.Context
import android.net.Uri
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

/**
 * Thin, Compose-friendly wrapper around a Media3 MediaController connected to
 * [PlaybackService]. Exposes observable playback state + simple commands so the
 * UI (mini-player + full player) stays in sync.
 */
object Playback {

    private var controller: MediaController? = null

    var ready by mutableStateOf(false); private set
    var hasItem by mutableStateOf(false); private set
    var isPlaying by mutableStateOf(false); private set
    var title by mutableStateOf(""); private set
    var shuffle by mutableStateOf(false); private set
    var repeatMode by mutableStateOf(Player.REPEAT_MODE_OFF); private set

    private val listener = object : Player.Listener {
        override fun onEvents(player: Player, events: Player.Events) = sync()
    }

    /** Connect to the background service (idempotent). Call once on launch. */
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
        shuffle = c.shuffleModeEnabled
        repeatMode = c.repeatMode
    }

    /** Replace the queue with [files] and start at [startIndex]. */
    fun play(files: List<File>, startIndex: Int = 0) {
        val c = controller ?: return
        if (files.isEmpty()) return
        val items = files.map { f ->
            MediaItem.Builder()
                .setUri(Uri.fromFile(f))
                .setMediaMetadata(MediaMetadata.Builder().setTitle(f.nameWithoutExtension).build())
                .build()
        }
        c.setMediaItems(items, startIndex.coerceIn(0, items.lastIndex), 0L)
        c.prepare()
        c.play()
    }

    fun playPause() {
        val c = controller ?: return
        if (c.isPlaying) c.pause() else c.play()
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

    fun position(): Long = controller?.currentPosition?.coerceAtLeast(0) ?: 0L
    fun duration(): Long = (controller?.duration ?: 0L).coerceAtLeast(0L)
}
