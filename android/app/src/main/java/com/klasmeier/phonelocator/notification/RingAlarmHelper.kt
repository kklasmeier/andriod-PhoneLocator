package com.klasmeier.phonelocator.notification

import android.content.Context
import android.media.AudioAttributes
import android.media.Ringtone
import android.media.RingtoneManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.core.content.getSystemService

class RingAlarmHelper(private val context: Context) {
    private val appContext = context.applicationContext
    private val handler = Handler(Looper.getMainLooper())

    fun ring(durationMs: Long = RING_DURATION_MS) {
        vibrate(durationMs)
        val ringtone = defaultRingtone() ?: return
        ringtone.play()
        handler.postDelayed({
            if (ringtone.isPlaying) {
                ringtone.stop()
            }
        }, durationMs)
    }

    private fun defaultRingtone(): Ringtone? {
        val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE) ?: return null
        val ringtone = RingtoneManager.getRingtone(appContext, uri) ?: return null
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            ringtone.audioAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build()
        }
        return ringtone
    }

    private fun vibrate(durationMs: Long) {
        val pattern = longArrayOf(0, 500, 250, 500, 250, 500, 250, 500)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vibrator = appContext.getSystemService<VibratorManager>()?.defaultVibrator
            vibrator?.vibrate(
                VibrationEffect.createWaveform(pattern, -1),
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .build(),
            )
        } else {
            @Suppress("DEPRECATION")
            val vibrator = appContext.getSystemService<Vibrator>()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator?.vibrate(
                    VibrationEffect.createWaveform(pattern, -1),
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .build(),
                )
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(pattern, -1)
            }
        }
        handler.postDelayed({ cancelVibration() }, durationMs)
    }

    private fun cancelVibration() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            appContext.getSystemService<VibratorManager>()?.defaultVibrator?.cancel()
        } else {
            @Suppress("DEPRECATION")
            appContext.getSystemService<Vibrator>()?.cancel()
        }
    }

    companion object {
        private const val RING_DURATION_MS = 30_000L
    }
}
