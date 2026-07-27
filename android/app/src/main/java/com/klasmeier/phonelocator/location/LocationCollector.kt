package com.klasmeier.phonelocator.location

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import androidx.core.content.ContextCompat
import com.google.android.gms.location.CurrentLocationRequest
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import com.klasmeier.phonelocator.data.api.LocationPointPayload
import kotlinx.coroutines.tasks.await
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.UUID
import kotlin.math.max

data class CollectedLocation(
    val payload: LocationPointPayload,
    val recordedAtEpochMs: Long,
)

class LocationCollector(private val context: Context) {
    private val fusedClient = LocationServices.getFusedLocationProviderClient(context)

    suspend fun collect(appVersion: String, uploadAttempt: Int = 1): CollectedLocation? {
        if (!hasLocationPermission()) return null
        val location = fetchLocation() ?: return null
        val recordedAtEpochMs = max(location.time, System.currentTimeMillis())
        val recordedAt = Instant.ofEpochMilli(recordedAtEpochMs)
            .atOffset(ZoneOffset.UTC)
            .format(DateTimeFormatter.ISO_INSTANT)
        val queuedDurationSec = 0
        val payload = LocationPointPayload(
            clientPointId = UUID.randomUUID().toString(),
            latitude = location.latitude,
            longitude = location.longitude,
            accuracyM = if (location.hasAccuracy()) location.accuracy.toDouble() else null,
            altitudeM = if (location.hasAltitude()) location.altitude else null,
            speedMps = if (location.hasSpeed()) location.speed.toDouble() else null,
            bearingDeg = if (location.hasBearing()) location.bearing.toDouble() else null,
            locationProvider = location.provider ?: "fused",
            activity = null,
            batteryPct = batteryPercent(),
            batteryCharging = isCharging(),
            powerSaveMode = isPowerSaveMode(),
            networkType = networkType(),
            wifiSsid = wifiSsidOrNull(),
            appVersion = appVersion,
            uploadAttempt = uploadAttempt,
            queuedDurationSec = queuedDurationSec,
            recordedAt = recordedAt,
        )
        return CollectedLocation(payload = payload, recordedAtEpochMs = recordedAtEpochMs)
    }

    private suspend fun fetchLocation(): Location? {
        val request = CurrentLocationRequest.Builder()
            .setPriority(Priority.PRIORITY_BALANCED_POWER_ACCURACY)
            .setMaxUpdateAgeMillis(5 * 60 * 1000L)
            .build()
        val token = CancellationTokenSource()
        return runCatching {
            fusedClient.getCurrentLocation(request, token.token).await()
        }.getOrNull()
    }

    private fun hasLocationPermission(): Boolean {
        val fine = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION)
        return fine == PackageManager.PERMISSION_GRANTED
    }

    private fun batteryPercent(): Int? {
        val manager = context.getSystemService(BatteryManager::class.java) ?: return null
        return manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
    }

    private fun isCharging(): Boolean {
        val manager = context.getSystemService(BatteryManager::class.java) ?: return false
        val status = manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_STATUS)
        return status == BatteryManager.BATTERY_STATUS_CHARGING ||
            status == BatteryManager.BATTERY_STATUS_FULL
    }

    private fun isPowerSaveMode(): Boolean {
        val pm = context.getSystemService(PowerManager::class.java) ?: return false
        return pm.isPowerSaveMode
    }

    private fun networkType(): String {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return "none"
        val network = cm.activeNetwork ?: return "none"
        val caps = cm.getNetworkCapabilities(network) ?: return "none"
        return when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            else -> "other"
        }
    }

    @Suppress("DEPRECATION")
    private fun wifiSsidOrNull(): String? {
        if (networkType() != "wifi") return null
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED
        ) {
            return null
        }
        val wifi = context.applicationContext.getSystemService(WifiManager::class.java) ?: return null
        val info = wifi.connectionInfo ?: return null
        val ssid = info.ssid?.trim('"')
        return ssid?.takeIf { it.isNotBlank() && it != "<unknown ssid>" }
    }
}
