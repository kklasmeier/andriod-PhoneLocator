package com.klasmeier.phonelocator.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.content.ContextCompat
import com.klasmeier.phonelocator.ops.ProblemBanner

object AppPermissions {
    fun hasFineLocation(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    fun hasBackgroundLocation(context: Context): Boolean =
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            hasFineLocation(context)
        } else {
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.ACCESS_BACKGROUND_LOCATION,
            ) == PackageManager.PERMISSION_GRANTED
        }

    fun hasNotifications(context: Context): Boolean =
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            true
        } else {
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED
        }

    fun allGranted(context: Context): Boolean =
        hasFineLocation(context) && hasBackgroundLocation(context) && hasNotifications(context)

    fun isBatteryOptimizationDisabled(context: Context): Boolean {
        val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
        return powerManager.isIgnoringBatteryOptimizations(context.packageName)
    }

    fun detectProblems(context: Context, serviceRunning: Boolean, paused: Boolean): List<ProblemBanner> {
        val problems = mutableListOf<ProblemBanner>()
        if (!hasFineLocation(context)) {
            problems += ProblemBanner("Location permission not granted")
        } else if (!hasBackgroundLocation(context)) {
            problems += ProblemBanner("Background location not granted — use Allow all the time")
        }
        if (!hasNotifications(context)) {
            problems += ProblemBanner("Notification permission not granted")
        }
        if (!isBatteryOptimizationDisabled(context)) {
            problems += ProblemBanner("Battery optimization enabled — may stop tracking")
        }
        if (!paused && !serviceRunning) {
            problems += ProblemBanner("Tracking service is not running")
        }
        return problems
    }

    fun batteryOptimizationIntent(context: Context): Intent =
        Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
            data = Uri.parse("package:${context.packageName}")
        }

    fun appSettingsIntent(context: Context): Intent =
        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
            data = Uri.parse("package:${context.packageName}")
        }

    fun statusSummary(context: Context): String {
        val location = when {
            hasBackgroundLocation(context) -> "Location: always (background OK)"
            hasFineLocation(context) -> "Location: while in use only — tap button for background"
            else -> "Location: not granted"
        }
        val notifications = if (hasNotifications(context)) {
            "Notifications: granted"
        } else {
            "Notifications: not granted"
        }
        return "$location\n$notifications"
    }

    fun foregroundPermissions(): Array<String> = arrayOf(
        Manifest.permission.ACCESS_FINE_LOCATION,
        Manifest.permission.ACCESS_COARSE_LOCATION,
    )

    fun backgroundPermission(): String? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            Manifest.permission.ACCESS_BACKGROUND_LOCATION
        } else {
            null
        }

    fun notificationPermission(): String? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.POST_NOTIFICATIONS
        } else {
            null
        }
}
