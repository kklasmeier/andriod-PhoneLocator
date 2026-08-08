package com.klasmeier.phonelocator.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColors = lightColorScheme(
    primary = Color(0xFF1565C0),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD6E4FF),
    secondary = Color(0xFF3B82F6),
    background = Color(0xFFF4F6FA),
    surface = Color.White,
    surfaceVariant = Color(0xFFE8EDF4),
    onSurfaceVariant = Color(0xFF5A6B82),
    error = Color(0xFFB3261E),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF3B82F6),
    onPrimary = Color(0xFF0F1419),
    primaryContainer = Color(0xFF1E3A5F),
    secondary = Color(0xFF60A5FA),
    background = Color(0xFF0F1419),
    surface = Color(0xFF1A2332),
    surfaceVariant = Color(0xFF243044),
    onSurface = Color(0xFFE8EDF4),
    onSurfaceVariant = Color(0xFF8B9CB3),
    error = Color(0xFFEF4444),
)

@Composable
fun PhoneLocatorTheme(
    themeMode: AppThemeMode = AppThemeMode.SYSTEM,
    content: @Composable () -> Unit,
) {
    val darkTheme = when (themeMode) {
        AppThemeMode.SYSTEM -> isSystemInDarkTheme()
        AppThemeMode.LIGHT -> false
        AppThemeMode.DARK -> true
    }
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        content = content,
    )
}
