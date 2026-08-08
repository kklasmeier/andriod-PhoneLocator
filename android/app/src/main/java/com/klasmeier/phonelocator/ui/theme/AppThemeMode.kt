package com.klasmeier.phonelocator.ui.theme

enum class AppThemeMode(val storageKey: String, val label: String) {
    SYSTEM("system", "System"),
    LIGHT("light", "Light"),
    DARK("dark", "Dark"),
    ;

    companion object {
        fun fromStorage(value: String?): AppThemeMode =
            entries.find { it.storageKey == value } ?: SYSTEM
    }
}
