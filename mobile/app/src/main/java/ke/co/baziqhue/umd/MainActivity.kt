package ke.co.baziqhue.umd

import android.Manifest
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Schedule
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
import kotlinx.coroutines.launch
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    App()
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

@Composable
fun App() {
    val ctx = LocalContext.current
    val lm = remember { LicenseManager(ctx) }
    var licensed by remember { mutableStateOf(lm.isLicensed()) }

    if (!licensed) {
        LicenseGate(lm) { licensed = true }
        return
    }

    // Licensed: a two-tab shell (Download / History). State + coroutine scope live
    // here so they persist across tab switches.
    val scope = rememberCoroutineScope()
    val ui = remember { DownloadUi() }
    var tab by remember { mutableStateOf(0) }

    Scaffold(
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = tab == 0, onClick = { tab = 0 },
                    icon = { Icon(Icons.Filled.Download, contentDescription = null) },
                    label = { Text("Download") }
                )
                NavigationBarItem(
                    selected = tab == 1, onClick = { tab = 1 },
                    icon = { Icon(Icons.Filled.Schedule, contentDescription = null) },
                    label = { Text("History") }
                )
            }
        }
    ) { pad ->
        Box(Modifier.fillMaxSize().padding(pad)) {
            when (tab) {
                0 -> DownloadScreen(lm, ui, scope) { licensed = false }
                else -> HistoryScreen { url, audio ->
                    ui.url = url; ui.audio = audio; ui.done = null; tab = 0
                }
            }
        }
    }
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
        Spacer(Modifier.height(8.dp))
        Text("⬇️ Universal Media Downloader", style = MaterialTheme.typography.headlineSmall)
        Text(lm.status(), style = MaterialTheme.typography.bodySmall)

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
        Spacer(Modifier.height(8.dp))
        Text("🕘 Download history", style = MaterialTheme.typography.headlineSmall)

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
