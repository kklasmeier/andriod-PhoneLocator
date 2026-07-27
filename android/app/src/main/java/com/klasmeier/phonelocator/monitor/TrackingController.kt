package com.klasmeier.phonelocator.monitor

import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.content.ContextCompat
import com.klasmeier.phonelocator.data.SettingsRepository
import kotlinx.coroutines.flow.first

object TrackingController {
    @Volatile
    private var networkMonitor: NetworkChangeMonitor? = null

    fun start(context: Context) {
        val appContext = context.applicationContext
        val intent = Intent(appContext, LocationTrackingService::class.java)
        ContextCompat.startForegroundService(appContext, intent)
        SyncWorker.schedule(appContext)
        if (networkMonitor == null) {
            networkMonitor = NetworkChangeMonitor(appContext) {
                SyncWorker.enqueueNow(appContext, flushOnly = true)
            }.also { it.register() }
        }
    }

    fun stop(context: Context) {
        val appContext = context.applicationContext
        appContext.stopService(Intent(appContext, LocationTrackingService::class.java))
        networkMonitor?.unregister()
        networkMonitor = null
        SyncWorker.cancelAll(appContext)
    }

    suspend fun ensureRunningIfConfigured(context: Context) {
        val configured = SettingsRepository(context).isConfigured.first()
        val settings = SettingsRepository(context).snapshot()
        if (configured && !settings.trackingPaused) {
            start(context)
        }
    }
}
