package ke.co.baziqhue.umd

import android.Manifest
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Repeat
import androidx.compose.material.icons.filled.RepeatOne
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.Shuffle
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material.icons.filled.Subscriptions
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            UmdTheme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    // Makes all read-only text selectable/copyable (long-press to
                    // select → Copy). Text fields keep their own paste/selection.
                    SelectionContainer { App() }
                }
            }
        }
    }
}

/** Download-screen state, hoisted so a tab switch never cancels an in-flight download. */
class DownloadUi {
    var url by mutableStateOf("")
    var audio by mutableStateOf(true)
    var quality by mutableStateOf("Best")
    var busy by mutableStateOf(false)
    var progress by mutableStateOf(0f)
    var log by mutableStateOf("")
    var done by mutableStateOf<Downloader.Outcome?>(null)
    // AI error-helper state
    var failure by mutableStateOf<String?>(null)
    var aiBusy by mutableStateOf(false)
    var aiExplanation by mutableStateOf<String?>(null)
}

/** Channel / Bulk tab state, hoisted so a scan or AI sort survives tab switches. */
class ChannelUi {
    var mode by mutableStateOf(0)            // 0 = Channel/Profile, 1 = Bulk
    var url by mutableStateOf("")
    var audio by mutableStateOf(true)
    var quality by mutableStateOf("Best")
    var scanning by mutableStateOf(false)
    var status by mutableStateOf("")
    val entries = mutableStateListOf<Downloader.Entry>()
    var query by mutableStateOf("")
    var page by mutableStateOf(0)
    val selected = mutableStateListOf<String>()   // selected entry urls
    var categoryFilter by mutableStateOf("All")
}

/** Bulk paste-and-go state, hoisted so the queued list survives tab switches. */
class BulkUi {
    var videoLinks by mutableStateOf("")
    var audioLinks by mutableStateOf("")
    var quality by mutableStateOf("Best")
    var status by mutableStateOf("")
}

/**
 * One line in the assistant chat. [filePath] is set on a completed download so the
 * bubble becomes tappable — opens it in the Library and starts playing.
 */
data class ChatMsg(val fromUser: Boolean, val text: String, val filePath: String? = null)

/** One conversation. Each artist/topic can have its own, ChatGPT-style. */
class ChatSession(val id: String, title: String, messages: List<ChatMsg> = emptyList()) {
    var title by mutableStateOf(title)
    val messages = mutableStateListOf<ChatMsg>().also { it.addAll(messages) }
}

/** Assistant state, hoisted so it survives tab switches / in-flight replies. */
class AssistantUi {
    val sessions = mutableStateListOf<ChatSession>()
    var currentId by mutableStateOf("")
    var input by mutableStateOf("")
    var busy by mutableStateOf(false)
    var loaded = false

    val current: ChatSession?
        get() = sessions.firstOrNull { it.id == currentId } ?: sessions.firstOrNull()

    fun ensureChat() {
        if (sessions.none { it.id == currentId }) {
            if (sessions.isEmpty()) newChat() else currentId = sessions.first().id
        }
    }

    fun newChat() {
        val s = ChatSession(System.nanoTime().toString(), "New chat")
        sessions.add(0, s); currentId = s.id; input = ""
    }

    fun delete(id: String) {
        sessions.removeAll { it.id == id }
        if (currentId == id) currentId = sessions.firstOrNull()?.id.orEmpty()
    }

    fun deleteAll() { sessions.clear(); currentId = ""; newChat() }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun App() {
    val ctx = LocalContext.current
    val lm = remember { LicenseManager(ctx) }
    var licensed by remember { mutableStateOf(lm.isLicensed()) }

    if (!licensed) {
        LicenseGate(lm) { licensed = true }
        return
    }

    // Licensed: a tabbed shell. State + coroutine scope live here so they persist
    // across tab switches (a download or chat reply keeps running).
    val scope = rememberCoroutineScope()
    val ui = remember { DownloadUi() }
    val channel = remember { ChannelUi() }
    val bulk = remember { BulkUi() }
    val assistant = remember { AssistantUi() }
    var tab by remember { mutableStateOf(0) }
    var showAbout by remember { mutableStateOf(false) }
    var showPlayer by remember { mutableStateOf(false) }
    var showAiKey by remember { mutableStateOf(false) }
    val sections = listOf("Download", "Channel / Bulk", "History", "Library", "Assistant")
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val notifLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(Unit) {
        Playback.init(ctx)
        Favorites.ensureLoaded()
        Playlists.ensureLoaded()
        PlayStats.ensureLoaded()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
    fun go(i: Int) { tab = i; scope.launch { drawer.close() } }

    ModalNavigationDrawer(
        drawerState = drawer,
        drawerContent = {
            ModalDrawerSheet {
                Column(Modifier.fillMaxWidth().padding(16.dp)) {
                    Text("Universal Media Downloader",
                        style = MaterialTheme.typography.titleLarge)
                    Text(lm.status(), style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                HorizontalDivider()
                Spacer(Modifier.height(8.dp))
                val drawerIcons = listOf(Icons.Filled.Download, Icons.Filled.Subscriptions,
                    Icons.Filled.Schedule, Icons.Filled.AutoAwesome)
                sections.forEachIndexed { i, name ->
                    NavigationDrawerItem(
                        label = { Text(name) }, selected = tab == i,
                        icon = {
                            Icon(if (i < drawerIcons.size) drawerIcons[i]
                                else Icons.AutoMirrored.Filled.Chat, contentDescription = null)
                        },
                        onClick = { go(i) },
                        modifier = Modifier.padding(horizontal = 12.dp)
                    )
                }
                HorizontalDivider()
                Spacer(Modifier.height(8.dp))
                NavigationDrawerItem(
                    label = { Text("AI assistant settings") }, selected = false,
                    icon = { Icon(Icons.Filled.AutoAwesome, contentDescription = null) },
                    onClick = { showAiKey = true; scope.launch { drawer.close() } },
                    modifier = Modifier.padding(horizontal = 12.dp)
                )
                NavigationDrawerItem(
                    label = { Text("About") }, selected = false,
                    icon = { Icon(Icons.Filled.Info, contentDescription = null) },
                    onClick = { showAbout = true; scope.launch { drawer.close() } },
                    modifier = Modifier.padding(horizontal = 12.dp)
                )
            }
        }
    ) {

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Universal Media Downloader",
                            style = MaterialTheme.typography.titleMedium)
                        Text(sections[tab], style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary)
                    }
                },
                navigationIcon = {
                    IconButton(onClick = { scope.launch { drawer.open() } }) {
                        Icon(Icons.Filled.Menu, contentDescription = "Menu")
                    }
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        },
        bottomBar = {
            Column {
                AiJobsBar { tab = 3 }
                DownloadsBar { tab = 0 }
                MiniPlayer { if (Playback.isVideo) Playback.showVideo = true else showPlayer = true }
                NavigationBar {
                NavigationBarItem(
                    selected = tab == 0, onClick = { tab = 0 },
                    icon = { Icon(Icons.Filled.Download, contentDescription = null) },
                    label = { Text("Download") })
                NavigationBarItem(
                    selected = tab == 1, onClick = { tab = 1 },
                    icon = { Icon(Icons.Filled.Subscriptions, contentDescription = null) },
                    label = { Text("Channel") })
                NavigationBarItem(
                    selected = tab == 2, onClick = { tab = 2 },
                    icon = { Icon(Icons.Filled.Schedule, contentDescription = null) },
                    label = { Text("History") })
                NavigationBarItem(
                    selected = tab == 3, onClick = { tab = 3 },
                    icon = { Icon(Icons.Filled.AutoAwesome, contentDescription = null) },
                    label = { Text("Library") })
                NavigationBarItem(
                    selected = tab == 4, onClick = { tab = 4 },
                    icon = { Icon(Icons.AutoMirrored.Filled.Chat, contentDescription = null) },
                    label = { Text("Assistant") })
                }
            }
        }
    ) { pad ->
        Crossfade(targetState = tab, animationSpec = tween(260), label = "tab",
            modifier = Modifier.fillMaxSize().padding(pad)) { t ->
            Box(Modifier.fillMaxSize()) {
                when (t) {
                    0 -> DownloadScreen(lm, ui, scope) { licensed = false }
                    1 -> ChannelBulkScreen(channel, bulk)
                    2 -> HistoryScreen { url, audio ->
                        ui.url = url; ui.audio = audio; ui.done = null; tab = 0
                    }
                    3 -> LibraryScreen()
                    else -> AssistantScreen(assistant, scope) { path ->
                        val f = File(path)
                        if (f.exists()) { playInApp(ctx, listOf(f), f); tab = 3 }
                    }
                }
            }
        }
    }
    }

    if (showAbout) AboutDialog(ctx, lm) { showAbout = false }
    if (showAiKey) AiKeyDialog(ctx) { showAiKey = false }
    if (showPlayer && Playback.hasItem && !Playback.isVideo) PlayerScreen { showPlayer = false }
    if (Playback.showVideo && Playback.hasItem) VideoPlayerScreen { Playback.showVideo = false }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LicenseGate(lm: LicenseManager, onActivated: () -> Unit) {
    val ctx = LocalContext.current
    val clip = LocalClipboardManager.current
    val deviceId = remember { lm.deviceId() }
    var key by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf<String?>(null) }
    var ok by remember { mutableStateOf(false) }

