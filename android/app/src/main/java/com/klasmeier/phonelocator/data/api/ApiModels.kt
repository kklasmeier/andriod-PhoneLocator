package com.klasmeier.phonelocator.data.api

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class LocationPointPayload(
    @Json(name = "client_point_id") val clientPointId: String,
    val latitude: Double,
    val longitude: Double,
    @Json(name = "accuracy_m") val accuracyM: Double?,
    @Json(name = "altitude_m") val altitudeM: Double?,
    @Json(name = "speed_mps") val speedMps: Double?,
    @Json(name = "bearing_deg") val bearingDeg: Double?,
    @Json(name = "location_provider") val locationProvider: String?,
    val activity: String?,
    @Json(name = "battery_pct") val batteryPct: Int?,
    @Json(name = "battery_charging") val batteryCharging: Boolean?,
    @Json(name = "power_save_mode") val powerSaveMode: Boolean?,
    @Json(name = "network_type") val networkType: String?,
    @Json(name = "wifi_ssid") val wifiSsid: String?,
    @Json(name = "app_version") val appVersion: String?,
    @Json(name = "upload_attempt") val uploadAttempt: Int,
    @Json(name = "queued_duration_sec") val queuedDurationSec: Int,
    @Json(name = "recorded_at") val recordedAt: String,
)

@JsonClass(generateAdapter = true)
data class BatchUploadRequest(
    @Json(name = "device_id") val deviceId: String,
    val points: List<LocationPointPayload>,
)

@JsonClass(generateAdapter = true)
data class BatchUploadResponse(
    val accepted: Int,
    val duplicates: Int,
    val errors: List<String> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class HealthResponse(
    val status: String,
)
