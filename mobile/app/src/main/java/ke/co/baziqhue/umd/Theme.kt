package ke.co.baziqhue.umd

import android.app.Activity
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat

/**
 * BAZIQ HUE design language. A deliberately-designed dark theme with a signature
 * violet→cyan "HUE" gradient — a consistent premium identity (not wallpaper-derived
 * dynamic colour, which looked dull/inconsistent). Used across hero cards, primary
 * buttons, artwork placeholders and the player.
 */

// --- Brand identity -------------------------------------------------------- //
val BrandViolet = Color(0xFF7C5CFF)
val BrandPurple = Color(0xFFB44DFF)
val BrandCyan = Color(0xFF18C8FF)
val BrandPink = Color(0xFFFF5CA8)

/** The signature gradient — use for primary CTAs, hero surfaces, art placeholders. */
val BrandGradient: Brush = Brush.linearGradient(listOf(BrandViolet, BrandPurple, BrandCyan))

/** A softer diagonal wash for large surfaces (player background, hero cards). */
val BrandWash: Brush = Brush.linearGradient(
    0f to Color(0xFF1A1430), 0.5f to Color(0xFF161425), 1f to Color(0xFF101620)
)

private val UmdDark = darkColorScheme(
    primary = Color(0xFFB9A8FF),
    onPrimary = Color(0xFF1A0B3D),
    primaryContainer = Color(0xFF3A2A78),
    onPrimaryContainer = Color(0xFFE7DEFF),
    secondary = Color(0xFF7FE0FF),
    onSecondary = Color(0xFF00344A),
    secondaryContainer = Color(0xFF124A60),
    onSecondaryContainer = Color(0xFFBEEEFF),
    tertiary = Color(0xFFFFA8D2),
    onTertiary = Color(0xFF5A1138),
    tertiaryContainer = Color(0xFF7A2752),
    onTertiaryContainer = Color(0xFFFFD9E8),
    background = Color(0xFF0A0A10),
    onBackground = Color(0xFFEAE8F2),
    surface = Color(0xFF111119),
    onSurface = Color(0xFFEAE8F2),
    surfaceVariant = Color(0xFF23232F),
    onSurfaceVariant = Color(0xFFC6C4D4),
    outline = Color(0xFF3C3C4A),
    error = Color(0xFFFFB4AB),
    onError = Color(0xFF690005),
)

/** Softer, rounder corners across the app — cards, sheets, buttons, chips. */
private val UmdShapes = Shapes(
    extraSmall = RoundedCornerShape(10.dp),
    small = RoundedCornerShape(14.dp),
    medium = RoundedCornerShape(18.dp),
    large = RoundedCornerShape(22.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

@Composable
fun UmdTheme(content: @Composable () -> Unit) {
    val scheme = UmdDark

    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = scheme.background.toArgb()
            window.navigationBarColor = scheme.surface.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(colorScheme = scheme, shapes = UmdShapes, content = content)
}
