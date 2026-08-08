package com.klasmeier.phonelocator.monitor

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.sync.UploadRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val settings = SettingsRepository(context).snapshot()
                val configured = SettingsRepository(context).isConfigured.first()
                if (configured && !settings.trackingPaused) {
                    UploadRepository.logService(context, "Boot restart")
                    TrackingController.start(context)
                }
            } finally {
                pending.finish()
            }
        }
    }
}
