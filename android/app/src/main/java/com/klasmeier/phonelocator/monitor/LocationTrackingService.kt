package com.klasmeier.phonelocator.monitor

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.content.ContextCompat
import com.klasmeier.phonelocator.BuildConfig
import com.klasmeier.phonelocator.data.ServiceStateRepository
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.location.LocationCollector
import com.klasmeier.phonelocator.notification.RingForegroundService
import com.klasmeier.phonelocator.notification.TrackingNotificationHelper
import com.klasmeier.phonelocator.sync.UploadRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class LocationTrackingService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var loopJob: Job? = null
    private lateinit var settingsRepository: SettingsRepository
    private lateinit var uploadRepository: UploadRepository
    private lateinit var locationCollector: LocationCollector
    private lateinit var notificationHelper: TrackingNotificationHelper

    override fun onCreate() {
        super.onCreate()
        settingsRepository = SettingsRepository(this)
        uploadRepository = UploadRepository(this)
        locationCollector = LocationCollector(this)
        notificationHelper = TrackingNotificationHelper(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_SYNC_NOW -> {
                promoteForegroundMinimal()
                startLoopIfNeeded()
                scope.launch {
                    uploadRepository.manualSync()
                    applyNotificationPolicy()
                }
                return START_STICKY
            }
            ACTION_RING -> {
                val commandId = intent.getStringExtra(EXTRA_COMMAND_ID) ?: return START_STICKY
                val durationSec = intent.getIntExtra(EXTRA_DURATION_SEC, DEFAULT_RING_DURATION_SEC)
                promoteForegroundMinimal()
                startLoopIfNeeded()
                scope.launch {
                    RingForegroundService.start(this@LocationTrackingService, commandId, durationSec)
                    applyNotificationPolicy()
                }
                return START_STICKY
            }
        }

        promoteForegroundMinimal()
        startLoopIfNeeded()
        scope.launch { applyNotificationPolicy() }
        return START_STICKY
    }

    private fun promoteForegroundMinimal() {
        val notification = notificationHelper.buildMinimalForegroundNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                TrackingNotificationHelper.NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION,
            )
        } else {
            startForeground(TrackingNotificationHelper.NOTIFICATION_ID, notification)
        }
    }

    private suspend fun applyNotificationPolicy() {
        uploadRepository.applyNotificationPolicy(
            onShowAlert = { queueCount, paused, lastSuccess, oldestQueued ->
                val notification = notificationHelper.buildAlertNotification(
                    queueCount,
                    paused,
                    lastSuccess,
                    oldestQueued,
                )
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    startForeground(
                        TrackingNotificationHelper.NOTIFICATION_ID,
                        notification,
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION,
                    )
                } else {
                    startForeground(TrackingNotificationHelper.NOTIFICATION_ID, notification)
                }
            },
            onHide = {
                promoteForegroundMinimal()
            },
        )
    }

    private fun startLoopIfNeeded() {
        if (loopJob != null) return
        loopJob = scope.launch {
            ServiceStateRepository(this@LocationTrackingService).markServiceStarted()
            UploadRepository.logService(this@LocationTrackingService, "Service started")
            while (isActive) {
                val settings = settingsRepository.snapshot()
                if (!settings.setupComplete || settings.trackingPaused) {
                    applyNotificationPolicy()
                    delay(5_000)
                    continue
                }
                runCycle(collect = true)
                val intervalMs = settings.uploadIntervalMinutes.coerceAtLeast(1) * 60_000L
                delay(intervalMs)
            }
        }
    }

    private suspend fun runCycle(collect: Boolean) {
        if (collect) {
            promoteForegroundMinimal()
            val collected = locationCollector.collect(appVersion = BuildConfig.VERSION_NAME)
            if (collected != null) {
                uploadRepository.enqueue(collected)
            }
        }
        uploadRepository.flushQueue()
        applyNotificationPolicy()
    }

    override fun onDestroy() {
        scope.launch {
            UploadRepository.logService(this@LocationTrackingService, "Service stopped")
            ServiceStateRepository(this@LocationTrackingService).markServiceStopped()
        }
        loopJob?.cancel()
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val ACTION_SYNC_NOW = "com.klasmeier.phonelocator.SYNC_NOW"
        const val ACTION_RING = "com.klasmeier.phonelocator.RING"
        const val EXTRA_COMMAND_ID = "command_id"
        const val EXTRA_DURATION_SEC = "duration_sec"
        private const val DEFAULT_RING_DURATION_SEC = 30

        fun requestRing(context: Context, commandId: String, durationSec: Int) {
            val intent = Intent(context, LocationTrackingService::class.java).apply {
                action = ACTION_RING
                putExtra(EXTRA_COMMAND_ID, commandId)
                putExtra(EXTRA_DURATION_SEC, durationSec)
            }
            ContextCompat.startForegroundService(context.applicationContext, intent)
        }
    }
}
