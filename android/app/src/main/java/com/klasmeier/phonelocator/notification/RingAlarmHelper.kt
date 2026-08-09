package com.klasmeier.phonelocator.notification

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
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
    private var mediaPlayer: MediaPlayer? = null
    private var stopRunnable: Runnable? = null

    fun start(durationMs: Long) {
        stop()
        vibrate(durationMs)
        val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE) ?: return
        mediaPlayer = MediaPlayer().apply {
            setDataSource(appContext, uri)
            isLooping = true
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build(),
                )
            }
            prepare()
            start()
        }
        stopRunnable = Runnable { stop() }
        handler.postDelayed(stopRunnable!!, durationMs)
    }

    fun stop() {
        stopRunnable?.let { handler.removeCallbacks(it) }
        stopRunnable = null
        mediaPlayer?.run {
            if (isPlaying) stop()
            release()
        }
        mediaPlayer = null
        cancelVibration()
    }

    val isPlaying: Boolean
        get() = mediaPlayer?.isPlaying == true

    private fun vibrate(durationMs: Long) {
        val pattern = longArrayOf(0, 500, 250, 500, 250, 500, 250, 500)
        val effect = VibrationEffect.createWaveform(pattern, 0)
        vibrator()?.vibrate(effect)
        handler.postDelayed({ cancelVibration() }, durationMs)
    }

    private fun cancelVibration() {
        vibrator()?.cancel()
    }

    private fun vibrator(): Vibrator? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            appContext.getSystemService<VibratorManager>()?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            appContext.getSystemService<Vibrator>()
        }
}
