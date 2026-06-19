package ke.co.baziqhue.umd

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ProvideTextStyle
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

private val ARTWORK_AUDIO = setOf("mp3", "m4a", "aac", "opus", "ogg", "wav", "flac")

/**
 * A primary call-to-action painted with the signature BAZIQ HUE gradient. Looks
 * premium where a flat filled button looked utilitarian. Content (icon + text)
 * inherits white; disabled falls back to a flat muted surface.
 */
@Composable
fun BrandButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    content: @Composable RowScope.() -> Unit,
) {
    val shape = MaterialTheme.shapes.large
    val fill = if (enabled) Modifier.background(BrandGradient, shape)
    else Modifier.background(MaterialTheme.colorScheme.surfaceVariant, shape)
    Row(
        modifier
            .clip(shape)
            .then(fill)
            .clickable(enabled = enabled, onClick = onClick)
            .heightIn(min = 54.dp)
            .padding(horizontal = 20.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val c = if (enabled) Color.White else MaterialTheme.colorScheme.onSurfaceVariant
        CompositionLocalProvider(LocalContentColor provides c) {
            ProvideTextStyle(MaterialTheme.typography.titleSmall) { content() }
        }
    }
}

/**
 * A frosted "glass" card — a faint translucent fill + hairline border over the
 * branded background. The modern, premium alternative to a flat opaque card.
 */
@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = MaterialTheme.shapes.large
    Column(
        modifier
            .clip(shape)
            .background(Color.White.copy(alpha = 0.055f), shape)
            .border(1.dp, Color.White.copy(alpha = 0.10f), shape)
            .then(if (onClick != null) Modifier.clickable { onClick() } else Modifier)
            .padding(16.dp),
        content = content,
    )
}

/** A consistent section heading with an optional trailing action ("See all"). */
@Composable
fun SectionHeader(title: String, actionLabel: String? = null, onAction: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(top = 6.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
        if (actionLabel != null && onAction != null) TextButton(onClick = onAction) { Text(actionLabel) }
    }
}

/** A small stat tile (e.g. "128 Songs") used on the Home dashboard. */
@Composable
fun StatTile(value: String, label: String, icon: ImageVector, onClick: () -> Unit, modifier: Modifier = Modifier) {
    GlassCard(modifier, onClick = onClick) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.height(6.dp))
        Text(value, style = MaterialTheme.typography.titleLarge)
        Text(label, style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** A pill-shaped floating action button painted with the signature gradient. */
@Composable
fun BrandFab(text: String, icon: ImageVector, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Row(
        modifier
            .clip(CircleShape)
            .background(BrandGradient)
            .clickable { onClick() }
            .heightIn(min = 56.dp)
            .padding(horizontal = 22.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = Color.White)
        Spacer(Modifier.width(10.dp))
        Text(text, color = Color.White, style = MaterialTheme.typography.titleSmall)
    }
}

/**
 * Album/cover artwork for a media file. Shows the embedded cover when present,
 * otherwise a gradient tile with a music/film glyph — so every list item looks
 * intentional (the Spotify/YT-Music feel) instead of a bare filename.
 */
@Composable
fun MediaArtwork(file: File, size: Dp, modifier: Modifier = Modifier, corner: Dp = 12.dp) {
    val path = file.absolutePath
    var bmp by remember(path) { mutableStateOf<ImageBitmap?>(null) }
    LaunchedEffect(path) {
        bmp = withContext(Dispatchers.IO) {
            MediaMeta.artwork(file)?.let {
                runCatching { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() }.getOrNull()
            }
        }
    }
    val shape = RoundedCornerShape(corner)
    Box(modifier.size(size).clip(shape), contentAlignment = Alignment.Center) {
        val art = bmp
        if (art != null) {
            Image(bitmap = art, contentDescription = null, contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize())
        } else {
            Box(Modifier.fillMaxSize().background(BrandGradient), contentAlignment = Alignment.Center) {
                Icon(
                    if (file.extension.lowercase() in ARTWORK_AUDIO) Icons.Filled.MusicNote
                    else Icons.Filled.Movie,
                    contentDescription = null,
                    tint = Color.White.copy(alpha = 0.92f),
                    modifier = Modifier.size(size * 0.42f)
                )
            }
        }
    }
}
