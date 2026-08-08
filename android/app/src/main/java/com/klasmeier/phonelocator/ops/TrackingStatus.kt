package com.klasmeier.phonelocator.ops

import com.klasmeier.phonelocator.data.db.ActivityLogEntity
import java.util.concurrent.TimeUnit

enum class TrackingHealth {
    Active,
    Syncing,
    Paused,
    Warning,
    Error,
}

data class UploadStats24h(
    val successCount: Int,
    val failureCount: Int,
) {
    val totalAttempts: Int get() = successCount + failureCount

    /** Null when there were no upload attempts in the window. */
    val successPercent: Int?
        get() = if (totalAttempts == 0) null else ((successCount * 100) / totalAttempts)
}

data class ProblemBanner(
    val message: String,
)

object TrackingStatus {
    /** No alert until uploads have been failing long enough to indicate a real backlog (e.g. VPN off). */
    private val BACKLOG_WARNING_MS = TimeUnit.HOURS.toMillis(4)
    private val BACKLOG_ERROR_MS = TimeUnit.HOURS.toMillis(8)

    fun computeUploadStats24h(
        logs: List<ActivityLogEntity>,
        nowEpochMs: Long = System.currentTimeMillis(),
    ): UploadStats24h {
        val cutoff = nowEpochMs - TimeUnit.HOURS.toMillis(24)
        var successes = 0
        var failures = 0
        for (entry in logs) {
            if (entry.timestampEpochMs < cutoff) continue
            when (entry.level) {
                "success" -> if (isUploadEvent(entry.message)) successes++
                "error" -> if (isUploadEvent(entry.message)) failures++
            }
        }
        return UploadStats24h(successes, failures)
    }

    /**
     * True when points are queued and nothing has uploaded successfully for several hours.
     * Routine successful sends never trigger this.
     */
    fun isUploadBacklogAlert(
        queueCount: Int,
        lastSuccessfulUploadMs: Long?,
        oldestQueuedEpochMs: Long?,
        nowEpochMs: Long = System.currentTimeMillis(),
    ): Boolean {
        if (queueCount == 0) return false
        val backlogSinceMs = lastSuccessfulUploadMs ?: oldestQueuedEpochMs ?: return false
        return nowEpochMs - backlogSinceMs >= BACKLOG_WARNING_MS
    }

    fun isUploadBacklogError(
        queueCount: Int,
        lastSuccessfulUploadMs: Long?,
        oldestQueuedEpochMs: Long?,
        nowEpochMs: Long = System.currentTimeMillis(),
    ): Boolean {
        if (queueCount == 0) return false
        val backlogSinceMs = lastSuccessfulUploadMs ?: oldestQueuedEpochMs ?: return false
        return nowEpochMs - backlogSinceMs >= BACKLOG_ERROR_MS
    }

    fun backlogBannerMessage(
        queueCount: Int,
        lastSuccessfulUploadMs: Long?,
        oldestQueuedEpochMs: Long?,
        nowEpochMs: Long = System.currentTimeMillis(),
    ): String? {
        if (!isUploadBacklogAlert(queueCount, lastSuccessfulUploadMs, oldestQueuedEpochMs, nowEpochMs)) {
            return null
        }
        val backlogSinceMs = lastSuccessfulUploadMs ?: oldestQueuedEpochMs ?: return null
        val hours = TimeUnit.MILLISECONDS.toHours(nowEpochMs - backlogSinceMs).coerceAtLeast(1)
        return "Upload backlog: $queueCount queued, no successful send for ${hours}h — check VPN or connection"
    }

    fun resolveHealth(
        paused: Boolean,
        syncInProgress: Boolean,
        queueCount: Int,
        lastSuccessfulUploadMs: Long?,
        oldestQueuedEpochMs: Long?,
        nowEpochMs: Long = System.currentTimeMillis(),
    ): TrackingHealth {
        if (syncInProgress) return TrackingHealth.Syncing
        if (paused) return TrackingHealth.Paused

        if (isUploadBacklogError(queueCount, lastSuccessfulUploadMs, oldestQueuedEpochMs, nowEpochMs)) {
            return TrackingHealth.Error
        }
        if (isUploadBacklogAlert(queueCount, lastSuccessfulUploadMs, oldestQueuedEpochMs, nowEpochMs)) {
            return TrackingHealth.Warning
        }

        return TrackingHealth.Active
    }

    fun healthLabel(health: TrackingHealth): String = when (health) {
        TrackingHealth.Active -> "Active"
        TrackingHealth.Syncing -> "Syncing"
        TrackingHealth.Paused -> "Paused"
        TrackingHealth.Warning -> "Warning"
        TrackingHealth.Error -> "Error"
    }

    fun formatUptime(serviceStartEpochMs: Long?, nowEpochMs: Long = System.currentTimeMillis()): String {
        if (serviceStartEpochMs == null) return "—"
        val minutes = TimeUnit.MILLISECONDS.toMinutes(nowEpochMs - serviceStartEpochMs).coerceAtLeast(0)
        return when {
            minutes < 60 -> "${minutes}m"
            minutes < 24 * 60 -> "${minutes / 60}h ${minutes % 60}m"
            else -> "${minutes / (24 * 60)}d ${(minutes / 60) % 24}h"
        }
    }

    fun formatRelative(epochMs: Long?, nowEpochMs: Long = System.currentTimeMillis()): String {
        if (epochMs == null) return "—"
        val minutes = TimeUnit.MILLISECONDS.toMinutes(nowEpochMs - epochMs).coerceAtLeast(0)
        return when {
            minutes < 1 -> "just now"
            minutes < 60 -> "${minutes}m ago"
            minutes < 24 * 60 -> "${minutes / 60}h ago"
            else -> "${minutes / (24 * 60)}d ago"
        }
    }

    private fun isUploadEvent(message: String): Boolean {
        val lower = message.lowercase()
        return lower.contains("sent") ||
            lower.contains("upload") ||
            lower.contains("sync") ||
            lower.contains("failed") ||
            lower.contains("401") ||
            lower.contains("unauthorized")
    }
}
