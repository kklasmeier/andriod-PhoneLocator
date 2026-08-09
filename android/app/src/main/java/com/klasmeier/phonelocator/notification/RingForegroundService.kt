package com.klasmeier.phonelocator.notification

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import com.klasmeier.phonelocator.BuildConfig
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.data.api.ApiClientFactory
import com.klasmeier.phonelocator.data.api.CommandAckRequest
import com.klasmeier.phonelocator.data.db.AppDatabase
import com.klasmeier.phonelocator.data.db.ActivityLogEntity
import com.klasmeier.phonelocator.location.LocationCollector
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

class RingForegroundService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var sessionJob: Job? = null
    private lateinit var settingsRepository: SettingsRepository
    private lateinit var ringHelper: RingAlarmHelper
    private lateinit var notificationHelper: RingNotificationHelper
    private val finishing = AtomicBoolean(false)
    private var activeCommandId: String? = null

    override fun onCreate() {
        super.onCreate()
        settingsRepository = SettingsRepository(this)
        ringHelper = RingAlarmHelper(this)
        notificationHelper = RingNotificationHelper(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                scope.launch { finishRing(STOPPED_BY_PHONE) }
                return START_NOT_STICKY
            }
            ACTION_START -> {
                val commandId = intent.getStringExtra(EXTRA_COMMAND_ID) ?: return START_NOT_STICKY
                val durationSec = intent.getIntExtra(EXTRA_DURATION_SEC, DEFAULT_DURATION_SEC)
                activeCommandId = commandId
                finishing.set(false)
                RingSessionState.setRinging(true)
                promoteForeground()
                sessionJob?.cancel()
                sessionJob = scope.launch { runRingSession(commandId, durationSec) }
                return START_NOT_STICKY
            }
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        sessionJob?.cancel()
        scope.cancel()
        ringHelper.stop()
        RingSessionState.setRinging(false)
        super.onDestroy()
    }

    private fun promoteForeground() {
        val notification = notificationHelper.buildRingNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                RingNotificationHelper.NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
            )
        } else {
            startForeground(RingNotificationHelper.NOTIFICATION_ID, notification)
        }
    }

    private suspend fun runRingSession(commandId: String, durationSec: Int) {
        val settings = settingsRepository.snapshot()
        if (settings.apiToken.isBlank() || settings.apiBaseUrl.isBlank()) {
            stopSelf()
            return
        }
        val api = ApiClientFactory().create(settings.apiBaseUrl)
        val deviceId = settings.deviceId.ifBlank { settingsRepository.ensureDeviceId() }
        val auth = "Bearer ${settings.apiToken}"
        val safeDurationSec = durationSec.coerceIn(MIN_DURATION_SEC, MAX_DURATION_SEC)
        val deadlineMs = System.currentTimeMillis() + safeDurationSec * 1000L

        try {
            api.startRingCommand(auth, deviceId, commandId)
        } catch (exc: Exception) {
            log("error", "Ring start failed — ${exc.message ?: "unknown error"}")
            RingSessionState.setRinging(false)
            stopSelf()
            return
        }

        promoteForeground()
        ringHelper.start(safeDurationSec * 1000L)
        log("info", "Ringing for up to ${safeDurationSec}s")

        while (scope.isActive && System.currentTimeMillis() < deadlineMs) {
            delay(POLL_INTERVAL_MS)
            if (!scope.isActive || System.currentTimeMillis() >= deadlineMs) break
            try {
                val status = api.getCommand(auth, deviceId, commandId)
                if (status.stopRequested) {
                    finishRing(STOPPED_BY_WEB, api, auth, deviceId, commandId)
                    return
                }
            } catch (exc: Exception) {
                log("error", "Ring status poll failed — ${exc.message ?: "unknown error"}")
            }
        }

        finishRing(STOPPED_BY_COMPLETED, api, auth, deviceId, commandId)
    }

    private suspend fun finishRing(
        stoppedBy: String,
        api: com.klasmeier.phonelocator.data.api.LocationApi? = null,
        auth: String? = null,
        deviceId: String? = null,
        commandId: String? = null,
    ) {
        if (!finishing.compareAndSet(false, true)) return
        ringHelper.stop()
        RingSessionState.setRinging(false)

        val settings = settingsRepository.snapshot()
        val resolvedApi = api ?: ApiClientFactory().create(settings.apiBaseUrl)
        val resolvedAuth = auth ?: "Bearer ${settings.apiToken}"
        val resolvedDeviceId = deviceId ?: settings.deviceId.ifBlank { settingsRepository.ensureDeviceId() }
        val resolvedCommandId = commandId ?: activeCommandId
        if (resolvedCommandId == null) {
            stopService()
            return
        }

        var latitude: Double? = null
        var longitude: Double? = null
        val collected = LocationCollector(this).collect(appVersion = BuildConfig.VERSION_NAME)
        if (collected != null) {
            latitude = collected.payload.latitude
            longitude = collected.payload.longitude
        }

        val message = when (stoppedBy) {
            STOPPED_BY_WEB -> "stopped from website"
            STOPPED_BY_PHONE -> "stopped on phone"
            else -> "ring completed"
        }
        try {
            resolvedApi.ackCommand(
                authorization = resolvedAuth,
                deviceId = resolvedDeviceId,
                commandId = resolvedCommandId,
                body = CommandAckRequest(
                    latitude = latitude,
                    longitude = longitude,
                    message = if (collected != null) message else "$message (no fresh location)",
                    stoppedBy = stoppedBy,
                ),
            )
            log("info", "Ring session ended ($stoppedBy)")
        } catch (exc: Exception) {
            log("error", "Ring ack failed — ${exc.message ?: "unknown error"}")
        }
        stopService()
    }

    private fun stopService() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        stopSelf()
    }

    private suspend fun log(level: String, message: String) {
        AppDatabase.get(this).activityLogDao().insert(
            ActivityLogEntity(
                timestampEpochMs = System.currentTimeMillis(),
                level = level,
                message = message,
            ),
        )
    }

    companion object {
        const val ACTION_START = "com.klasmeier.phonelocator.action.RING_START"
        const val ACTION_STOP = "com.klasmeier.phonelocator.action.RING_STOP"
        const val EXTRA_COMMAND_ID = "command_id"
        const val EXTRA_DURATION_SEC = "duration_sec"

        private const val POLL_INTERVAL_MS = 5_000L
        private const val DEFAULT_DURATION_SEC = 30
        private const val MIN_DURATION_SEC = 5
        private const val MAX_DURATION_SEC = 300
        const val STOPPED_BY_WEB = "web"
        const val STOPPED_BY_PHONE = "phone"
        const val STOPPED_BY_COMPLETED = "completed"

        fun start(context: Context, commandId: String, durationSec: Int) {
            val intent = Intent(context, RingForegroundService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_COMMAND_ID, commandId)
                putExtra(EXTRA_DURATION_SEC, durationSec)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stopRinging(context: Context) {
            val intent = Intent(context, RingForegroundService::class.java).apply {
                action = ACTION_STOP
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
