package com.klasmeier.phonelocator.data

import android.app.ActivityManager
import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.klasmeier.phonelocator.monitor.LocationTrackingService
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.serviceStateStore: DataStore<Preferences> by preferencesDataStore(
    name = "phone_locator_service_state",
)

class ServiceStateRepository(private val context: Context) {
    private object Keys {
        val SERVICE_START_MS = longPreferencesKey("service_start_ms")
    }

    val serviceStartEpochMs: Flow<Long?> = context.serviceStateStore.data.map { prefs ->
        prefs[Keys.SERVICE_START_MS]
    }

    suspend fun snapshotStartEpochMs(): Long? = serviceStartEpochMs.first()

    suspend fun markServiceStarted(epochMs: Long = System.currentTimeMillis()) {
        context.serviceStateStore.edit { prefs ->
            val existing = prefs[Keys.SERVICE_START_MS]
            if (existing == null) {
                prefs[Keys.SERVICE_START_MS] = epochMs
            }
        }
    }

    suspend fun markServiceStopped() {
        context.serviceStateStore.edit { prefs ->
            prefs.remove(Keys.SERVICE_START_MS)
        }
    }

    fun isServiceRunning(): Boolean {
        val manager = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        @Suppress("DEPRECATION")
        return manager.getRunningServices(Int.MAX_VALUE).any { info ->
            info.service.className == LocationTrackingService::class.java.name
        }
    }
}
