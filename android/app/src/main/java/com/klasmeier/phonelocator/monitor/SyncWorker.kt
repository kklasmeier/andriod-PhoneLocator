package com.klasmeier.phonelocator.monitor

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.klasmeier.phonelocator.BuildConfig
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.location.LocationCollector
import com.klasmeier.phonelocator.sync.UploadRepository
import java.util.concurrent.TimeUnit

class SyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val settings = SettingsRepository(applicationContext).snapshot()
        if (!settings.setupComplete || settings.trackingPaused) {
            return Result.success()
        }
        val flushOnly = inputData.getBoolean(KEY_FLUSH_ONLY, false)
        val uploadRepository = UploadRepository(applicationContext)
        if (!flushOnly) {
            val collected = LocationCollector(applicationContext).collect(BuildConfig.VERSION_NAME)
            if (collected != null) {
                uploadRepository.enqueue(collected)
            }
        }
        uploadRepository.flushQueue()
        TrackingController.start(applicationContext)
        return Result.success()
    }

    companion object {
        private const val PERIODIC_NAME = "phone_locator_sync"
        private const val KEY_FLUSH_ONLY = "flush_only"

        fun schedule(context: Context) {
            val periodic = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                PERIODIC_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                periodic,
            )
        }

        fun enqueueNow(context: Context, flushOnly: Boolean = false) {
            val once = OneTimeWorkRequestBuilder<SyncWorker>()
                .setInputData(workDataOf(KEY_FLUSH_ONLY to flushOnly))
                .build()
            WorkManager.getInstance(context).enqueue(once)
        }

        fun cancelAll(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(PERIODIC_NAME)
        }
    }
}
