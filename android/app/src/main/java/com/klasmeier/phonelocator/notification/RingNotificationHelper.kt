package com.klasmeier.phonelocator.notification

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.klasmeier.phonelocator.R

class RingNotificationHelper(private val context: Context) {
    private val manager = context.getSystemService(NotificationManager::class.java)

    fun buildRingNotification(): Notification {
        ensureChannel()
        val stopIntent = Intent(context, RingForegroundService::class.java).apply {
            action = RingForegroundService.ACTION_STOP
        }
        val stopFlags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val stopPending = PendingIntent.getService(context, 1, stopIntent, stopFlags)
        return NotificationCompat.Builder(context, CHANNEL_ID_RING)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(context.getString(R.string.ring_notification_title))
            .setContentText(context.getString(R.string.ring_notification_text))
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .addAction(
                R.drawable.ic_launcher_foreground,
                context.getString(R.string.ring_notification_stop),
                stopPending,
            )
            .build()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID_RING,
            context.getString(R.string.ring_notification_channel_name),
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = context.getString(R.string.ring_notification_channel_description)
        }
        manager.createNotificationChannel(channel)
    }

    companion object {
        const val CHANNEL_ID_RING = "phone_locator_ring"
        const val NOTIFICATION_ID = 2002
    }
}
