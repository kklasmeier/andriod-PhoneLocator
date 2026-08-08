package com.klasmeier.phonelocator

import com.klasmeier.phonelocator.data.db.ActivityLogEntity
import com.klasmeier.phonelocator.ops.TrackingHealth
import com.klasmeier.phonelocator.ops.TrackingStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.TimeUnit

class TrackingStatusTest {
    private val now = 1_700_000_000_000L

    @Test
    fun computeUploadStats24h_countsSuccessAndFailure() {
        val logs = listOf(
            log(now - TimeUnit.HOURS.toMillis(1), "success", "Sent 1 point(s)"),
            log(now - TimeUnit.HOURS.toMillis(2), "error", "Failed — timeout"),
            log(now - TimeUnit.HOURS.toMillis(25), "success", "Sent 1 point(s)"),
        )
        val stats = TrackingStatus.computeUploadStats24h(logs, now)
        assertEquals(1, stats.successCount)
        assertEquals(1, stats.failureCount)
        assertEquals(50, stats.successPercent)
    }

    @Test
    fun computeUploadStats24h_returnsNullPercentWhenNoAttempts() {
        val stats = TrackingStatus.computeUploadStats24h(emptyList(), now)
        assertNull(stats.successPercent)
    }

    @Test
    fun resolveHealth_returnsPausedWhenPaused() {
        val health = TrackingStatus.resolveHealth(
            paused = true,
            syncInProgress = false,
            queueCount = 50,
            lastSuccessfulUploadMs = now - TimeUnit.HOURS.toMillis(10),
            oldestQueuedEpochMs = now - TimeUnit.HOURS.toMillis(10),
            nowEpochMs = now,
        )
        assertEquals(TrackingHealth.Paused, health)
    }

    @Test
    fun resolveHealth_staysActiveWhenQueueSmallAndRecentSuccess() {
        val health = TrackingStatus.resolveHealth(
            paused = false,
            syncInProgress = false,
            queueCount = 3,
            lastSuccessfulUploadMs = now - TimeUnit.MINUTES.toMillis(5),
            oldestQueuedEpochMs = now - TimeUnit.MINUTES.toMillis(10),
            nowEpochMs = now,
        )
        assertEquals(TrackingHealth.Active, health)
    }

    @Test
    fun resolveHealth_warnsAfterFourHourBacklog() {
        val health = TrackingStatus.resolveHealth(
            paused = false,
            syncInProgress = false,
            queueCount = 40,
            lastSuccessfulUploadMs = now - TimeUnit.HOURS.toMillis(5),
            oldestQueuedEpochMs = now - TimeUnit.HOURS.toMillis(5),
            nowEpochMs = now,
        )
        assertEquals(TrackingHealth.Warning, health)
    }

    @Test
    fun resolveHealth_errorsAfterEightHourBacklog() {
        val health = TrackingStatus.resolveHealth(
            paused = false,
            syncInProgress = false,
            queueCount = 80,
            lastSuccessfulUploadMs = now - TimeUnit.HOURS.toMillis(9),
            oldestQueuedEpochMs = now - TimeUnit.HOURS.toMillis(9),
            nowEpochMs = now,
        )
        assertEquals(TrackingHealth.Error, health)
    }

    @Test
    fun shouldShowSyncFailureNotification_falseWhenQueueEmpty() {
        assertFalse(
            TrackingStatus.shouldShowSyncFailureNotification(
                queueCount = 0,
                lastSuccessfulUploadMs = now - TimeUnit.HOURS.toMillis(2),
                oldestQueuedEpochMs = null,
                nowEpochMs = now,
            ),
        )
    }

    @Test
    fun shouldShowSyncFailureNotification_falseWhenRecentSuccess() {
        assertFalse(
            TrackingStatus.shouldShowSyncFailureNotification(
                queueCount = 5,
                lastSuccessfulUploadMs = now - TimeUnit.MINUTES.toMillis(10),
                oldestQueuedEpochMs = now - TimeUnit.MINUTES.toMillis(20),
                nowEpochMs = now,
            ),
        )
    }

    @Test
    fun shouldShowSyncFailureNotification_trueAfterThirtyMinutes() {
        assertFalse(
            TrackingStatus.shouldShowSyncFailureNotification(
                queueCount = 3,
                lastSuccessfulUploadMs = now - TimeUnit.MINUTES.toMillis(20),
                oldestQueuedEpochMs = now - TimeUnit.MINUTES.toMillis(25),
                nowEpochMs = now,
            ),
        )
        assertTrue(
            TrackingStatus.shouldShowSyncFailureNotification(
                queueCount = 3,
                lastSuccessfulUploadMs = now - TimeUnit.MINUTES.toMillis(35),
                oldestQueuedEpochMs = now - TimeUnit.MINUTES.toMillis(40),
                nowEpochMs = now,
            ),
        )
    }

    @Test
    fun isUploadBacklogAlert_falseWhenQueueEmpty() {
        assertFalse(
            TrackingStatus.isUploadBacklogAlert(
                queueCount = 0,
                lastSuccessfulUploadMs = now - TimeUnit.HOURS.toMillis(10),
                oldestQueuedEpochMs = null,
                nowEpochMs = now,
            ),
        )
    }

    @Test
    fun isUploadBacklogAlert_falseWhenRecentSuccess() {
        assertFalse(
            TrackingStatus.isUploadBacklogAlert(
                queueCount = 2,
                lastSuccessfulUploadMs = now - TimeUnit.MINUTES.toMillis(3),
                oldestQueuedEpochMs = now - TimeUnit.MINUTES.toMillis(6),
                nowEpochMs = now,
            ),
        )
    }

    @Test
    fun formatUptime_formatsMinutesAndHours() {
        assertEquals("45m", TrackingStatus.formatUptime(now - TimeUnit.MINUTES.toMillis(45), now))
        assertEquals("2h 5m", TrackingStatus.formatUptime(now - TimeUnit.MINUTES.toMillis(125), now))
    }

    private fun log(epochMs: Long, level: String, message: String) =
        ActivityLogEntity(id = epochMs, timestampEpochMs = epochMs, level = level, message = message)
}
