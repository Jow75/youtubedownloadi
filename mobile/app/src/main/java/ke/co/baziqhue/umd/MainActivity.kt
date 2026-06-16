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
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.Subscriptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
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

/** One line in the assistant chat. */
data class ChatMsg(val fromUser: Boolean, val text: String)

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
    val assistant = remember { AssistantUi() }
    var tab by remember { mutableStateOf(0) }
    var showAbout by remember { mutableStateOf(false) }
    val sections = listOf("Download", "Channel", "History", "Library", "Assistant")

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
                actions = {
                    IconButton(onClick = { showAbout = true }) {
                        Icon(Icons.Filled.Info, contentDescription = "About")
                    }
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        },
        bottomBar = {
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
    ) { pad ->
        Box(Modifier.fillMaxSize().padding(pad)) {
            when (tab) {
                0 -> DownloadScreen(lm, ui, scope) { licensed = false }
                1 -> ChannelScreen()
                2 -> HistoryScreen { url, audio ->
                    ui.url = url; ui.audio = audio; ui.done = null; tab = 0
                }
                3 -> LibraryScreen()
                else -> AssistantScreen(assistant, scope)
            }
        }
    }

    if (showAbout) AboutDialog(ctx, lm) { showAbout = false }
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

        Button(
            onClick = {
                ui.busy = true; ui.progress = 0f; ui.log = "Starting…"; ui.done = null
                ui.failure = null; ui.aiExplanation = null
                val reqUrl = ui.url.trim(); val reqAudio = ui.audio; val reqQ = ui.quality
                scope.launch {
                    val res = Downloader.download(ctx, reqUrl, reqAudio, reqQ) { p, line ->
                        ui.progress = p / 100f
                        if (line.isNotBlank()) ui.log = line
                    }
                    ui.busy = false
                    res.fold(
                        onSuccess = { out ->
                            ui.done = out; ui.log = out.message; ui.failure = null
                            out.file?.let { f ->
                                History.add(HistoryEntry(
                                    title = f.nameWithoutExtension, url = reqUrl, audio = reqAudio,
                                    path = f.absolutePath, sizeBytes = f.length(),
                                    timestamp = System.currentTimeMillis()
                                ))
                            }
                        },
                        onFailure = {
                            ui.done = null
                            ui.failure = it.message ?: "Download failed."
                            ui.log = "Failed: ${it.message}"
                        }
                    )
                }
            },
            enabled = ui.url.isNotBlank() && !ui.busy && hasStorage,
            modifier = Modifier.fillMaxWidth()
        ) { Text(if (ui.busy) "Downloading…" else "⬇️ Download") }

        if (ui.busy) LinearProgressIndicator(progress = { ui.progress }, modifier = Modifier.fillMaxWidth())
        if (ui.log.isNotBlank() && ui.done == null && ui.failure == null)
            Text(ui.log, style = MaterialTheme.typography.bodySmall)

        ui.done?.let { DownloadDoneCard(ctx, it) }

        if (ui.failure != null && !ui.busy) {
            DownloadFailedCard(ctx, ui, scope) { showAiKey = true }
        }

        Spacer(Modifier.height(8.dp))
        Text("Saves to: ${Storage.displayPath(Downloader.targetDir(ui.audio))}",
            style = MaterialTheme.typography.bodySmall)
        OutlinedButton(
            onClick = { Storage.openFolder(ctx, Downloader.targetDir(ui.audio)) },
            modifier = Modifier.fillMaxWidth()
        ) { Text("📂 Open downloads folder") }

        OutlinedButton(
            onClick = { scope.launch { ui.log = Downloader.updateEngine(ctx); ui.done = null } },
            enabled = !ui.busy, modifier = Modifier.fillMaxWidth()
        ) { Text("Update download engine (yt-dlp)") }

        TextButton(onClick = { showAiKey = true }) { Text("🤖 AI assistant settings") }

        HorizontalDivider()
        ContactLinks(ctx)
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
            TextButton(onClick = { History.clear(); refresh() }) { Text("Clear all") }
        }

        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.weight(1f).fillMaxWidth()
        ) {
            items(filtered) { e ->
                HistoryRow(ctx, e, onRedownload) { History.remove(e); refresh() }
            }
        }
    }
}

