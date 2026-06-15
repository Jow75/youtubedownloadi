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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
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
import kotlinx.coroutines.launch

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

@Composable
fun App() {
    val ctx = LocalContext.current
    val lm = remember { LicenseManager(ctx) }
    var licensed by remember { mutableStateOf(lm.isLicensed()) }

    if (!licensed) {
        LicenseGate(lm) { licensed = true }
    } else {
        DownloadScreen(lm) { licensed = false }
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
fun DownloadScreen(lm: LicenseManager, onDeactivated: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf("") }
    var audio by remember { mutableStateOf(true) }
    var quality by remember { mutableStateOf("Best") }
    var busy by remember { mutableStateOf(false) }
    var progress by remember { mutableFloatStateOf(0f) }
    var log by remember { mutableStateOf("") }
    var done by remember { mutableStateOf<Downloader.Outcome?>(null) }
    var engineStatus by remember { mutableStateOf("") }

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
            value = url, onValueChange = { url = it },
            label = { Text("Paste a link (YouTube, X, TikTok…)") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri)
        )

        // Format: Audio is the primary choice (left), Video second.
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            SegmentedButton(
                selected = audio, onClick = { audio = true },
                shape = SegmentedButtonDefaults.itemShape(0, 2)
            ) { Text("🎵 Audio (MP3)") }
            SegmentedButton(
                selected = !audio, onClick = { audio = false },
                shape = SegmentedButtonDefaults.itemShape(1, 2)
            ) { Text("🎬 Video (MP4)") }
        }
        if (!audio) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("Best", "720p", "480p").forEach {
                    FilterChip(selected = quality == it, onClick = { quality = it },
                        label = { Text(it) })
                }
            }
        }

        Button(
            onClick = {
                busy = true; progress = 0f; log = "Starting…"; done = null
                scope.launch {
                    val res = Downloader.download(ctx, url.trim(), audio, quality) { p, line ->
                        progress = p / 100f
                        if (line.isNotBlank()) log = line
                    }
                    busy = false
                    res.fold(
                        onSuccess = { done = it; log = it.message },
                        onFailure = { done = null; log = "Failed: ${it.message}" }
                    )
                }
            },
            enabled = url.isNotBlank() && !busy && hasStorage, modifier = Modifier.fillMaxWidth()
        ) { Text(if (busy) "Downloading…" else "⬇️ Download") }

        if (busy) LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth())
        if (log.isNotBlank() && done == null) Text(log, style = MaterialTheme.typography.bodySmall)

        done?.let { DownloadDoneCard(ctx, it) }

        Spacer(Modifier.height(8.dp))
        Text("Saves to: ${Storage.displayPath(Downloader.targetDir(audio))}",
            style = MaterialTheme.typography.bodySmall)

        OutlinedButton(
            onClick = { scope.launch { log = Downloader.updateEngine(ctx); done = null } },
            enabled = !busy, modifier = Modifier.fillMaxWidth()
        ) { Text("Update download engine (yt-dlp)") }

        HorizontalDivider()
        ContactLinks(ctx)
        TextButton(onClick = { lm.deactivate(); onDeactivated() }) {
            Text("Remove license from this device")
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
