package com.klasmeier.phonelocator.notification

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.widget.RemoteViews
import androidx.core.app.NotificationCompat
import com.klasmeier.phonelocator.MainActivity
import com.klasmeier.phonelocator.R

class RingNotificationHelper(private val context: Context) {
    private val manager = context.getSystemService(NotificationManager::class.java)

    fun buildRingNotification(): Notification {
        ensureChannel()
        val stopPending = stopPendingIntent()
        val openAppPending = openAppPendingIntent()
        val collapsedView = buildCollapsedView(stopPending)
        val expandedView = buildExpandedView(stopPending)

        val builder = NotificationCompat.Builder(context, CHANNEL_ID_RING)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(context.getString(R.string.ring_notification_title))
            .setContentText(context.getString(R.string.ring_notification_text))
            .setContentIntent(openAppPending)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setOnlyAlertOnce(false)
            .setCustomContentView(collapsedView)
            .setCustomBigContentView(expandedView)
            .setStyle(NotificationCompat.DecoratedCustomViewStyle())
            .addAction(
                android.R.drawable.ic_menu_close_clear_cancel,
                context.getString(R.string.ring_notification_stop),
                stopPending,
            )

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            builder.setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
        }

        return builder.build()
    }

    private fun buildCollapsedView(stopPending: PendingIntent): RemoteViews {
        val view = RemoteViews(context.packageName, R.layout.notification_ring_collapsed)
        view.setTextViewText(R.id.stop_button, context.getString(R.string.ring_notification_stop))
        view.setOnClickPendingIntent(R.id.stop_button, stopPending)
        return view
    }

    private fun buildExpandedView(stopPending: PendingIntent): RemoteViews {
        val view = RemoteViews(context.packageName, R.layout.notification_ring)
        view.setTextViewText(R.id.ring_title, context.getString(R.string.ring_notification_title))
        view.setTextViewText(R.id.ring_text, context.getString(R.string.ring_notification_text))
        view.setTextViewText(R.id.stop_button, context.getString(R.string.ring_notification_stop))
        view.setOnClickPendingIntent(R.id.stop_button, stopPending)
        return view
    }

    private fun stopPendingIntent(): PendingIntent {
        val stopIntent = Intent(context, RingForegroundService::class.java).apply {
            action = RingForegroundService.ACTION_STOP
        }
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getService(context, 1, stopIntent, flags)
    }

    private fun openAppPendingIntent(): PendingIntent {
        val openIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getActivity(context, 2, openIntent, flags)
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        manager.deleteNotificationChannel(LEGACY_CHANNEL_ID)
        val channel = NotificationChannel(
            CHANNEL_ID_RING,
            context.getString(R.string.ring_notification_channel_name),
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = context.getString(R.string.ring_notification_channel_description)
            setShowBadge(true)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }
        manager.createNotificationChannel(channel)
    }

    companion object {
        private const val LEGACY_CHANNEL_ID = "phone_locator_ring"
        const val CHANNEL_ID_RING = "phone_locator_ring_v2"
        const val NOTIFICATION_ID = 2002
    }
}