    Column(
        Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Spacer(Modifier.height(8.dp))
        Text("Universal Media Downloader", style = MaterialTheme.typography.headlineSmall)
        Text("Activate this device", style = MaterialTheme.typography.titleMedium)
        Text("Send the publisher this device's ID, paste the license key you get " +
            "back, and tap Activate.")

        OutlinedCard {
            Column(Modifier.padding(14.dp)) {
                Text("This device's ID", style = MaterialTheme.typography.labelMedium)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(deviceId, fontFamily = FontFamily.Monospace,
                        style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                    IconButton(onClick = { clip.setText(AnnotatedString(deviceId)) }) {
                        Icon(Icons.Filled.ContentCopy, "Copy device ID")
                    }
                }
            }
        }

        OutlinedTextField(
            value = key, onValueChange = { key = it },
            label = { Text("License key (UMDL-…)") },
            singleLine = true, modifier = Modifier.fillMaxWidth()
        )
        Button(
            onClick = {
                val (success, m) = lm.activate(key)
                ok = success; msg = m
                if (success) onActivated()
            },
            enabled = key.isNotBlank(), modifier = Modifier.fillMaxWidth()
        ) { Text("Activate") }

        msg?.let {
            Text(it, color = if (ok) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.error)
        }

        HorizontalDivider()
        Text("Need a license / upgrade?", style = MaterialTheme.typography.titleMedium)
        ContactLinks(ctx)
        Text("Universal Media Downloader v1.0 · Published by George (Jowgei), Kenya",
            style = MaterialTheme.typography.bodySmall)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DownloadScreen(lm: LicenseManager, ui: DownloadUi, scope: CoroutineScope, onDeactivated: () -> Unit) {
    val ctx = LocalContext.current
    var engineStatus by remember { mutableStateOf("") }
    var showAiKey by remember { mutableStateOf(false) }

    // Auto-refresh the (bundled, fast-stale) yt-dlp engine on launch so YouTube/
    // TikTok work without the user racing the "Update engine" button.
    LaunchedEffect(Unit) {
        Downloader.prepareEngine(ctx) { s -> engineStatus = s }
        engineStatus = ""
    }

    // Public-storage access is required to save where the user can browse.
    var hasStorage by remember { mutableStateOf(Storage.hasAccess(ctx)) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { hasStorage = Storage.hasAccess(ctx) }
    LaunchedEffect(hasStorage) { if (hasStorage) Storage.ensureTree() }
    val permLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> hasStorage = granted }

    Column(
        Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(lm.status(), style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)

        if (engineStatus.isNotBlank()) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                Text(engineStatus, style = MaterialTheme.typography.bodySmall)
            }
        }

        if (!hasStorage) {
            ElevatedCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Allow storage access", style = MaterialTheme.typography.titleMedium)
                    Text("So your music & videos save to a folder you can open in your " +
                        "Files app (Download/Universal Media Downloader) — not a hidden " +
                        "app folder — grant storage access.",
                        style = MaterialTheme.typography.bodySmall)
                    Button(
                        onClick = {
                            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
                                Storage.requestAllFilesAccess(ctx)
                            else
                                permLauncher.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) { Text("Grant storage access") }
                }
            }
        }

        OutlinedTextField(
            value = ui.url, onValueChange = { ui.url = it },
            label = { Text("Paste a link (YouTube, X, TikTok…)") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri)
        )

        // Format: Audio is the primary choice (left), Video second.
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            SegmentedButton(
                selected = ui.audio, onClick = { ui.audio = true },
                shape = SegmentedButtonDefaults.itemShape(0, 2)
            ) { Text("🎵 Audio (MP3)") }
            SegmentedButton(
                selected = !ui.audio, onClick = { ui.audio = false },
                shape = SegmentedButtonDefaults.itemShape(1, 2)
            ) { Text("🎬 Video (MP4)") }
        }
        if (!ui.audio) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("Best", "720p", "480p").forEach {
                    FilterChip(selected = ui.quality == it, onClick = { ui.quality = it },
                        label = { Text(it) })
                }
            }
        }

        BrandButton(
            onClick = {
                val reqUrl = ui.url.trim()
                if (reqUrl.isNotBlank()) {
                    Downloads.enqueue(ctx, reqUrl, ui.audio, ui.quality, reqUrl)
                    ui.url = ""
                }
            },
            enabled = ui.url.isNotBlank() && hasStorage,
            modifier = Modifier.fillMaxWidth()
        ) {
            Icon(Icons.Filled.Download, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Download")
        }

        // Live downloads — they keep running in the background on every tab.
        DownloadsList(ctx, scope) { showAiKey = true }

        Spacer(Modifier.height(8.dp))
        Text("Saves to: ${Storage.displayPath(Downloader.targetDir(ui.audio))}",
            style = MaterialTheme.typography.bodySmall)
        OutlinedButton(
            onClick = { Storage.openFolder(ctx, Downloader.targetDir(ui.audio)) },
            modifier = Modifier.fillMaxWidth()
        ) { Text("📂 Open downloads folder") }

        OutlinedButton(
            onClick = { scope.launch { Downloader.updateEngine(ctx) } },
            modifier = Modifier.fillMaxWidth()
        ) { Text("Update download engine (yt-dlp)") }

        HorizontalDivider()
        ContactLinks(ctx, websiteOnly = true)
        TextButton(onClick = { lm.deactivate(); onDeactivated() }) {
            Text("Remove license from this device")
        }
    }

    if (showAiKey) AiKeyDialog(ctx) { showAiKey = false }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryScreen(onRedownload: (url: String, audio: Boolean) -> Unit) {
    val ctx = LocalContext.current
    var query by remember { mutableStateOf("") }
    var entries by remember { mutableStateOf(emptyList<HistoryEntry>()) }
    fun refresh() { entries = History.all() }
    // Reload whenever this screen comes to the foreground.
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { refresh() }
    LaunchedEffect(Unit) { refresh() }

    val filtered = entries.filter {
        query.isBlank() || it.title.contains(query, true) || it.url.contains(query, true)
    }

    Column(
        Modifier.fillMaxSize().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        if (entries.isEmpty()) {
            Text("No downloads yet. Finished downloads show up here — and the list " +
                "lives in your History folder, so it survives reinstalls.",
                style = MaterialTheme.typography.bodyMedium)
            return@Column
        }

        OutlinedTextField(
            value = query, onValueChange = { query = it },
            label = { Text("Search history") }, singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("${filtered.size} of ${entries.size}", style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.weight(1f))
            TextButton(onClick = { History.clear(); refresh() }) { Text("Clear log") }
        }
        Text("Download log — clearing it keeps your media safe in the Library.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)

        val playQueue = filtered.map { File(it.path) }
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.weight(1f).fillMaxWidth()
        ) {
            items(filtered) { e ->
                HistoryRow(ctx, e, playQueue, onRedownload) { History.remove(e); refresh() }
            }
        }
    }
}

@Composable
fun HistoryRow(
    ctx: android.content.Context,
    e: HistoryEntry,
    queue: List<File>,
    onRedownload: (String, Boolean) -> Unit,
    onDelete: () -> Unit,
) {
    val f = File(e.path)
    val exists = f.exists()
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text((if (e.audio) "🎵 " else "🎬 ") + e.title.ifBlank { f.name },
                style = MaterialTheme.typography.titleSmall, maxLines = 2)
            Text(formatTime(e.timestamp) + "  ·  " + humanSize(e.sizeBytes) +
                (if (!exists) "  ·  (file moved/deleted)" else ""),
                style = MaterialTheme.typography.bodySmall)
            Text(Storage.displayPath(f.parentFile ?: f),
                fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (exists) {
                    OutlinedButton(onClick = { playInApp(ctx, queue, f) },
                        modifier = Modifier.weight(1f), contentPadding = PaddingValues(4.dp)) { Text("▶ Play") }
                    OutlinedButton(onClick = { Storage.shareFile(ctx, f) },
                        modifier = Modifier.weight(1f), contentPadding = PaddingValues(4.dp)) { Text("↗ Share") }
                }
                OutlinedButton(onClick = { onRedownload(e.url, e.audio) },
                    modifier = Modifier.weight(1f), contentPadding = PaddingValues(4.dp)) { Text("↻ Again") }
                OutlinedButton(onClick = onDelete,
                    modifier = Modifier.weight(1f), contentPadding = PaddingValues(4.dp)) { Text("🗑 Remove") }
            }
        }
    }
}

private fun formatTime(ts: Long): String =
    if (ts <= 0) "" else SimpleDateFormat("MMM d, yyyy HH:mm", Locale.US).format(Date(ts))

private fun humanSize(bytes: Long): String = when {
    bytes <= 0 -> "—"
    bytes < 1024 -> "$bytes B"
    bytes < 1024 * 1024 -> "%.0f KB".format(bytes / 1024.0)
    bytes < 1024L * 1024 * 1024 -> "%.1f MB".format(bytes / (1024.0 * 1024))
    else -> "%.2f GB".format(bytes / (1024.0 * 1024 * 1024))
}

private val LIB_SORTS =
    listOf("Newest", "Oldest", "A–Z", "Artist", "Largest", "Recently played", "Most played")

