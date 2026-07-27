package com.klasmeier.phonelocator.sync

import android.content.Context
import com.klasmeier.phonelocator.BuildConfig
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.data.api.ApiClientFactory
import com.klasmeier.phonelocator.data.api.BatchUploadRequest
import com.klasmeier.phonelocator.data.api.LocationPointPayload
import com.klasmeier.phonelocator.data.db.ActivityLogEntity
import com.klasmeier.phonelocator.data.db.AppDatabase
import com.klasmeier.phonelocator.data.db.LatestReadingEntity
import com.klasmeier.phonelocator.data.db.UploadQueueEntity
import com.klasmeier.phonelocator.location.CollectedLocation
import com.klasmeier.phonelocator.location.LocationCollector
import com.klasmeier.phonelocator.notification.TrackingNotificationHelper
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

data class UploadResult(
    val accepted: Int,
    val duplicates: Int,
    val remainingQueue: Int,
)

data class ManualSyncResult(
    val collected: Boolean,
    val upload: UploadResult,
    val message: String,
)

class UploadRepository(
    context: Context,
    private val database: AppDatabase = AppDatabase.get(context),
    private val settingsRepository: SettingsRepository = SettingsRepository(context),
    private val apiFactory: ApiClientFactory = ApiClientFactory(),
) {
    private val appContext = context.applicationContext
    private val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
    private val payloadAdapter = moshi.adapter(LocationPointPayload::class.java)

    suspend fun enqueue(collected: CollectedLocation) = withContext(Dispatchers.IO) {
        val json = payloadAdapter.toJson(collected.payload)
        database.uploadQueueDao().insert(
            UploadQueueEntity(
                clientPointId = collected.payload.clientPointId,
                payloadJson = json,
                recordedAt = collected.payload.recordedAt,
                createdAtEpochMs = collected.recordedAtEpochMs,
            ),
        )
        database.latestReadingDao().upsert(
            LatestReadingEntity(
                latitude = collected.payload.latitude,
                longitude = collected.payload.longitude,
                accuracyM = collected.payload.accuracyM,
                batteryPct = collected.payload.batteryPct,
                networkType = collected.payload.networkType,
                recordedAt = collected.payload.recordedAt,
                recordedAtEpochMs = collected.recordedAtEpochMs,
            ),
        )
        settingsRepository.markCollection(collected.recordedAtEpochMs)
    }

    suspend fun flushQueue(maxBatchSize: Int = 50, logOnSuccess: Boolean = true): UploadResult =
        withContext(Dispatchers.IO) {
        val settings = settingsRepository.snapshot()
        if (settings.apiToken.isBlank() || settings.apiBaseUrl.isBlank()) {
            return@withContext UploadResult(0, 0, database.uploadQueueDao().count())
        }

        val pending = database.uploadQueueDao().oldest(maxBatchSize)
        if (pending.isEmpty()) {
            return@withContext UploadResult(0, 0, 0)
        }

        val nowIso = Instant.now().atOffset(ZoneOffset.UTC).format(DateTimeFormatter.ISO_INSTANT)
        val points = pending.map { row ->
            val base = payloadAdapter.fromJson(row.payloadJson)!!
            val queuedSec = ((System.currentTimeMillis() - row.createdAtEpochMs) / 1000L).toInt().coerceAtLeast(0)
            base.copy(
                uploadAttempt = row.syncAttempts + 1,
                queuedDurationSec = queuedSec,
                recordedAt = base.recordedAt.ifBlank { nowIso },
            )
        }

        settingsRepository.markUploadAttempt(System.currentTimeMillis())
        val api = apiFactory.create(settings.apiBaseUrl)
        return@withContext try {
            val response = api.uploadBatch(
                authorization = "Bearer ${settings.apiToken}",
                body = BatchUploadRequest(
                    deviceId = settings.deviceId.ifBlank { settingsRepository.ensureDeviceId() },
                    points = points,
                ),
            )
            val ids = pending.map { it.clientPointId }
            if (response.accepted > 0 || response.duplicates > 0) {
                database.uploadQueueDao().deleteByIds(ids)
            } else {
                database.uploadQueueDao().incrementAttempts(ids)
            }
            val sentCount = response.accepted + response.duplicates
            if (sentCount > 0) {
                settingsRepository.markSuccessfulUpload(System.currentTimeMillis())
                if (logOnSuccess) {
                    log("success", "Sent $sentCount point(s)")
                }
            }
            if (response.errors.isNotEmpty()) {
                log("error", response.errors.first())
            }
            val remaining = database.uploadQueueDao().count()
            TrackingNotificationHelper(appContext).updateFromState(remaining)
            UploadResult(response.accepted, response.duplicates, remaining)
        } catch (exc: Exception) {
            database.uploadQueueDao().incrementAttempts(pending.map { it.clientPointId })
            log("error", "Failed — ${exc.message ?: "upload error"}")
            val remaining = database.uploadQueueDao().count()
            TrackingNotificationHelper(appContext).updateFromState(remaining, error = true)
            UploadResult(0, 0, remaining)
        }
    }

    suspend fun manualSync(): ManualSyncResult = withContext(Dispatchers.IO) {
        log("info", "Manual sync started")
        val collected = LocationCollector(appContext).collect(appVersion = BuildConfig.VERSION_NAME)
        if (collected == null) {
            val queuedBefore = database.uploadQueueDao().count()
            val upload = if (queuedBefore > 0) {
                flushQueue(logOnSuccess = false)
            } else {
                UploadResult(0, 0, 0)
            }
            val sent = upload.accepted + upload.duplicates
            val message = when {
                sent > 0 ->
                    "Manual sync: could not get location; uploaded $sent queued point(s)"
                queuedBefore > 0 ->
                    "Manual sync: could not get location; upload failed (${upload.remainingQueue} in queue)"
                else -> "Manual sync: could not get location"
            }
            log(if (sent > 0) "success" else "error", message)
            TrackingNotificationHelper(appContext).updateFromState(
                upload.remainingQueue,
                error = sent == 0 && queuedBefore > 0,
            )
            return@withContext ManualSyncResult(collected = false, upload = upload, message = message)
        }

        enqueue(collected)
        val upload = flushQueue(logOnSuccess = false)
        val sent = upload.accepted + upload.duplicates
        val message = when {
            sent > 0 -> "Manual sync: sent $sent point(s)"
            upload.remainingQueue > 0 ->
                "Manual sync: location collected; upload pending (${upload.remainingQueue} in queue)"
            else -> "Manual sync: location collected"
        }
        log(if (sent > 0) "success" else if (upload.remainingQueue > 0) "error" else "info", message)
        ManualSyncResult(collected = true, upload = upload, message = message)
    }

    suspend fun testConnection(): String = withContext(Dispatchers.IO) {
        val settings = settingsRepository.snapshot()
        val api = apiFactory.create(settings.apiBaseUrl)
        api.health().status
    }

    suspend fun queueCount(): Int = withContext(Dispatchers.IO) {
        database.uploadQueueDao().count()
    }

    suspend fun recentLogs(limit: Int = 50): List<ActivityLogEntity> = withContext(Dispatchers.IO) {
        database.activityLogDao().recent(limit)
    }

    private suspend fun log(level: String, message: String) {
        database.activityLogDao().insert(
            ActivityLogEntity(
                timestampEpochMs = System.currentTimeMillis(),
                level = level,
                message = message,
            ),
        )
        database.activityLogDao().trim(100)
    }

    companion object {
        suspend fun logService(context: Context, message: String) {
            val db = AppDatabase.get(context)
            db.activityLogDao().insert(
                ActivityLogEntity(
                    timestampEpochMs = System.currentTimeMillis(),
                    level = "info",
                    message = message,
                ),
            )
            db.activityLogDao().trim(100)
        }
    }
}