@Composable
fun HistoryRow(
    ctx: android.content.Context,
    e: HistoryEntry,
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
                    OutlinedButton(onClick = { Storage.viewFile(ctx, f) },
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var entries by remember { mutableStateOf<List<HistoryEntry>>(emptyList()) }
    var aiOn by remember { mutableStateOf(false) }
    var showAiKey by remember { mutableStateOf(false) }
    fun reload() { entries = History.all(); aiOn = Ai.isConfigured(ctx) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { reload() }
    LaunchedEffect(Unit) { reload() }

    Column(
        Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
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

        SmartSearchSection(ctx, scope, entries, aiOn) { showAiKey = true }
        DuplicatesSection(ctx, scope)
        TitleCleanupSection(ctx, scope, entries, aiOn, { showAiKey = true }) { reload() }

        Spacer(Modifier.height(8.dp))
    }

    if (showAiKey) AiKeyDialog(ctx) { showAiKey = false }
}

@Composable
private fun SmartSearchSection(
    ctx: android.content.Context,
    scope: CoroutineScope,
    entries: List<HistoryEntry>,
    aiOn: Boolean,
    onNeedKey: () -> Unit,
) {
    var indexed by remember { mutableStateOf(0) }
    var status by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<Pair<HistoryEntry, Float>>>(emptyList()) }
    LaunchedEffect(entries.size) { indexed = SearchIndex.indexedCount() }

    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("🔎 Smart search", style = MaterialTheme.typography.titleMedium)
            Text("Find downloads by meaning, not exact words — e.g. \"that calm " +
                "piano study music\".", style = MaterialTheme.typography.bodySmall)
            Text("Indexed: $indexed / ${entries.size}", style = MaterialTheme.typography.bodySmall)

            OutlinedButton(
                onClick = {
                    if (!aiOn) onNeedKey() else {
                        busy = true; status = "Indexing…"
                        scope.launch {
                            val r = SearchIndex.build(ctx, entries.map { it.title }) { d, t ->
                                status = "Indexing $d / $t…"
                            }
                            indexed = SearchIndex.indexedCount()
                            busy = false
                            status = r.fold({ "Index ready ($indexed)." }, { "Failed: ${it.message}" })
                        }
                    }
                },
                enabled = !busy && entries.isNotEmpty(), modifier = Modifier.fillMaxWidth()
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
                            val r = SearchIndex.search(ctx, query.trim(), entries.map { it.title })
                            results = r.getOrDefault(emptyList()).mapNotNull { (title, score) ->
                                entries.firstOrNull { it.title == title }?.let { it to score }
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

            results.forEach { (e, score) ->
                val f = File(e.path)
                Column {
                    Text((if (e.audio) "🎵 " else "🎬 ") + e.title +
                        "  ·  ${(score * 100).toInt()}%",
                        style = MaterialTheme.typography.bodyMedium, maxLines = 2)
                    if (f.exists()) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            TextButton(onClick = { Storage.viewFile(ctx, f) }) { Text("▶ Play") }
                            TextButton(onClick = { Storage.shareFile(ctx, f) }) { Text("↗ Share") }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DuplicatesSection(ctx: android.content.Context, scope: CoroutineScope) {
    var busy by remember { mutableStateOf(false) }
    var scanned by remember { mutableStateOf(false) }
    var groups by remember { mutableStateOf<List<List<File>>>(emptyList()) }

    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("🧹 Duplicate cleanup", style = MaterialTheme.typography.titleMedium)
            Text("Finds byte-identical files in your Music/Video folders so you can " +
                "free up space.", style = MaterialTheme.typography.bodySmall)
            Button(
                onClick = {
                    busy = true
                    scope.launch {
                        groups = withContext(Dispatchers.IO) { Library.findDuplicates() }
                        scanned = true; busy = false
                    }
                },
                enabled = !busy, modifier = Modifier.fillMaxWidth()
            ) { Text(if (busy) "Scanning…" else "Scan for duplicates") }

            if (scanned && groups.isEmpty()) {
                Text("No duplicates found 🎉", style = MaterialTheme.typography.bodyMedium)
            }
            groups.forEachIndexed { gi, group ->
                HorizontalDivider()
                Text("Group ${gi + 1} — ${group.size} copies of \"${group.first().name}\"",
                    style = MaterialTheme.typography.bodySmall)
                group.forEachIndexed { i, f ->
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
    entries: List<HistoryEntry>,
    aiOn: Boolean,
    onNeedKey: () -> Unit,
    onChanged: () -> Unit,
) {
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    var cleaned by remember { mutableStateOf<List<Pair<HistoryEntry, Ai.TitleInfo>>>(emptyList()) }

    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("🏷️ Title clean-up", style = MaterialTheme.typography.titleMedium)
            Text("AI suggests a clean artist · title · category for your downloads. " +
                "Rename a file to tidy your library.", style = MaterialTheme.typography.bodySmall)
            Button(
                onClick = {
                    if (!aiOn) onNeedKey() else {
                        busy = true; status = "Analyzing titles…"
                        scope.launch {
                            val r = Ai.analyzeTitles(ctx, entries.map { it.title }) { done, total ->
                                status = "Analyzing $done / $total…"
                            }
                            busy = false
                            r.fold(
                                onSuccess = { m ->
                                    cleaned = entries.mapNotNull { e -> m[e.title]?.let { e to it } }
                                    status = if (cleaned.isEmpty()) "Nothing to clean." else ""
                                },
                                onFailure = { status = "Failed: ${it.message}" }
                            )
                        }
                    }
                },
                enabled = !busy && entries.isNotEmpty(), modifier = Modifier.fillMaxWidth()
            ) { Text(if (busy) "Analyzing…" else "Analyze titles (AI)") }

            if (status.isNotBlank()) Text(status, style = MaterialTheme.typography.bodySmall)

            cleaned.forEach { (e, info) ->
                HorizontalDivider()
                val suggested = listOfNotNull(info.artist, info.cleanTitle)
                    .joinToString(" — ").ifBlank { info.cleanTitle }
                Column {
                    Text("From: ${e.title}", style = MaterialTheme.typography.bodySmall)
                    Text("→ $suggested  ·  ${info.category}",
                        style = MaterialTheme.typography.bodyMedium)
                    val f = File(e.path)
                    if (f.exists()) {
                        TextButton(onClick = {
                            val nf = Library.rename(f, suggested)
                            if (nf != null) {
                                Storage.scan(ctx, f); Storage.scan(ctx, nf)
                                History.updatePath(e, nf.absolutePath, nf.nameWithoutExtension)
                                onChanged()
                            }
                        }) { Text("Rename file to this") }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AssistantScreen(ui: AssistantUi, scope: CoroutineScope) {
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
                    items(msgs) { m -> ChatBubble(m) }
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
private fun ChatBubble(m: ChatMsg) {
    val bg = if (m.fromUser) MaterialTheme.colorScheme.primaryContainer
    else MaterialTheme.colorScheme.surfaceVariant
    val fg = if (m.fromUser) MaterialTheme.colorScheme.onPrimaryContainer
    else MaterialTheme.colorScheme.onSurfaceVariant
    Column(
        Modifier.fillMaxWidth(),
        horizontalAlignment = if (m.fromUser) Alignment.End else Alignment.Start
    ) {
        Surface(color = bg, shape = MaterialTheme.shapes.large) {
            Text(m.text, color = fg,
                modifier = Modifier.widthIn(max = 300.dp)
                    .padding(horizontal = 14.dp, vertical = 10.dp),
                style = MaterialTheme.typography.bodyMedium)
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
                onSuccess = { plan -> runPlan(ctx, session, plan) },
                onFailure = { session.messages.add(ChatMsg(false, "Sorry — ${it.message}")) }
            )
        }
        ui.busy = false
        persist()
    }
}

private suspend fun runPlan(ctx: Context, session: ChatSession, plan: Ai.AgentPlan) {
    if (plan.action == "help") {
        session.messages.add(ChatMsg(false, plan.answer ?: "How can I help with your downloads?"))
        return
    }
    if (!Storage.hasAccess(ctx)) {
        session.messages.add(ChatMsg(false,
            "I need storage access first — open the Download tab and tap \"Grant storage access\"."))
        return
    }
    val url = when {
        !plan.url.isNullOrBlank() -> plan.url
        !plan.query.isNullOrBlank() -> "ytsearch1:${plan.query}"
        else -> null
    }
    if (url == null) {
        session.messages.add(ChatMsg(false,
            plan.answer ?: "I couldn't find anything to download — give me a link or a song/video name."))
        return
    }
    val audio = !plan.fmt.equals("mp4", ignoreCase = true)
    val quality = when {
        plan.quality.contains("720") -> "720p"
        plan.quality.contains("480") -> "480p"
        else -> "Best"
    }
    session.messages.add(ChatMsg(false,
        "On it — downloading ${if (audio) "audio (MP3)" else "video (MP4)"}…"))
    Downloader.download(ctx, url, audio, quality) { _, _ -> }.fold(
        onSuccess = { out ->
            out.file?.let { f ->
                History.add(HistoryEntry(f.nameWithoutExtension, url, audio,
                    f.absolutePath, f.length(), System.currentTimeMillis()))
            }
            session.messages.add(ChatMsg(false, "✅ Done — saved to ${Storage.displayPath(out.dir)}" +
                (out.file?.let { "\n${it.name}" } ?: "")))
        },
        onFailure = { session.messages.add(ChatMsg(false, "❌ Couldn't download it: ${it.message}")) }
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChannelScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf("") }
    var audio by remember { mutableStateOf(true) }
    var quality by remember { mutableStateOf("Best") }
    var limit by remember { mutableStateOf("All") }
    var scanning by remember { mutableStateOf(false) }
    var entries by remember { mutableStateOf<List<Downloader.Entry>>(emptyList()) }
    var busy by remember { mutableStateOf(false) }
    var progress by remember { mutableStateOf(0f) }
    var log by remember { mutableStateOf("") }
    var hasStorage by remember { mutableStateOf(Storage.hasAccess(ctx)) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { hasStorage = Storage.hasAccess(ctx) }

    Column(
        Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Download a whole channel, playlist or profile.",
            style = MaterialTheme.typography.bodyMedium)

        OutlinedTextField(
            value = url, onValueChange = { url = it },
            label = { Text("Channel / playlist / profile URL") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri)
        )

        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            SegmentedButton(selected = audio, onClick = { audio = true },
                shape = SegmentedButtonDefaults.itemShape(0, 2)) { Text("🎵 Audio (MP3)") }
            SegmentedButton(selected = !audio, onClick = { audio = false },
                shape = SegmentedButtonDefaults.itemShape(1, 2)) { Text("🎬 Video (MP4)") }
        }
        if (!audio) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("Best", "720p", "480p").forEach {
                    FilterChip(selected = quality == it, onClick = { quality = it }, label = { Text(it) })
                }
            }
        }

        Text("How many?", style = MaterialTheme.typography.labelMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("All", "10", "25", "50").forEach {
                FilterChip(selected = limit == it, onClick = { limit = it }, label = { Text(it) })
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = {
                    scanning = true; log = ""; entries = emptyList()
                    scope.launch {
                        val r = Downloader.scanEntries(ctx, url.trim())
                        scanning = false
                        r.fold(
                            onSuccess = { entries = it; log = "Found ${it.size} item(s)." },
                            onFailure = { log = "Scan failed: ${it.message}" }
                        )
                    }
                },
                enabled = url.isNotBlank() && !scanning && !busy,
                modifier = Modifier.weight(1f)
            ) { Text(if (scanning) "Scanning…" else "Scan") }

            Button(
                onClick = {
                    busy = true; progress = 0f; log = "Starting…"
                    scope.launch {
                        val r = Downloader.downloadAll(ctx, url.trim(), audio, quality, limit.toIntOrNull()) { p, line ->
                            progress = p / 100f
                            if (line.isNotBlank()) log = line
                        }
                        busy = false
                        log = r.fold(
                            { "✅ Downloaded $it file(s) to ${Storage.displayPath(Downloader.targetDir(audio))}" },
                            { "❌ Failed: ${it.message}" })
                    }
                },
                enabled = url.isNotBlank() && hasStorage && !busy,
                modifier = Modifier.weight(1f)
            ) { Text(if (busy) "Downloading…" else "Download all") }
        }

        if (!hasStorage) {
            Text("Grant storage access on the Download tab first.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error)
        }

        if (scanning) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        if (busy) LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
        if (log.isNotBlank()) Text(log, style = MaterialTheme.typography.bodySmall)

        if (entries.isNotEmpty()) {
            HorizontalDivider()
            Text("In this link:", style = MaterialTheme.typography.titleSmall)
            entries.take(50).forEachIndexed { i, e ->
                Text("${i + 1}. ${e.title}", style = MaterialTheme.typography.bodySmall, maxLines = 2)
            }
            if (entries.size > 50) {
                Text("…and ${entries.size - 50} more",
                    style = MaterialTheme.typography.bodySmall)
            }
        }

        Spacer(Modifier.height(8.dp))
        Text("Saves to: ${Storage.displayPath(Downloader.targetDir(audio))}",
            style = MaterialTheme.typography.bodySmall)
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
                    OutlinedButton(onClick = { Storage.viewFile(ctx, f) },
                        modifier = Modifier.weight(1f)) { Text("▶ Play") }
                    OutlinedButton(onClick = { Storage.shareFile(ctx, f) },
                        modifier = Modifier.weight(1f)) { Text("↗ Share") }
                }
            }
        }
    }
}

@Composable
fun ContactLinks(ctx: android.content.Context) {
    fun open(uri: String) = ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(uri)))
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        TextButton(onClick = { open("mailto:phantomtyper.review@gmail.com") }) {
            Text("📧 phantomtyper.review@gmail.com")
        }
        TextButton(onClick = { open("https://wa.me/254799553292") }) {
            Text("💬 WhatsApp +254 799 553292")
        }
        TextButton(onClick = { open("https://wa.me/12103296074") }) {
            Text("💬 WhatsApp +1 210 329 6074")
        }
        TextButton(onClick = { open("https://baziqhue.co.ke/") }) {
            Text("🌐 baziqhue.co.ke")
        }
    }
}
