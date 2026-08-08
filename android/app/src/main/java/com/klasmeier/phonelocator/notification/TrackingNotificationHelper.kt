package com.klasmeier.phonelocator.notification

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.klasmeier.phonelocator.MainActivity
import com.klasmeier.phonelocator.R
import com.klasmeier.phonelocator.ops.TrackingStatus

class TrackingNotificationHelper(private val context: Context) {
    private val manager = context.getSystemService(NotificationManager::class.java)

    /** Minimal notification required while briefly in the foreground for location access. */
    fun buildMinimalForegroundNotification(): Notification {
        ensureChannels()
        return NotificationCompat.Builder(context, CHANNEL_ID_SILENT)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(context.getString(R.string.notification_running_silent))
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setContentIntent(openAppIntent())
            .setOnlyAlertOnce(true)
            .build()
    }

    fun buildAlertNotification(
        queueCount: Int,
        paused: Boolean = false,
        lastSuccessfulUploadMs: Long? = null,
        oldestQueuedEpochMs: Long? = null,
    ): Notification {
        ensureChannels()
        val now = System.currentTimeMillis()
        val backlogError = TrackingStatus.isUploadBacklogError(
            queueCount,
            lastSuccessfulUploadMs,
            oldestQueuedEpochMs,
            now,
        )
        val text = when {
            paused -> context.getString(R.string.notification_paused)
            backlogError -> context.getString(R.string.notification_backlog_error, queueCount)
            else -> context.getString(R.string.notification_backlog_warning, queueCount)
        }
        return NotificationCompat.Builder(context, CHANNEL_ID_ALERT)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(openAppIntent())
            .setOnlyAlertOnce(true)
            .build()
    }

    fun showAlertNotification(
        queueCount: Int,
        paused: Boolean = false,
        lastSuccessfulUploadMs: Long? = null,
        oldestQueuedEpochMs: Long? = null,
    ) {
        val notification = buildAlertNotification(
            queueCount,
            paused,
            lastSuccessfulUploadMs,
            oldestQueuedEpochMs,
        )
        manager.notify(NOTIFICATION_ID, notification)
    }

    fun cancelNotification() {
        manager.cancel(NOTIFICATION_ID)
    }

    private fun openAppIntent(): PendingIntent {
        val intent = Intent(context, MainActivity::class.java)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getActivity(context, 0, intent, flags)
    }

    private fun ensureChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val silent = NotificationChannel(
            CHANNEL_ID_SILENT,
            context.getString(R.string.notification_channel_name),
            NotificationManager.IMPORTANCE_MIN,
        ).apply {
            description = context.getString(R.string.notification_channel_description)
            setShowBadge(false)
        }
        val alert = NotificationChannel(
            CHANNEL_ID_ALERT,
            context.getString(R.string.notification_channel_alert_name),
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = context.getString(R.string.notification_channel_alert_description)
        }
        manager.createNotificationChannel(silent)
        manager.createNotificationChannel(alert)
    }

    companion object {
        const val CHANNEL_ID_SILENT = "phone_locator_tracking_silent"
        const val CHANNEL_ID_ALERT = "phone_locator_tracking_alert"
        const val NOTIFICATION_ID = 1001
    }
}