private fun sortLibrary(list: List<File>, sort: Int): List<File> = when (sort) {
    1 -> list.sortedBy { it.lastModified() }
    2 -> list.sortedBy { it.nameWithoutExtension.lowercase() }
    3 -> list.sortedBy { MediaMeta.artist(it).lowercase() }
    4 -> list.sortedByDescending { it.length() }
    5 -> list.sortedByDescending { PlayStats.lastPlayed(it.absolutePath) }
    6 -> list.sortedByDescending { PlayStats.count(it.absolutePath) }
    else -> list.sortedByDescending { it.lastModified() }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var refreshKey by remember { mutableStateOf(0) }
    var aiOn by remember { mutableStateOf(false) }
    var showAiKey by remember { mutableStateOf(false) }
    var category by remember { mutableStateOf(0) }  // 0 Songs,1 Videos,2 Favorites,3 Playlists,4 Artists,5 Tools
    var query by remember { mutableStateOf("") }
    var sort by remember { mutableStateOf(0) }
    var sortMenu by remember { mutableStateOf(false) }
    var openPlaylist by remember { mutableStateOf<String?>(null) }
    var openArtist by remember { mutableStateOf<String?>(null) }
    var selecting by remember { mutableStateOf(false) }
    val selected = remember { mutableStateListOf<String>() }
    var addTarget by remember { mutableStateOf<List<String>?>(null) }

    // The library IS the filesystem — independent of the History log.
    val allFiles = remember(refreshKey) { Library.mediaFiles() }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { refreshKey++; aiOn = Ai.isConfigured(ctx) }
    LaunchedEffect(Unit) { aiOn = Ai.isConfigured(ctx); Playlists.ensureLoaded(); PlayStats.ensureLoaded() }
    // Warm the artist cache off the main thread (MediaMetadataRetriever is slow).
    LaunchedEffect(allFiles) {
        withContext(Dispatchers.IO) { allFiles.forEach { if (isAudioFile(it)) MediaMeta.artist(it) } }
    }

    fun exitSelect() { selecting = false; selected.clear() }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Spacer(Modifier.height(8.dp))
        Row(Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("All Songs", "Videos", "Favorites", "Playlists", "Artists", "Tools")
                .forEachIndexed { i, lbl ->
                    FilterChip(selected = category == i, onClick = {
                        category = i; openPlaylist = null; openArtist = null; exitSelect()
                    }, label = { Text(lbl) })
                }
        }
        Spacer(Modifier.height(8.dp))

        Box(Modifier.weight(1f).fillMaxWidth()) {
        when {
            category == 5 -> {
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (!aiOn) {
                        ElevatedCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text("Smart search and title clean-up use the AI assistant.",
                                    style = MaterialTheme.typography.bodyMedium)
                                Button(onClick = { showAiKey = true }, modifier = Modifier.fillMaxWidth()) {
                                    Text("🤖 Set up AI key")
                                }
                            }
                        }
                    }
                    SmartSearchSection(ctx, scope, allFiles, aiOn) { showAiKey = true }
                    DuplicatesSection(ctx, scope)
                    TitleCleanupSection(ctx, scope, allFiles, aiOn, { showAiKey = true }) { refreshKey++ }
                    Spacer(Modifier.height(16.dp))
                }
            }
            category == 3 && openPlaylist == null -> PlaylistsList(ctx, scope,
                allFiles.filter { isAudioFile(it) }, aiOn, { showAiKey = true }) { openPlaylist = it }
            category == 3 -> PlaylistDetail(openPlaylist!!) { openPlaylist = null }
            category == 4 && openArtist == null -> ArtistsList(allFiles) { openArtist = it }
            else -> Column(Modifier.fillMaxSize()) {
                val source = when {
                    category == 4 -> allFiles.filter { isAudioFile(it) && MediaMeta.artist(it).equals(openArtist, true) }
                    category == 1 -> allFiles.filter { !isAudioFile(it) }
                    category == 2 -> { val fav = Favorites.all().toHashSet(); allFiles.filter { it.absolutePath in fav } }
                    else -> allFiles.filter { isAudioFile(it) }
                }
                val files = sortLibrary(source, sort)
                    .filter { query.isBlank() || it.nameWithoutExtension.contains(query, true) }

                if (category == 4 && openArtist != null) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = { openArtist = null; exitSelect() }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                        Text(openArtist!!, style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.weight(1f), maxLines = 1)
                    }
                }

                OutlinedTextField(query, { query = it }, label = { Text("Search") },
                    singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box {
                        OutlinedButton(onClick = { sortMenu = true }) { Text("Sort: ${LIB_SORTS[sort]}") }
                        DropdownMenu(expanded = sortMenu, onDismissRequest = { sortMenu = false }) {
                            LIB_SORTS.forEachIndexed { i, n ->
                                DropdownMenuItem(text = { Text(n) }, onClick = { sort = i; sortMenu = false })
                            }
                        }
                    }
                    Spacer(Modifier.weight(1f))
                    if (files.isNotEmpty()) {
                        TextButton(onClick = { selecting = !selecting; if (!selecting) selected.clear() }) {
                            Text(if (selecting) "Done" else "Select")
                        }
                    }
                }

                if (selecting) {
                    val selFiles = files.filter { it.absolutePath in selected }
                    Row(verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                        TextButton(onClick = {
                            if (selected.size == files.size) selected.clear()
                            else { selected.clear(); selected.addAll(files.map { it.absolutePath }) }
                        }) { Text("All") }
                        Text("${selected.size}", style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.weight(1f))
                        IconButton(enabled = selFiles.isNotEmpty(), onClick = { Playback.play(selFiles, 0) }) {
                            Icon(Icons.Filled.PlayArrow, "Play")
                        }
                        IconButton(enabled = selFiles.isNotEmpty(), onClick = { addTarget = selected.toList() }) {
                            Icon(Icons.Filled.Add, "Add to playlist")
                        }
                        IconButton(enabled = selFiles.isNotEmpty(), onClick = { Storage.shareFiles(ctx, selFiles) }) {
                            Icon(Icons.Filled.Share, "Share")
                        }
                        IconButton(enabled = selFiles.isNotEmpty(), onClick = {
                            selFiles.forEach { if (it.delete()) Storage.scan(ctx, it) }
                            exitSelect(); refreshKey++
                        }) { Icon(Icons.Filled.Delete, "Delete") }
                    }
                } else if (files.isNotEmpty()) {
                    Button(onClick = { Playback.play(files, 0) }, modifier = Modifier.fillMaxWidth()) {
                        Icon(Icons.Filled.PlayArrow, contentDescription = null)
                        Spacer(Modifier.width(8.dp)); Text("Play all (${files.size})")
                    }
                }
                Spacer(Modifier.height(8.dp))

                if (files.isEmpty()) {
                    Text("Nothing here yet. Downloads stay in your library permanently — " +
                        "clearing History won't remove them.",
                        style = MaterialTheme.typography.bodyMedium)
                }
                LazyColumn(Modifier.weight(1f).fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    items(files, key = { it.absolutePath }) { f ->
                        LibraryFileRow(ctx, f, files, selecting,
                            isSelected = f.absolutePath in selected,
                            onToggle = {
                                if (f.absolutePath in selected) selected.remove(f.absolutePath)
                                else selected.add(f.absolutePath)
                            })
                    }
                }
            }
        }
        }
    }

    addTarget?.let { paths -> AddToPlaylistDialog(paths) { addTarget = null; exitSelect() } }
    if (showAiKey) AiKeyDialog(ctx) { showAiKey = false }
}

@Composable
private fun LibraryFileRow(
    ctx: android.content.Context,
    f: File,
    queue: List<File>,
    selecting: Boolean,
    isSelected: Boolean,
    onToggle: () -> Unit,
) {
    val fav = Favorites.isFavorite(f.absolutePath)
    val audio = isAudioFile(f)
    Row(
        Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium)
            .clickable { if (selecting) onToggle() else playInApp(ctx, queue, f) }
            .padding(horizontal = 6.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (selecting) {
            Checkbox(checked = isSelected, onCheckedChange = { onToggle() })
            Spacer(Modifier.width(2.dp))
        }
        MediaArtwork(f, size = 52.dp, corner = 11.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(f.nameWithoutExtension, style = MaterialTheme.typography.bodyMedium, maxLines = 2)
            Text(if (audio) MediaMeta.artist(f) else "Video",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
        }
        if (!selecting) {
            IconButton(onClick = { Favorites.toggle(f.absolutePath) }) {
                Icon(if (fav) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                    contentDescription = "Favorite",
                    tint = if (fav) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.onSurfaceVariant)
            }
            FilledIconButton(onClick = { playInApp(ctx, queue, f) }) {
                Icon(Icons.Filled.PlayArrow, contentDescription = "Play")
            }
        }
    }
}

@Composable
private fun PlaylistsList(
    ctx: android.content.Context,
    scope: CoroutineScope,
    audioFiles: List<File>,
    aiOn: Boolean,
    onNeedKey: () -> Unit,
    onOpen: (String) -> Unit,
) {
    var newDialog by remember { mutableStateOf(false) }
    var renameId by remember { mutableStateOf<String?>(null) }
    val lists = Playlists.all()

    Column(Modifier.fillMaxSize()) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { newDialog = true }, modifier = Modifier.weight(1f),
                shape = MaterialTheme.shapes.large) {
                Icon(Icons.Filled.Add, contentDescription = null)
                Spacer(Modifier.width(8.dp)); Text("New")
            }
            OutlinedButton(
                onClick = {
                    when {
                        !aiOn -> onNeedKey()
                        audioFiles.isEmpty() -> AutoPlaylistJob.status = "No songs to group yet."
                        else -> {
                            AutoPlaylistJob.running = true
                            AutoPlaylistJob.status = "Analyzing your library…"
                            // App-scope: keeps grouping even if you leave the Library tab.
                            Jobs.launch("Smart playlists") {
                                val names = audioFiles.map { it.nameWithoutExtension }
                                Ai.classifyTracks(ctx, names) { d, t ->
                                    AutoPlaylistJob.status = "Analyzing $d / $t…"
                                }.fold(
                                    onSuccess = { map ->
                                        val groups = LinkedHashMap<String, MutableList<String>>()
                                        fun add(name: String, path: String) {
                                            groups.getOrPut(name) { mutableListOf() }.add(path)
                                        }
                                        audioFiles.forEach { f ->
                                            val tg = map[f.nameWithoutExtension] ?: return@forEach
                                            if (tg.genre.isNotBlank() && !tg.genre.equals("other", true))
                                                add("🎵 ${tg.genre}", f.absolutePath)
                                            if (tg.language.isNotBlank() && !tg.language.equals("unknown", true))
                                                add("🗣 ${tg.language}", f.absolutePath)
                                            if (tg.mood.isNotBlank() && !tg.mood.equals("unknown", true))
                                                add("💫 ${tg.mood}", f.absolutePath)
                                        }
                                        var n = 0
                                        groups.forEach { (name, paths) ->
                                            if (paths.size >= 2) {
                                                val pl = Playlists.all().firstOrNull { it.name == name }
                                                    ?: Playlists.create(name)
                                                Playlists.addPaths(pl.id, paths); n++
                                            }
                                        }
                                        AutoPlaylistJob.status = if (n == 0) "Not enough songs to group yet."
                                        else "Built $n smart playlists by genre, language & mood."
                                    },
                                    onFailure = { AutoPlaylistJob.status = "Failed: ${it.message}" }
                                )
                                AutoPlaylistJob.running = false
                            }
                        }
                    }
                },
                enabled = !AutoPlaylistJob.running, modifier = Modifier.weight(1f),
                shape = MaterialTheme.shapes.large
            ) {
                Icon(Icons.Filled.AutoAwesome, contentDescription = null)
                Spacer(Modifier.width(6.dp)); Text(if (AutoPlaylistJob.running) "Working…" else "Auto (AI)")
            }
        }
        if (AutoPlaylistJob.status.isNotBlank()) {
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (AutoPlaylistJob.running) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                Text(AutoPlaylistJob.status, style = MaterialTheme.typography.bodySmall)
            }
        }
        Spacer(Modifier.height(8.dp))
        if (lists.isEmpty()) {
            Text("No playlists yet. Create one, add songs from any list (Select → +), or " +
                "tap Auto (AI) to group your library by genre, language and mood.",
                style = MaterialTheme.typography.bodyMedium)
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.weight(1f)) {
            items(lists, key = { it.id }) { pl ->
                var menu by remember { mutableStateOf(false) }
                ElevatedCard(Modifier.fillMaxWidth().clickable { onOpen(pl.id) }) {
                    Row(Modifier.padding(start = 14.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f).padding(vertical = 10.dp)) {
                            Text(pl.name, style = MaterialTheme.typography.titleSmall, maxLines = 1)
                            Text("${pl.paths.size} song(s)", style = MaterialTheme.typography.bodySmall)
                        }
                        IconButton(onClick = {
                            val files = pl.paths.map { File(it) }.filter { it.exists() }
                            if (files.isNotEmpty()) Playback.play(files, 0)
                        }) { Icon(Icons.Filled.PlayArrow, "Play") }
                        Box {
                            IconButton(onClick = { menu = true }) { Icon(Icons.Filled.MoreVert, "More") }
                            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                                DropdownMenuItem(text = { Text("Rename") },
                                    onClick = { menu = false; renameId = pl.id })
                                DropdownMenuItem(text = { Text("Delete") },
                                    onClick = { menu = false; Playlists.delete(pl.id) })
                            }
                        }
                    }
                }
            }
        }
    }
    if (newDialog) {
        PlaylistNameDialog("New playlist", "") { name ->
            if (name != null) Playlists.create(name); newDialog = false
        }
    }
    renameId?.let { id ->
        PlaylistNameDialog("Rename playlist", Playlists.get(id)?.name ?: "") { name ->
            if (name != null) Playlists.rename(id, name); renameId = null
        }
    }
}

