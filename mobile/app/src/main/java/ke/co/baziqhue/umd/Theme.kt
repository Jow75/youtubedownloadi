package ke.co.baziqhue.umd

import android.app.Activity
import android.os.Build
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * App theme. Stays dark (the product's look), but modernised:
 *  - Material You dynamic colour on Android 12+ (themes to the user's wallpaper —
 *    a native, current feel, not a flashy custom skin).
 *  - A refined slate-and-blue fallback palette on older devices.
 */
private val FallbackDark = darkColorScheme(
    primary = Color(0xFF8FB6FF),
    onPrimary = Color(0xFF062045),
    primaryContainer = Color(0xFF20406B),
    onPrimaryContainer = Color(0xFFD7E4FF),
    secondary = Color(0xFF9BD4C6),
    onSecondary = Color(0xFF003730),
    secondaryContainer = Color(0xFF1E4E46),
    onSecondaryContainer = Color(0xFFBDEEE0),
    background = Color(0xFF0E1116),
    onBackground = Color(0xFFE6E8EE),
    surface = Color(0xFF13161C),
    onSurface = Color(0xFFE6E8EE),
    surfaceVariant = Color(0xFF262B34),
    onSurfaceVariant = Color(0xFFC4C8D2),
    outline = Color(0xFF3B414C),
    error = Color(0xFFFFB4AB),
    onError = Color(0xFF690005),
)

@Composable
fun UmdTheme(content: @Composable () -> Unit) {
    val ctx = LocalContext.current
    val scheme = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
        dynamicDarkColorScheme(ctx) else FallbackDark

    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = scheme.background.toArgb()
            window.navigationBarColor = scheme.surface.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(colorScheme = scheme, content = content)
}
