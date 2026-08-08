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

    fun buildForegroundNotification(
        queueCount: Int,
        paused: Boolean = false,
        lastSuccessfulUploadMs: Long? = null,
        oldestQueuedEpochMs: Long? = null,
    ): Notification {
        ensureChannel()
        val now = System.currentTimeMillis()
        val backlogError = TrackingStatus.isUploadBacklogError(
            queueCount,
            lastSuccessfulUploadMs,
            oldestQueuedEpochMs,
            now,
        )
        val backlogWarning = TrackingStatus.isUploadBacklogAlert(
            queueCount,
            lastSuccessfulUploadMs,
            oldestQueuedEpochMs,
            now,
        )
        val text = when {
            paused -> "Paused"
            backlogError -> "Upload backlog · $queueCount queued · check VPN"
            backlogWarning -> "Upload backlog · $queueCount queued · check connection"
            else -> "Tracking active · queue $queueCount"
        }
        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(openAppIntent())
            .setOnlyAlertOnce(true)
            .build()
    }

    fun updateFromState(
        queueCount: Int,
        paused: Boolean = false,
        lastSuccessfulUploadMs: Long? = null,
        oldestQueuedEpochMs: Long? = null,
    ) {
        val notification = buildForegroundNotification(
            queueCount,
            paused,
            lastSuccessfulUploadMs,
            oldestQueuedEpochMs,
        )
        manager.notify(NOTIFICATION_ID, notification)
    }

    private fun openAppIntent(): PendingIntent {
        val intent = Intent(context, MainActivity::class.java)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getActivity(context, 0, intent, flags)
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            context.getString(R.string.notification_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = context.getString(R.string.notification_channel_description)
        }
        manager.createNotificationChannel(channel)
    }

    companion object {
        const val CHANNEL_ID = "phone_locator_tracking"
        const val NOTIFICATION_ID = 1001
    }
}
