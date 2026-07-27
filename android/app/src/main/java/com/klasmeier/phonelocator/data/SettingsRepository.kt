package com.klasmeier.phonelocator.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.util.UUID

const val DEFAULT_API_URL = "http://192.168.1.26:8000/locator"
const val DEFAULT_INTERVAL_MINUTES = 3

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "phone_locator_settings")

data class AppSettings(
    val apiBaseUrl: String = DEFAULT_API_URL,
    val apiToken: String = "",
    val deviceId: String = "",
    val uploadIntervalMinutes: Int = DEFAULT_INTERVAL_MINUTES,
    val trackingPaused: Boolean = false,
    val setupComplete: Boolean = false,
    val lastSuccessfulUploadEpochMs: Long? = null,
    val lastUploadAttemptEpochMs: Long? = null,
    val lastCollectionEpochMs: Long? = null,
)

class SettingsRepository(private val context: Context) {
    private object Keys {
        val API_BASE_URL = stringPreferencesKey("api_base_url")
        val API_TOKEN = stringPreferencesKey("api_token")
        val DEVICE_ID = stringPreferencesKey("device_id")
        val UPLOAD_INTERVAL_MINUTES = intPreferencesKey("upload_interval_minutes")
        val TRACKING_PAUSED = booleanPreferencesKey("tracking_paused")
        val SETUP_COMPLETE = booleanPreferencesKey("setup_complete")
        val LAST_SUCCESS_UPLOAD_MS = longPreferencesKey("last_success_upload_ms")
        val LAST_UPLOAD_ATTEMPT_MS = longPreferencesKey("last_upload_attempt_ms")
        val LAST_COLLECTION_MS = longPreferencesKey("last_collection_ms")
    }

    val settingsFlow: Flow<AppSettings> = context.dataStore.data.map { prefs -> fromPrefs(prefs) }

    val isConfigured: Flow<Boolean> = settingsFlow.map { it.setupComplete && it.apiToken.isNotBlank() }

    suspend fun snapshot(): AppSettings = settingsFlow.first()

    suspend fun saveSetup(
        apiBaseUrl: String,
        apiToken: String,
        deviceId: String,
        uploadIntervalMinutes: Int,
    ) {
        context.dataStore.edit { prefs ->
            prefs[Keys.API_BASE_URL] = apiBaseUrl.trimEnd('/')
            prefs[Keys.API_TOKEN] = apiToken.trim()
            prefs[Keys.DEVICE_ID] = deviceId.ifBlank { UUID.randomUUID().toString() }
            prefs[Keys.UPLOAD_INTERVAL_MINUTES] = uploadIntervalMinutes.coerceIn(1, 60)
            prefs[Keys.SETUP_COMPLETE] = true
        }
    }

    suspend fun setTrackingPaused(paused: Boolean) {
        context.dataStore.edit { prefs -> prefs[Keys.TRACKING_PAUSED] = paused }
    }

    suspend fun markSuccessfulUpload(epochMs: Long) {
        context.dataStore.edit { prefs ->
            prefs[Keys.LAST_SUCCESS_UPLOAD_MS] = epochMs
            prefs[Keys.LAST_UPLOAD_ATTEMPT_MS] = epochMs
        }
    }

    suspend fun markUploadAttempt(epochMs: Long) {
        context.dataStore.edit { prefs -> prefs[Keys.LAST_UPLOAD_ATTEMPT_MS] = epochMs }
    }

    suspend fun markCollection(epochMs: Long) {
        context.dataStore.edit { prefs -> prefs[Keys.LAST_COLLECTION_MS] = epochMs }
    }

    suspend fun ensureDeviceId(): String {
        val current = snapshot()
        if (current.deviceId.isNotBlank()) return current.deviceId
        val id = UUID.randomUUID().toString()
        context.dataStore.edit { prefs -> prefs[Keys.DEVICE_ID] = id }
        return id
    }

    private fun fromPrefs(prefs: Preferences): AppSettings {
        return AppSettings(
            apiBaseUrl = prefs[Keys.API_BASE_URL] ?: DEFAULT_API_URL,
            apiToken = prefs[Keys.API_TOKEN] ?: "",
            deviceId = prefs[Keys.DEVICE_ID] ?: "",
            uploadIntervalMinutes = prefs[Keys.UPLOAD_INTERVAL_MINUTES] ?: DEFAULT_INTERVAL_MINUTES,
            trackingPaused = prefs[Keys.TRACKING_PAUSED] ?: false,
            setupComplete = prefs[Keys.SETUP_COMPLETE] ?: false,
            lastSuccessfulUploadEpochMs = prefs[Keys.LAST_SUCCESS_UPLOAD_MS],
            lastUploadAttemptEpochMs = prefs[Keys.LAST_UPLOAD_ATTEMPT_MS],
            lastCollectionEpochMs = prefs[Keys.LAST_COLLECTION_MS],
        )
    }

    companion object {
        val DEFAULT_API_URL = com.klasmeier.phonelocator.data.DEFAULT_API_URL
        val DEFAULT_INTERVAL_MINUTES = com.klasmeier.phonelocator.data.DEFAULT_INTERVAL_MINUTES
    }
}