@Composable
private fun PlaylistDetail(id: String, onBack: () -> Unit) {
    val pl = Playlists.get(id)
    val paths = pl?.paths?.toList() ?: emptyList()
    val existing = paths.map { File(it) }.filter { it.exists() }
    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
            Text(pl?.name ?: "Playlist", style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f), maxLines = 1)
            if (existing.isNotEmpty()) {
                TextButton(onClick = { Playback.play(existing, 0) }) {
                    Icon(Icons.Filled.PlayArrow, null); Spacer(Modifier.width(4.dp)); Text("Play")
                }
            }
        }
        if (paths.isEmpty()) {
            Text("Empty. Add songs from any list: tap Select, pick songs, then +.",
                style = MaterialTheme.typography.bodyMedium)
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.weight(1f)) {
            itemsIndexed(paths, key = { _, p -> p }) { i, p ->
                val f = File(p); val ok = f.exists()
                ElevatedCard(Modifier.fillMaxWidth().clickable {
                    if (ok) Playback.play(existing, existing.indexOf(f).coerceAtLeast(0))
                }) {
                    Row(Modifier.padding(start = 12.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(f.nameWithoutExtension + (if (!ok) "  (missing)" else ""),
                            style = MaterialTheme.typography.bodyMedium, maxLines = 2,
                            modifier = Modifier.weight(1f).padding(vertical = 6.dp))
                        IconButton(enabled = i > 0, onClick = { Playlists.move(id, i, i - 1) }) {
                            Icon(Icons.Filled.KeyboardArrowUp, "Up")
                        }
                        IconButton(enabled = i < paths.lastIndex, onClick = { Playlists.move(id, i, i + 1) }) {
                            Icon(Icons.Filled.KeyboardArrowDown, "Down")
                        }
                        IconButton(onClick = { Playlists.removePath(id, p) }) {
                            Icon(Icons.Filled.Close, "Remove")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ArtistsList(allFiles: List<File>, onOpen: (String) -> Unit) {
    var artists by remember { mutableStateOf<List<Pair<String, Int>>?>(null) }
    LaunchedEffect(allFiles) {
        artists = withContext(Dispatchers.IO) {
            allFiles.filter { isAudioFile(it) }.groupBy { MediaMeta.artist(it) }
                .map { it.key to it.value.size }
                .sortedWith(compareByDescending<Pair<String, Int>> { it.second }
                    .thenBy { it.first.lowercase() })
        }
    }
    when (val a = artists) {
        null -> Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
            Text("Reading artist tags…", style = MaterialTheme.typography.bodySmall)
        }
        else -> if (a.isEmpty()) {
            Text("No songs yet.", style = MaterialTheme.typography.bodyMedium)
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxSize()) {
                items(a, key = { it.first }) { (name, count) ->
                    ElevatedCard(Modifier.fillMaxWidth().clickable { onOpen(name) }) {
                        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(name, style = MaterialTheme.typography.titleSmall,
                                modifier = Modifier.weight(1f), maxLines = 1)
                            Text("$count song(s)", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddToPlaylistDialog(paths: List<String>, onDone: () -> Unit) {
    var newName by remember { mutableStateOf("") }
    val lists = Playlists.all()
    AlertDialog(
        onDismissRequest = onDone,
        confirmButton = {
            TextButton(onClick = {
                if (newName.isNotBlank()) {
                    val p = Playlists.create(newName); Playlists.addPaths(p.id, paths)
                }
                onDone()
            }) { Text("Done") }
        },
        title = { Text("Add ${paths.size} to playlist") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(4.dp)) {
                lists.forEach { pl ->
                    TextButton(onClick = { Playlists.addPaths(pl.id, paths); onDone() },
                        modifier = Modifier.fillMaxWidth()) {
                        Text("${pl.name}  (${pl.paths.size})", modifier = Modifier.fillMaxWidth())
                    }
                }
                HorizontalDivider()
                OutlinedTextField(newName, { newName = it },
                    label = { Text("…or new playlist name") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth())
            }
        }
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PlaylistNameDialog(title: String, initial: String, onResult: (String?) -> Unit) {
    var name by remember { mutableStateOf(initial) }
    AlertDialog(
        onDismissRequest = { onResult(null) },
        confirmButton = { TextButton(onClick = { onResult(name) }, enabled = name.isNotBlank()) { Text("Save") } },
        dismissButton = { TextButton(onClick = { onResult(null) }) { Text("Cancel") } },
        title = { Text(title) },
        text = {
            OutlinedTextField(name, { name = it }, label = { Text("Name") }, singleLine = true,
                modifier = Modifier.fillMaxWidth())
        }
    )
}

@Composable
private fun SmartSearchSection(
    ctx: android.content.Context,
    scope: CoroutineScope,
    files: List<File>,
    aiOn: Boolean,
    onNeedKey: () -> Unit,
) {
    var indexed by remember { mutableStateOf(0) }
    var status by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<File>>(emptyList()) }
    LaunchedEffect(files.size) { indexed = SearchIndex.indexedCount() }
    val names = files.map { it.nameWithoutExtension }

    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("🔎 Smart search", style = MaterialTheme.typography.titleMedium)
            Text("Find media by meaning, not exact words — e.g. \"that calm " +
                "piano study music\".", style = MaterialTheme.typography.bodySmall)
            Text("Indexed: $indexed / ${files.size}", style = MaterialTheme.typography.bodySmall)

            OutlinedButton(
                onClick = {
                    if (!aiOn) onNeedKey() else {
                        busy = true; status = "Indexing…"
                        scope.launch {
                            val r = SearchIndex.build(ctx, names) { d, t ->
                                status = "Indexing $d / $t…"
                            }
                            indexed = SearchIndex.indexedCount()
                            busy = false
                            status = r.fold({ "Index ready ($indexed)." }, { "Failed: ${it.message}" })
                        }
                    }
                },
                enabled = !busy && files.isNotEmpty(), modifier = Modifier.fillMaxWidth()
            ) { Text("Build / refresh search index") }

            OutlinedTextField(
                value = query, onValueChange = { query = it },
                label = { Text("Search by meaning") }, singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Button(
                onClick = {
                    if (!aiOn) onNeedKey() else {
                        busy = true; status = "Searching…"
                        scope.launch {
                            val r = SearchIndex.search(ctx, query.trim(), names)
                            results = r.getOrDefault(emptyList()).mapNotNull { (name, _) ->
                                files.firstOrNull { it.nameWithoutExtension == name }
                            }
                            busy = false
                            status = r.fold(
                                { if (results.isEmpty()) "No matches (build the index first?)." else "" },
                                { "Failed: ${it.message}" })
                        }
                    }
                },
                enabled = !busy && query.isNotBlank(), modifier = Modifier.fillMaxWidth()
            ) { Text("Search") }

            if (busy) Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                Text(status, style = MaterialTheme.typography.bodySmall)
            } else if (status.isNotBlank()) {
                Text(status, style = MaterialTheme.typography.bodySmall)
            }

            results.forEach { f ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text((if (isAudioFile(f)) "🎵 " else "🎬 ") + f.nameWithoutExtension,
                        style = MaterialTheme.typography.bodyMedium, maxLines = 2,
                        modifier = Modifier.weight(1f))
                    TextButton(onClick = { playInApp(ctx, results, f) }) { Text("▶ Play") }
                }
            }
        }
    }
}

@Composable
private fun DuplicatesSection(ctx: android.content.Context, scope: CoroutineScope) {
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("🧹 Duplicate cleanup", style = MaterialTheme.typography.titleMedium)
            Text("Finds repeats in your library — both byte-identical copies and the " +
                "same song saved twice (e.g. an MP3 and an MP4, or a re-download). " +
                "Keeps one, you delete the rest.", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Button(
                onClick = {
                    DedupJob.running = true; DedupJob.status = "Scanning your library…"
                    DedupJob.groups.clear()
                    Jobs.launch("Duplicate scan") {
                        val found = Library.findDuplicates()
                        DedupJob.groups.clear(); DedupJob.groups.addAll(found)
                        DedupJob.scanned = true; DedupJob.running = false
                        DedupJob.status = if (found.isEmpty()) "No duplicates found 🎉"
                        else "Found ${found.size} group(s) of duplicates."
                    }
                },
                enabled = !DedupJob.running, modifier = Modifier.fillMaxWidth(),
                shape = MaterialTheme.shapes.large
            ) {
                if (DedupJob.running) {
                    CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary)
                    Spacer(Modifier.width(8.dp))
                }
                Text(if (DedupJob.running) "Scanning…" else "Scan for duplicates")
            }

            if (DedupJob.status.isNotBlank()) {
                Text(DedupJob.status, style = MaterialTheme.typography.bodyMedium)
            }
            DedupJob.groups.forEachIndexed { gi, group ->
                HorizontalDivider()
                Text("${group.reason} — ${group.files.size}× \"${group.files.first().nameWithoutExtension}\"",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary)
                group.files.forEachIndexed { i, f ->
                    var deleted by remember(f.absolutePath) { mutableStateOf(!f.exists()) }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text((if (i == 0) "✓ keep  " else "• ") + f.name +
                            (if (deleted) "  (deleted)" else ""),
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.weight(1f))
                        if (i > 0 && !deleted) {
                            TextButton(onClick = {
                                if (f.delete()) { Storage.scan(ctx, f); deleted = true }
                            }) { Text("Delete") }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TitleCleanupSection(
    ctx: android.content.Context,
    scope: CoroutineScope,
    files: List<File>,
    aiOn: Boolean,
    onNeedKey: () -> Unit,
    onChanged: () -> Unit,
) {
    // Rename a single suggestion; records it so it won't be suggested again.
    fun applyOne(s: CleanupSuggestion) {
        if (s.done) return
        val old = File(s.path)
        if (!old.exists()) { s.done = true; return }
        val nf = Library.rename(old, s.suggested)
        if (nf != null) {
            Storage.scan(ctx, old); Storage.scan(ctx, nf)
            CleanState.markRenamed(old, nf)
            s.done = true
        }
    }

    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("🏷️ Title clean-up", style = MaterialTheme.typography.titleMedium)
            Text("AI suggests a clean \"Artist — Title\" for messy filenames. Rename them " +
                "all in one tap, or pick which. Files you've already cleaned won't be " +
                "suggested again.", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)

            Button(
                onClick = onClick@{
                    if (!aiOn) { onNeedKey(); return@onClick }
                    CleanupJob.reset(); CleanupJob.running = true
                    CleanupJob.status = "Analyzing titles…"
                    Jobs.launch("Title clean-up") {
                        CleanState.ensureLoaded()
                        // Skip files already cleaned/ignored (and unchanged since).
                        val todo = files.filter { !CleanState.isHandled(it) }
                        if (todo.isEmpty()) {
                            CleanupJob.status = "Everything's already tidy 🎉"
                            CleanupJob.running = false; return@launch
                        }
                        val names = todo.map { it.nameWithoutExtension }
                        Ai.analyzeTitles(ctx, names) { d, t -> CleanupJob.status = "Analyzing $d / $t…" }
                            .fold(
                                onSuccess = { m ->
                                    val out = todo.mapNotNull { f ->
                                        val info = m[f.nameWithoutExtension] ?: return@mapNotNull null
                                        val suggested = listOfNotNull(info.artist, info.cleanTitle)
                                            .joinToString(" — ").ifBlank { info.cleanTitle }.trim()
                                        // Only suggest a real change.
                                        if (suggested.isBlank() || suggested == f.nameWithoutExtension)
                                            null
                                        else CleanupSuggestion(f.absolutePath, f.nameWithoutExtension,
                                            suggested, info.category)
                                    }
                                    CleanupJob.results.clear(); CleanupJob.results.addAll(out)
                                    CleanupJob.status = if (out.isEmpty()) "Nothing needs renaming 🎉"
                                    else "${out.size} file(s) could be tidied."
                                    CleanupJob.running = false
                                },
                                onFailure = {
                                    CleanupJob.status = "Failed: ${it.message}"
                                    CleanupJob.running = false
                                }
                            )
                    }
                },
                enabled = !CleanupJob.running && files.isNotEmpty(),
                modifier = Modifier.fillMaxWidth(), shape = MaterialTheme.shapes.large
            ) {
                if (CleanupJob.running) {
                    CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary)
                    Spacer(Modifier.width(8.dp))
                }
                Text(if (CleanupJob.running) "Analyzing…" else "Analyze titles (AI)")
            }

            if (CleanupJob.status.isNotBlank())
                Text(CleanupJob.status, style = MaterialTheme.typography.bodyMedium)

            val pending = CleanupJob.results.filter { !it.done }
            if (pending.isNotEmpty()) {
                // --- Bulk action bar -------------------------------------------- #
                val selectedCount = pending.count { it.selected }
                Row(verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = {
                            CleanupJob.running = true
                            Jobs.launch("Rename files") {
                                CleanupJob.results.filter { !it.done }.forEach { applyOne(it) }
                                CleanupJob.running = false
                                CleanupJob.status = "Renamed everything. Library updated."
                                onChanged()
                            }
                        },
                        enabled = !CleanupJob.running, modifier = Modifier.weight(1f),
                        shape = MaterialTheme.shapes.large
                    ) { Text("Rename all (${pending.size})") }
                    OutlinedButton(
                        onClick = {
                            CleanupJob.running = true
                            Jobs.launch("Rename selected") {
                                CleanupJob.results.filter { !it.done && it.selected }.forEach { applyOne(it) }
                                CleanupJob.running = false
                                CleanupJob.status = "Renamed your picks. Library updated."
                                onChanged()
                            }
                        },
                        enabled = !CleanupJob.running && selectedCount > 0,
                        modifier = Modifier.weight(1f), shape = MaterialTheme.shapes.large
                    ) { Text("Selected ($selectedCount)") }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val allSel = pending.all { it.selected }
                    TextButton(onClick = { pending.forEach { it.selected = !allSel } }) {
                        Text(if (allSel) "Unselect all" else "Select all")
                    }
                }

                // --- Per-file suggestions --------------------------------------- #
                CleanupJob.results.forEach { s ->
                    if (s.done) return@forEach
                    HorizontalDivider()
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = s.selected, onCheckedChange = { s.selected = it })
                        Column(Modifier.weight(1f)) {
                            Text("From: ${s.from}", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text("→ ${s.suggested}", style = MaterialTheme.typography.bodyMedium)
                            Text(s.category, style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary)
                        }
                        TextButton(onClick = {
                            applyOne(s); onChanged()
                        }) { Text("Rename") }
                        TextButton(onClick = {
                            CleanState.mark(File(s.path)); s.done = true
                        }) { Text("Skip") }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AssistantScreen(ui: AssistantUi, scope: CoroutineScope, onOpen: (String) -> Unit) {
    val ctx = LocalContext.current
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    fun persist() = scope.launch(Dispatchers.IO) { ChatStore.save(ui.sessions.toList(), ui.currentId) }

    LaunchedEffect(Unit) {
        if (!ui.loaded) {
            val (list, cur) = withContext(Dispatchers.IO) { ChatStore.load() }
            if (ui.sessions.isEmpty()) { ui.sessions.addAll(list); ui.currentId = cur }
            ui.loaded = true
        }
        ui.ensureChat()
    }

    val session = ui.current

    ModalNavigationDrawer(
        drawerState = drawerState,
        gesturesEnabled = false,
        drawerContent = {
            ModalDrawerSheet {
                Column(Modifier.fillMaxSize().padding(12.dp)) {
                    Text("Your chats", style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(12.dp))
                    Button(
                        onClick = { ui.newChat(); persist(); scope.launch { drawerState.close() } },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Icon(Icons.Filled.Add, contentDescription = null)
                        Spacer(Modifier.width(8.dp)); Text("New chat")
                    }
                    Spacer(Modifier.height(8.dp))
                    LazyColumn(Modifier.weight(1f)) {
                        items(ui.sessions, key = { it.id }) { s ->
                            NavigationDrawerItem(
                                selected = s.id == ui.currentId,
                                label = { Text(s.title.ifBlank { "New chat" }, maxLines = 1) },
                                badge = {
                                    IconButton(onClick = { ui.delete(s.id); persist() }) {
                                        Icon(Icons.Filled.Delete, contentDescription = "Delete chat")
                                    }
                                },
                                onClick = {
                                    ui.currentId = s.id; persist()
                                    scope.launch { drawerState.close() }
                                },
                                modifier = Modifier.padding(horizontal = 8.dp)
                            )
                        }
                    }
                    if (ui.sessions.size > 1) {
                        HorizontalDivider()
                        TextButton(onClick = { ui.deleteAll(); persist() }) {
                            Text("Delete all chats")
                        }
                    }
                }
            }
        }
    ) {
        Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { scope.launch { drawerState.open() } }) {
                    Icon(Icons.Filled.Menu, contentDescription = "Chats")
                }
                Text(session?.title?.ifBlank { "New chat" } ?: "New chat",
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1, modifier = Modifier.weight(1f))
                IconButton(onClick = { ui.newChat(); persist() }) {
                    Icon(Icons.Filled.Add, contentDescription = "New chat")
                }
            }

            val msgs = session?.messages
            val listState = rememberLazyListState()
            LaunchedEffect(msgs?.size) {
                if (!msgs.isNullOrEmpty()) listState.animateScrollToItem(msgs.size - 1)
            }

            if (msgs.isNullOrEmpty()) {
                Column(
                    Modifier.weight(1f).fillMaxWidth(),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text("Ask me to grab something", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(6.dp))
                    Text("e.g. \"download lo-fi beats as mp3\", \"get this video in 720p\". " +
                        "Tap ☰ to keep separate chats (one per artist).",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(msgs) { m -> ChatBubble(m, onOpen) }
                }
            }

            if (ui.busy) {
                Row(
                    Modifier.padding(vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                    Text("Thinking…", style = MaterialTheme.typography.bodySmall)
                }
            }

            Row(
                Modifier.fillMaxWidth().padding(top = 4.dp),
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(
                    value = ui.input, onValueChange = { ui.input = it },
                    placeholder = { Text("Ask the assistant…") },
                    modifier = Modifier.weight(1f), maxLines = 4
                )
                FilledIconButton(
                    onClick = { assistantSend(ctx, scope, ui) { persist() } },
                    enabled = !ui.busy && ui.input.isNotBlank(),
                    modifier = Modifier.size(56.dp)
                ) { Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send") }
            }
        }
    }
}

@Composable
private fun ChatBubble(m: ChatMsg, onOpen: (String) -> Unit) {
    // A finished download whose file still exists → a tappable "play it" card.
    val playable = m.filePath?.takeIf { File(it).exists() }
    val bg = when {
        m.fromUser -> MaterialTheme.colorScheme.primaryContainer
        playable != null -> MaterialTheme.colorScheme.tertiaryContainer
        else -> MaterialTheme.colorScheme.surfaceVariant
    }
    val fg = when {
        m.fromUser -> MaterialTheme.colorScheme.onPrimaryContainer
        playable != null -> MaterialTheme.colorScheme.onTertiaryContainer
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    Column(
        Modifier.fillMaxWidth(),
        horizontalAlignment = if (m.fromUser) Alignment.End else Alignment.Start
    ) {
        Surface(
            color = bg, shape = MaterialTheme.shapes.large,
            modifier = if (playable != null) Modifier.clickable { onOpen(playable) } else Modifier
        ) {
            Row(
                Modifier.widthIn(max = 300.dp).padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(m.text, color = fg, style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.weight(1f, fill = false))
                if (playable != null) {
                    Icon(Icons.Filled.PlayCircle, contentDescription = "Play in Library",
                        tint = fg, modifier = Modifier.size(28.dp))
                }
            }
        }
    }
}

private fun assistantSend(ctx: Context, scope: CoroutineScope, ui: AssistantUi, persist: () -> Unit) {
    val text = ui.input.trim()
    if (text.isBlank() || ui.busy) return
    val session = ui.current ?: return
    session.messages.add(ChatMsg(true, text))
    if (session.title.isBlank() || session.title == "New chat") session.title = text.take(40)
    ui.input = ""
    ui.busy = true
    persist()
    scope.launch {
        if (!Ai.isConfigured(ctx)) {
            session.messages.add(ChatMsg(false,
                "I need an AI key first — go to Download → \"AI assistant settings\" and paste your NVIDIA key."))
        } else {
            Ai.agentPlan(ctx, text).fold(
                onSuccess = { plan -> runPlan(ctx, session, text, plan) },
                onFailure = { session.messages.add(ChatMsg(false, "Sorry — ${it.message}")) }
            )
        }
        ui.busy = false
        persist()
    }
}

private suspend fun runPlan(
    ctx: Context, session: ChatSession, instruction: String, plan: Ai.AgentPlan,
) {
    if (plan.action == "help") {
        session.messages.add(ChatMsg(false, plan.answer ?: "How can I help with your downloads?"))
        return
    }
    if (!Storage.hasAccess(ctx)) {
        session.messages.add(ChatMsg(false,
            "I need storage access first — open the Download tab and tap \"Grant storage access\"."))
        return
    }
    // Always act on THIS message: use a link the user actually pasted; otherwise
    // search the user's own words. Never reuse a model-recalled/hallucinated URL.
    val pastedUrl = Regex("""https?://\S+""").find(instruction)?.value
    val searchText = plan.query?.takeIf { it.isNotBlank() }
        ?: instruction.replace(
            Regex("(?i)\\b(please|download|get me|get|grab|play|find|the|a|an|song|track|video|by|for me)\\b"),
            " ").replace(Regex("\\s+"), " ").trim()
    val target = pastedUrl ?: if (searchText.isNotBlank()) "ytsearch1:$searchText" else null
    if (target == null) {
        session.messages.add(ChatMsg(false,
            plan.answer ?: "I couldn't tell what to download — give me a link or a song/video name."))
        return
    }
    val audio = !plan.fmt.equals("mp4", ignoreCase = true)
    val quality = when {
        plan.quality.contains("720") -> "720p"
        plan.quality.contains("480") -> "480p"
        else -> "Best"
    }
    val label = pastedUrl ?: searchText
    session.messages.add(ChatMsg(false,
        "On it — downloading \"$label\" as ${if (audio) "MP3" else "MP4"}…"))
    Downloader.download(ctx, target, audio, quality) { _, _ -> }.fold(
        onSuccess = { out ->
            out.file?.let { f ->
                History.add(HistoryEntry(f.nameWithoutExtension, target, audio,
                    f.absolutePath, f.length(), System.currentTimeMillis()))
            }
            session.messages.add(ChatMsg(false,
                "✅ Done — ${out.file?.nameWithoutExtension ?: "saved"}\n▶ Tap to play it in your Library",
                filePath = out.file?.absolutePath))
        },
        onFailure = { session.messages.add(ChatMsg(false, "❌ Couldn't download it: ${it.message}")) }
    )
}

private fun fmtDur(s: Int): String {
    if (s <= 0) return ""
    val h = s / 3600; val m = (s % 3600) / 60; val sec = s % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, sec) else "%d:%02d".format(m, sec)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChannelBulkScreen(ui: ChannelUi, bulk: BulkUi) {
    Column(Modifier.fillMaxSize()) {
        Spacer(Modifier.height(8.dp))
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
            SegmentedButton(selected = ui.mode == 0, onClick = { ui.mode = 0 },
                shape = SegmentedButtonDefaults.itemShape(0, 2)) { Text("📺 Channel / Profile") }
            SegmentedButton(selected = ui.mode == 1, onClick = { ui.mode = 1 },
                shape = SegmentedButtonDefaults.itemShape(1, 2)) { Text("📚 Bulk") }
        }
        if (ui.mode == 0) ChannelBody(ui) else BulkBody(bulk)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ChannelBody(ui: ChannelUi) {
    val ctx = LocalContext.current
    var hasStorage by remember { mutableStateOf(Storage.hasAccess(ctx)) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { hasStorage = Storage.hasAccess(ctx) }

    val perPage = 20
    val filtered = ui.entries.filter {
        (ui.query.isBlank() || it.title.contains(ui.query, true)) &&
            (ui.categoryFilter == "All" || ChannelTriage.categories[it.title] == ui.categoryFilter)
    }
    val pages = if (filtered.isEmpty()) 1 else (filtered.size + perPage - 1) / perPage
    val pageClamped = ui.page.coerceIn(0, pages - 1)
    val pageItems = filtered.drop(pageClamped * perPage).take(perPage)

    fun enqueueAll(list: List<Downloader.Entry>) {
        list.forEach { Downloads.enqueue(ctx, it.url, ui.audio, ui.quality, it.title) }
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(ui.url, { ui.url = it },
            label = { Text("Channel / playlist / profile URL") }, singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
        Spacer(Modifier.height(8.dp))
        BrandButton(
            onClick = {
                ui.scanning = true; ui.status = "Scanning…"; ui.entries.clear()
                ui.selected.clear(); ui.page = 0; ui.categoryFilter = "All"; ChannelTriage.reset()
                // App-scope scan: keeps reading the channel even if you switch tabs.
                Jobs.launch("Scan channel") {
                    Downloader.scanEntries(ctx, ui.url.trim()).fold(
                        onSuccess = {
                            ui.entries.clear(); ui.entries.addAll(it)
                            ui.status = "Found ${it.size} item(s)."
                        },
                        onFailure = { ui.status = "Scan failed: ${it.message}" })
                    ui.scanning = false
                }
            },
            enabled = ui.url.isNotBlank() && !ui.scanning, modifier = Modifier.fillMaxWidth()
        ) {
            Icon(Icons.Filled.Subscriptions, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text(if (ui.scanning) "Scanning…" else "Scan channel / playlist")
        }

        if (ui.scanning) { Spacer(Modifier.height(8.dp)); LinearProgressIndicator(Modifier.fillMaxWidth()) }
        if (ui.status.isNotBlank()) { Spacer(Modifier.height(6.dp)); Text(ui.status, style = MaterialTheme.typography.bodySmall) }
        if (!hasStorage && ui.entries.isNotEmpty()) {
            Text("Grant storage access on the Download tab first.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }

        if (ui.entries.isEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text("Paste a channel, playlist or profile link and Scan. You'll get the full " +
                "list — search, sort by type with AI (Music / Live / Interview / …), select " +
                "items, choose MP3/MP4, and download. It all keeps running while you browse " +
                "other tabs.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            Spacer(Modifier.height(8.dp))
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                SegmentedButton(selected = ui.audio, onClick = { ui.audio = true },
                    shape = SegmentedButtonDefaults.itemShape(0, 2)) { Text("🎵 MP3") }
                SegmentedButton(selected = !ui.audio, onClick = { ui.audio = false },
                    shape = SegmentedButtonDefaults.itemShape(1, 2)) { Text("🎬 MP4") }
            }
            if (!ui.audio) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("Best", "720p", "480p").forEach {
                        FilterChip(selected = ui.quality == it, onClick = { ui.quality = it }, label = { Text(it) })
                    }
                }
            }

            // --- AI category sort (desktop "AI Triage" parity) ------------------ #
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = {
                        if (!Ai.isConfigured(ctx)) {
                            ChannelTriage.status = "Set an AI key first (menu → AI assistant settings)."
                        } else {
                            ChannelTriage.running = true; ChannelTriage.status = "Sorting by type…"
                            Jobs.launch("Sort channel") {
                                val titles = ui.entries.map { it.title }
                                Ai.analyzeTitles(ctx, titles) { d, t -> ChannelTriage.status = "Sorting $d / $t…" }
                                    .fold(
                                        onSuccess = { m ->
                                            ui.entries.forEach { e ->
                                                m[e.title]?.let { ChannelTriage.categories[e.title] = it.category }
                                            }
                                            ChannelTriage.status = "Sorted — tap a category below."
                                        },
                                        onFailure = { ChannelTriage.status = "Sort failed: ${it.message}" }
                                    )
                                ChannelTriage.running = false
                            }
                        }
                    },
                    enabled = !ChannelTriage.running
                ) {
                    Icon(Icons.Filled.AutoAwesome, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(if (ChannelTriage.running) "Sorting…" else "AI sort by type")
                }
                if (ChannelTriage.status.isNotBlank())
                    Text(ChannelTriage.status, style = MaterialTheme.typography.bodySmall,
                        maxLines = 2, modifier = Modifier.weight(1f))
            }
            if (ChannelTriage.categories.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                val counts = ChannelTriage.categories.values.groupingBy { it }.eachCount()
                val cats = listOf("All") + counts.keys.sortedByDescending { counts[it] }
                Row(Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    cats.forEach { c ->
                        FilterChip(selected = ui.categoryFilter == c,
                            onClick = { ui.categoryFilter = c; ui.page = 0 },
                            label = { Text(if (c == "All") "All (${ui.entries.size})" else "$c (${counts[c]})") })
                    }
                }
            }

            Spacer(Modifier.height(8.dp))
            OutlinedTextField(ui.query, { ui.query = it; ui.page = 0 },
                label = { Text("Search items") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Spacer(Modifier.height(8.dp))

            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = {
                    val pageUrls = pageItems.map { it.url }
                    if (pageUrls.all { it in ui.selected }) ui.selected.removeAll(pageUrls.toSet())
                    else pageUrls.forEach { if (it !in ui.selected) ui.selected.add(it) }
                }) { Text("Select page") }
                Text("${ui.selected.size} selected", style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(enabled = hasStorage && ui.selected.isNotEmpty(),
                    onClick = {
                        enqueueAll(ui.entries.filter { it.url in ui.selected })
                        ui.status = "Queued ${ui.selected.size}."
                    },
                    modifier = Modifier.weight(1f), shape = MaterialTheme.shapes.large) {
                    Text("Download selected (${ui.selected.size})")
                }
                OutlinedButton(enabled = hasStorage && filtered.isNotEmpty(),
                    onClick = { enqueueAll(filtered); ui.status = "Queued ${filtered.size}." },
                    modifier = Modifier.weight(1f), shape = MaterialTheme.shapes.large) {
                    Text("All (${filtered.size})")
                }
            }
            Spacer(Modifier.height(8.dp))

            LazyColumn(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(pageItems, key = { it.url }) { e ->
                    val sel = e.url in ui.selected
                    ElevatedCard(Modifier.fillMaxWidth().clickable {
                        if (sel) ui.selected.remove(e.url) else ui.selected.add(e.url)
                    }) {
                        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = sel, onCheckedChange = {
                                if (sel) ui.selected.remove(e.url) else ui.selected.add(e.url)
                            })
                            if (e.thumb.isNotBlank()) {
                                AsyncImage(model = e.thumb, contentDescription = null,
                                    modifier = Modifier.size(width = 64.dp, height = 40.dp)
                                        .clip(MaterialTheme.shapes.small))
                                Spacer(Modifier.width(8.dp))
                            }
                            Column(Modifier.weight(1f)) {
                                Text(e.title, style = MaterialTheme.typography.bodyMedium, maxLines = 2)
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    if (e.durationSec > 0) Text(fmtDur(e.durationSec),
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    ChannelTriage.categories[e.title]?.let {
                                        Text(it, style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.primary)
                                    }
                                }
                            }
                            IconButton(enabled = hasStorage, onClick = {
                                Downloads.enqueue(ctx, e.url, ui.audio, ui.quality, e.title)
                                ui.status = "Queued \"${e.title}\"."
                            }) { Icon(Icons.Filled.Download, contentDescription = "Download this") }
                        }
                    }
                }
            }

            if (pages > 1) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton(enabled = pageClamped > 0, onClick = { ui.page = pageClamped - 1 }) { Text("‹ Prev") }
                    Text("Page ${pageClamped + 1} / $pages", textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                    OutlinedButton(enabled = pageClamped < pages - 1, onClick = { ui.page = pageClamped + 1 }) { Text("Next ›") }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BulkBody(ui: BulkUi) {
    val ctx = LocalContext.current
    var hasStorage by remember { mutableStateOf(Storage.hasAccess(ctx)) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { hasStorage = Storage.hasAccess(ctx) }

    fun parse(s: String) = s.split("\n").map { it.trim() }.filter { it.isNotBlank() }
    val vCount = parse(ui.videoLinks).size
    val aCount = parse(ui.audioLinks).size
    val total = vCount + aCount

    Column(
        Modifier.fillMaxSize().padding(16.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Paste links — one per line — into the format you want, then Download all. " +
            "Everything queues into Downloads and keeps running while you use the app.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)

        Text("🎬 Video → MP4", style = MaterialTheme.typography.titleSmall)
        OutlinedTextField(ui.videoLinks, { ui.videoLinks = it },
            placeholder = { Text("https://…\nhttps://…") },
            modifier = Modifier.fillMaxWidth().height(150.dp),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("Best", "720p", "480p").forEach {
                FilterChip(selected = ui.quality == it, onClick = { ui.quality = it }, label = { Text(it) })
            }
        }

        Text("🎵 Audio → MP3", style = MaterialTheme.typography.titleSmall)
        OutlinedTextField(ui.audioLinks, { ui.audioLinks = it },
            placeholder = { Text("https://…\nhttps://…") },
            modifier = Modifier.fillMaxWidth().height(150.dp),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))

        BrandButton(
            onClick = {
                parse(ui.videoLinks).forEach { Downloads.enqueue(ctx, it, false, ui.quality, it) }
                parse(ui.audioLinks).forEach { Downloads.enqueue(ctx, it, true, "Best", it) }
                ui.status = "Queued $total item(s) — they're downloading in the background " +
                    "(see Downloads on the Download tab)."
                ui.videoLinks = ""; ui.audioLinks = ""
            },
            enabled = hasStorage && total > 0, modifier = Modifier.fillMaxWidth()
        ) {
            Icon(Icons.Filled.Download, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Download all ($total)")
        }

        if (!hasStorage) Text("Grant storage access on the Download tab first.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        if (ui.status.isNotBlank()) Text(ui.status, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
fun AiJobsBar(onTap: () -> Unit) {
    val active = Jobs.activeCount
    if (active == 0) return
    val cur = Jobs.items.firstOrNull { it.status == JobStatus.RUNNING }
    Surface(
        color = MaterialTheme.colorScheme.tertiaryContainer,
        modifier = Modifier.fillMaxWidth().clickable { onTap() }
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            CircularProgressIndicator(Modifier.size(14.dp), strokeWidth = 2.dp,
                color = MaterialTheme.colorScheme.onTertiaryContainer)
            Text("🤖 ${cur?.label ?: "AI working"}…  ${cur?.detail.orEmpty()}".trim(),
                color = MaterialTheme.colorScheme.onTertiaryContainer,
                style = MaterialTheme.typography.bodySmall, maxLines = 1,
                modifier = Modifier.weight(1f))
            if (active > 1) Text("$active",
                color = MaterialTheme.colorScheme.onTertiaryContainer,
                style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
fun DownloadsBar(onTap: () -> Unit) {
    val active = Downloads.activeCount
    if (active == 0) return
    val cur = Downloads.tasks.firstOrNull { it.status == "running" }
    Surface(
        color = MaterialTheme.colorScheme.secondaryContainer,
        modifier = Modifier.fillMaxWidth().clickable { onTap() }
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Icon(Icons.Filled.Download, contentDescription = null, modifier = Modifier.size(16.dp))
            Text("$active downloading…", style = MaterialTheme.typography.bodySmall,
                maxLines = 1, modifier = Modifier.weight(1f))
            cur?.let { Text("${(it.progress * 100).toInt()}%", style = MaterialTheme.typography.bodySmall) }
        }
    }
}

@Composable
fun DownloadsList(ctx: android.content.Context, scope: CoroutineScope, onNeedKey: () -> Unit) {
    if (Downloads.tasks.isEmpty()) return
    Spacer(Modifier.height(8.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("Downloads", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
        TextButton(onClick = { Downloads.clearFinished() }) { Text("Clear finished") }
    }
    Downloads.tasks.forEach { t ->
        key(t.id) {
            var explanation by remember { mutableStateOf<String?>(null) }
            var aiBusy by remember { mutableStateOf(false) }
            ElevatedCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    val icon = when (t.status) {
                        "done" -> "✅"; "failed" -> "❌"; "running" -> "⬇️"; else -> "⏳"
                    }
                    Text("$icon ${t.label}", style = MaterialTheme.typography.bodyMedium, maxLines = 2)
                    if (t.status == "running") {
                        LinearProgressIndicator(progress = { t.progress }, modifier = Modifier.fillMaxWidth())
                    }
                    if (t.detail.isNotBlank()) {
                        Text(t.detail, style = MaterialTheme.typography.bodySmall, maxLines = 2)
                    }
                    if (t.status == "failed") {
                        Button(
                            onClick = {
                                if (!Ai.isConfigured(ctx)) onNeedKey() else {
                                    aiBusy = true
                                    scope.launch {
                                        explanation = Ai.explainError(ctx, t.label, t.detail)
                                            .getOrElse { "Couldn't reach the AI: ${it.message}" }
                                        aiBusy = false
                                    }
                                }
                            },
                            enabled = !aiBusy
                        ) { Text(if (aiBusy) "Thinking…" else "💡 Explain & fix (AI)") }
                        explanation?.let { Text("🤖 $it", style = MaterialTheme.typography.bodyMedium) }
                    }
                }
            }
        }
    }
}

@Composable
fun DownloadFailedCard(
    ctx: android.content.Context,
    ui: DownloadUi,
    scope: CoroutineScope,
    onNeedKey: () -> Unit,
) {
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("❌ Download failed", style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.error)
            ui.failure?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            Button(
                onClick = {
                    if (!Ai.isConfigured(ctx)) {
                        onNeedKey()
                    } else {
                        ui.aiBusy = true; ui.aiExplanation = null
                        val err = ui.failure.orEmpty()
                        val title = ui.url.trim()
                        scope.launch {
                            val r = Ai.explainError(ctx, title, err)
                            ui.aiBusy = false
                            ui.aiExplanation = r.getOrElse { "Couldn't reach the AI: ${it.message}" }
                        }
                    }
                },
                enabled = !ui.aiBusy, modifier = Modifier.fillMaxWidth()
            ) { Text(if (ui.aiBusy) "Thinking…" else "💡 Explain & fix (AI)") }

            if (ui.aiBusy) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                    Text("Asking the assistant…", style = MaterialTheme.typography.bodySmall)
                }
            }
            ui.aiExplanation?.let {
                HorizontalDivider()
                Text("🤖 $it", style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Composable
fun AiKeyDialog(ctx: android.content.Context, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    var key by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val existing = remember { Ai.maskedKey(ctx) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("AI assistant") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Paste your NVIDIA API key (starts with nvapi-). It's stored " +
                    "encrypted on this device and only used to explain download " +
                    "errors — never your files. Get a free key at build.nvidia.com.",
                    style = MaterialTheme.typography.bodySmall)
                if (existing.isNotBlank()) {
                    Text("Current key: $existing", fontFamily = FontFamily.Monospace,
                        style = MaterialTheme.typography.bodySmall)
                }
                OutlinedTextField(
                    value = key, onValueChange = { key = it },
                    label = { Text("nvapi-…") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                msg?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = !busy && key.isNotBlank(),
                onClick = {
                    busy = true; msg = "Checking key…"
                    val k = key.trim()
                    scope.launch {
                        val r = Ai.validateKey(k)
                        busy = false
                        r.fold(
                            onSuccess = { Ai.saveKey(ctx, k); onDismiss() },
                            onFailure = { msg = it.message }
                        )
                    }
                }
            ) { Text("Save") }
        },
        dismissButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                if (existing.isNotBlank()) {
                    TextButton(onClick = { Ai.clearKey(ctx); onDismiss() }) { Text("Remove") }
                }
                TextButton(onClick = onDismiss) { Text("Close") }
            }
        }
    )
}

@Composable
fun AboutDialog(ctx: android.content.Context, lm: LicenseManager, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } },
        title = { Text("Universal Media Downloader") },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("Download, organize, play and manage media — powered by AI.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)

                AboutRow("Version", "v${BuildConfig.VERSION_NAME} (build ${BuildConfig.VERSION_CODE})")
                AboutRow("Developer", "George Muraguri Muthoni")
                AboutRow("Publisher", "BAZIQ HUE")
                AboutRow("License", lm.status())
                AboutRow("Package", ctx.packageName)

                HorizontalDivider()
                Text("What's new", style = MaterialTheme.typography.labelLarge)
                Text("• Channel / playlist / profile bulk download\n" +
                    "• Multi-chat AI assistant (saved chats)\n" +
                    "• AI: error helper, smart search, duplicate cleanup, title clean-up\n" +
                    "• Public-folder saves, history, selectable text",
                    style = MaterialTheme.typography.bodySmall)

                HorizontalDivider()
                Text("Support & links", style = MaterialTheme.typography.labelLarge)
                ContactLinks(ctx)
            }
        }
    )
}

@Composable
private fun AboutRow(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.primary)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

private val AUDIO_EXTS = setOf("mp3", "m4a", "aac", "opus", "ogg", "wav", "flac")
private fun isAudioFile(f: File) = f.extension.lowercase() in AUDIO_EXTS

/** Built-in player for both audio and video; queued with same-type siblings. */
private fun playInApp(ctx: android.content.Context, queue: List<File>, f: File) {
    val sameType = queue.filter { isAudioFile(it) == isAudioFile(f) }.ifEmpty { listOf(f) }
    Playback.play(sameType, sameType.indexOf(f).coerceAtLeast(0))
}

private fun fmtTime(ms: Long): String {
    if (ms <= 0) return "0:00"
    val s = ms / 1000
    return "%d:%02d".format(s / 60, s % 60)
}

@Composable
fun MiniPlayer(onExpand: () -> Unit) {
    if (!Playback.hasItem) return
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        tonalElevation = 3.dp,
        modifier = Modifier.fillMaxWidth().clickable { onExpand() }
    ) {
        Row(
            Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            val path = Playback.currentPath
            if (path.isNotBlank()) MediaArtwork(File(path), size = 40.dp, corner = 9.dp)
            else Icon(Icons.Filled.MusicNote, contentDescription = null)
            Spacer(Modifier.width(10.dp))
            Text(Playback.title.ifBlank { "Now playing" },
                style = MaterialTheme.typography.bodyMedium, maxLines = 1,
                modifier = Modifier.weight(1f))
            IconButton(onClick = { Playback.playPause() }) {
                Icon(if (Playback.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    contentDescription = "Play/Pause")
            }
            IconButton(onClick = { Playback.next() }) {
                Icon(Icons.Filled.SkipNext, contentDescription = "Next")
            }
            IconButton(onClick = { Playback.stop() }) {
                Icon(Icons.Filled.Close, contentDescription = "Close player")
            }
        }
    }
}

@Composable
fun PlayerScreen(onClose: () -> Unit) {
    Dialog(onDismissRequest = onClose,
        properties = DialogProperties(usePlatformDefaultWidth = false)) {
        var pos by remember { mutableStateOf(0L) }
        var sleepMenu by remember { mutableStateOf(false) }
        LaunchedEffect(Playback.isPlaying, Playback.title) {
            while (true) { pos = Playback.position(); delay(500) }
        }
        val dur = Playback.duration()
        Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            Column(
                Modifier.fillMaxSize().background(BrandWash).padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onClose) {
                        Icon(Icons.Filled.KeyboardArrowDown, contentDescription = "Minimize")
                    }
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = { Playback.stop(); onClose() }) {
                        Icon(Icons.Filled.Close, contentDescription = null)
                        Spacer(Modifier.width(4.dp)); Text("Stop")
                    }
                }
                Spacer(Modifier.weight(1f))
                val path = Playback.currentPath
                if (path.isNotBlank()) MediaArtwork(File(path), size = 260.dp, corner = 24.dp)
                else Icon(Icons.Filled.MusicNote, contentDescription = null,
                    modifier = Modifier.size(96.dp), tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.height(28.dp))
                Text(Playback.title.ifBlank { "Now playing" },
                    style = MaterialTheme.typography.titleLarge,
                    textAlign = TextAlign.Center, maxLines = 3)
                Spacer(Modifier.height(28.dp))
                Slider(
                    value = if (dur > 0) (pos.toFloat() / dur).coerceIn(0f, 1f) else 0f,
                    onValueChange = { if (dur > 0) Playback.seekTo((it * dur).toLong()) },
                    modifier = Modifier.fillMaxWidth()
                )
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(fmtTime(pos), style = MaterialTheme.typography.bodySmall)
                    Text(fmtTime(dur), style = MaterialTheme.typography.bodySmall)
                }
                Spacer(Modifier.height(10.dp))
                // Extras: favorite · speed · sleep timer
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceEvenly,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    val fav = Favorites.isFavorite(Playback.currentPath)
                    IconButton(onClick = { Favorites.toggle(Playback.currentPath) }) {
                        Icon(if (fav) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                            contentDescription = "Favorite",
                            tint = if (fav) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    TextButton(onClick = { Playback.cycleSpeed() }) { Text("${Playback.speed}x") }
                    Box {
                        TextButton(onClick = { sleepMenu = true }) {
                            Icon(Icons.Filled.Bedtime, contentDescription = "Sleep timer")
                            Spacer(Modifier.width(4.dp))
                            Text(if (Playback.sleepMinutes > 0) "${Playback.sleepMinutes}m" else "Off")
                        }
                        DropdownMenu(expanded = sleepMenu, onDismissRequest = { sleepMenu = false }) {
                            listOf(0, 15, 30, 60).forEach { m ->
                                DropdownMenuItem(
                                    text = { Text(if (m == 0) "Sleep off" else "$m minutes") },
                                    onClick = { Playback.scheduleSleep(m); sleepMenu = false })
                            }
                        }
                    }
                }
                Spacer(Modifier.height(14.dp))
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    IconButton(onClick = { Playback.toggleShuffle() }) {
                        Icon(Icons.Filled.Shuffle, contentDescription = "Shuffle",
                            tint = if (Playback.shuffle) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    IconButton(onClick = { Playback.prev() }, modifier = Modifier.size(48.dp)) {
                        Icon(Icons.Filled.SkipPrevious, contentDescription = "Previous",
                            modifier = Modifier.size(36.dp))
                    }
                    FilledIconButton(onClick = { Playback.playPause() },
                        modifier = Modifier.size(72.dp)) {
                        Icon(if (Playback.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                            contentDescription = "Play/Pause", modifier = Modifier.size(40.dp))
                    }
                    IconButton(onClick = { Playback.next() }, modifier = Modifier.size(48.dp)) {
                        Icon(Icons.Filled.SkipNext, contentDescription = "Next",
                            modifier = Modifier.size(36.dp))
                    }
                    IconButton(onClick = { Playback.cycleRepeat() }) {
                        Icon(
                            if (Playback.repeatMode == Player.REPEAT_MODE_ONE) Icons.Filled.RepeatOne
                            else Icons.Filled.Repeat,
                            contentDescription = "Repeat",
                            tint = if (Playback.repeatMode != Player.REPEAT_MODE_OFF)
                                MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                Spacer(Modifier.weight(1f))
            }
        }
    }
}

@OptIn(UnstableApi::class)
@Composable
fun VideoPlayerScreen(onClose: () -> Unit) {
    // Default Fit preserves the source aspect ratio (fixes stretching); the user
    // can switch like VLC. Stretch = fill, Crop = zoom-to-fill.
    val modes = remember {
        listOf(
            "Fit" to AspectRatioFrameLayout.RESIZE_MODE_FIT,
            "Stretch" to AspectRatioFrameLayout.RESIZE_MODE_FILL,
            "Crop" to AspectRatioFrameLayout.RESIZE_MODE_ZOOM,
        )
    }
    var mode by remember { mutableStateOf(0) }

    Dialog(onDismissRequest = onClose,
        properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize(), color = Color.Black) {
            Box(Modifier.fillMaxSize()) {
                AndroidView(
                    factory = { c ->
                        PlayerView(c).apply {
                            player = Playback.player()
                            resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                            setShowSubtitleButton(true)
                            setShowNextButton(true)
                            setShowPreviousButton(true)
                        }
                    },
                    update = {
                        it.player = Playback.player()
                        it.resizeMode = modes[mode].second
                    },
                    modifier = Modifier.fillMaxSize()
                )
                Row(
                    Modifier.fillMaxWidth().padding(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    IconButton(onClick = onClose) {
                        Icon(Icons.Filled.KeyboardArrowDown, contentDescription = "Close",
                            tint = Color.White)
                    }
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = { mode = (mode + 1) % modes.size }) {
                        Text(modes[mode].first, color = Color.White)
                    }
                    TextButton(onClick = { Playback.cycleSpeed() }) {
                        Text("${Playback.speed}x", color = Color.White)
                    }
                }
            }
        }
    }
}

@Composable
fun DownloadDoneCard(ctx: android.content.Context, out: Downloader.Outcome) {
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("✅ Download complete", style = MaterialTheme.typography.titleMedium)
            Text("Saved to", style = MaterialTheme.typography.labelMedium)
            Text(Storage.displayPath(out.dir), fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodySmall)
            out.file?.let {
                Text("📄 ${it.name}", style = MaterialTheme.typography.bodySmall)
            }
            Button(
                onClick = { Storage.openFolder(ctx, out.dir) },
                modifier = Modifier.fillMaxWidth()
            ) { Text("📂 Open folder") }
            out.file?.let { f ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { playInApp(ctx, listOf(f), f) },
                        modifier = Modifier.weight(1f)) { Text("▶ Play") }
                    OutlinedButton(onClick = { Storage.shareFile(ctx, f) },
                        modifier = Modifier.weight(1f)) { Text("↗ Share") }
                }
            }
        }
    }
}

@Composable
fun ContactLinks(ctx: android.content.Context, websiteOnly: Boolean = false) {
    fun open(uri: String) = ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(uri)))
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (!websiteOnly) {
            TextButton(onClick = { open("mailto:phantomtyper.review@gmail.com") }) {
                Text("📧 phantomtyper.review@gmail.com")
            }
            TextButton(onClick = { open("https://wa.me/254799553292") }) {
                Text("💬 WhatsApp +254 799 553292")
            }
            TextButton(onClick = { open("https://wa.me/12103296074") }) {
                Text("💬 WhatsApp +1 210 329 6074")
            }
        }
        TextButton(onClick = { open("https://baziqhue.co.ke/") }) {
            Text("🌐 baziqhue.co.ke")
        }
    }
}
