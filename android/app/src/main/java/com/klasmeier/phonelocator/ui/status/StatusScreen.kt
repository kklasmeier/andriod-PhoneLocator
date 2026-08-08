package com.klasmeier.phonelocator.ui.status

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.klasmeier.phonelocator.data.DEFAULT_API_URL
import com.klasmeier.phonelocator.data.ServiceStateRepository
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.data.db.AppDatabase
import com.klasmeier.phonelocator.data.db.LatestReadingEntity
import com.klasmeier.phonelocator.monitor.TrackingController
import com.klasmeier.phonelocator.ops.ProblemBanner
import com.klasmeier.phonelocator.ops.TrackingHealth
import com.klasmeier.phonelocator.ops.TrackingStatus
import com.klasmeier.phonelocator.ops.UploadStats24h
import com.klasmeier.phonelocator.sync.UploadRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date
import java.util.concurrent.TimeUnit

data class StatusUiState(
    val health: TrackingHealth = TrackingHealth.Active,
    val trackingPaused: Boolean = false,
    val queueCount: Int = 0,
    val lastSentLabel: String = "—",
    val lastReadingLabel: String = "—",
    val uploadSuccessLabel: String = "—",
    val serviceUptimeLabel: String = "—",
    val latestReading: LatestReadingEntity? = null,
    val intervalMinutes: Int = 3,
    val syncMessage: String? = null,
    val syncInProgress: Boolean = false,
    val problems: List<ProblemBanner> = emptyList(),
)

class StatusViewModel(
    private val context: android.content.Context,
    private val settingsRepository: SettingsRepository,
    private val uploadRepository: UploadRepository,
    private val serviceStateRepository: ServiceStateRepository,
    private val database: AppDatabase,
) : ViewModel() {
    private val queueFlow = MutableStateFlow(0)
    private val oldestQueuedFlow = MutableStateFlow<Long?>(null)
    private val latestFlow = MutableStateFlow<LatestReadingEntity?>(null)
    private val uploadStatsFlow = MutableStateFlow(UploadStats24h(0, 0))
    private val recentLogsFlow = MutableStateFlow(emptyList<com.klasmeier.phonelocator.data.db.ActivityLogEntity>())
    private val serviceStartFlow = MutableStateFlow<Long?>(null)
    private val problemsFlow = MutableStateFlow<List<ProblemBanner>>(emptyList())
    private val syncMessageFlow = MutableStateFlow<String?>(null)
    private val syncInProgressFlow = MutableStateFlow(false)
    private val _uiState = MutableStateFlow(StatusUiState())
    val uiState: StateFlow<StatusUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            settingsRepository.settingsFlow.collect { settings ->
                emitState(settings, syncInProgressFlow.value, syncMessageFlow.value)
            }
        }
        viewModelScope.launch {
            syncInProgressFlow.collect { inProgress ->
                emitState(settingsRepository.snapshot(), inProgress, syncMessageFlow.value)
            }
        }
        viewModelScope.launch {
            syncMessageFlow.collect { message ->
                emitState(settingsRepository.snapshot(), syncInProgressFlow.value, message)
            }
        }
        refresh()
    }

    private suspend fun emitState(
        settings: com.klasmeier.phonelocator.data.AppSettings,
        syncInProgress: Boolean,
        syncMessage: String?,
    ) {
        val queue = queueFlow.value
        val oldestQueued = oldestQueuedFlow.value
        val latest = latestFlow.value
        val uploadStats = uploadStatsFlow.value
        val serviceStart = serviceStartFlow.value
        val problems = problemsFlow.value
        val now = System.currentTimeMillis()

        val health = TrackingStatus.resolveHealth(
            paused = settings.trackingPaused,
            syncInProgress = syncInProgress,
            queueCount = queue,
            lastSuccessfulUploadMs = settings.lastSuccessfulUploadEpochMs,
            oldestQueuedEpochMs = oldestQueued,
            nowEpochMs = now,
        )

        _uiState.value = StatusUiState(
            health = health,
            trackingPaused = settings.trackingPaused,
            queueCount = queue,
            lastSentLabel = formatEpoch(settings.lastSuccessfulUploadEpochMs),
            lastReadingLabel = formatEpoch(settings.lastCollectionEpochMs),
            uploadSuccessLabel = formatUploadSuccess(uploadStats),
            serviceUptimeLabel = TrackingStatus.formatUptime(serviceStart, now),
            latestReading = latest,
            intervalMinutes = settings.uploadIntervalMinutes,
            syncMessage = syncMessage,
            syncInProgress = syncInProgress,
            problems = problems,
        )
    }

    fun refresh() {
        viewModelScope.launch {
            val settings = settingsRepository.snapshot()
            val snapshot = uploadRepository.queueSnapshot()
            queueFlow.value = snapshot.count
            oldestQueuedFlow.value = snapshot.oldestQueuedEpochMs
            latestFlow.value = database.latestReadingDao().get()
            val since = System.currentTimeMillis() - TimeUnit.HOURS.toMillis(24)
            val logs = uploadRepository.logsSince(since)
            recentLogsFlow.value = logs
            uploadStatsFlow.value = TrackingStatus.computeUploadStats24h(logs)
            serviceStartFlow.value = serviceStateRepository.snapshotStartEpochMs()
            val backlogMessage = TrackingStatus.backlogBannerMessage(
                snapshot.count,
                settings.lastSuccessfulUploadEpochMs,
                snapshot.oldestQueuedEpochMs,
            )
            problemsFlow.value = backlogMessage?.let { listOf(ProblemBanner(it)) } ?: emptyList()
            emitState(settings, syncInProgressFlow.value, syncMessageFlow.value)
        }
    }

    fun syncNow() {
        viewModelScope.launch {
            syncInProgressFlow.value = true
            syncMessageFlow.value = "Syncing…"
            TrackingController.start(context)
            try {
                val result = uploadRepository.manualSync()
                syncMessageFlow.value = result.message
            } catch (exc: Exception) {
                syncMessageFlow.value = "Manual sync failed — ${exc.message ?: "unknown error"}"
            } finally {
                syncInProgressFlow.value = false
                refresh()
            }
        }
    }

    fun togglePause() {
        viewModelScope.launch {
            val paused = !settingsRepository.snapshot().trackingPaused
            settingsRepository.setTrackingPaused(paused)
            if (paused) {
                TrackingController.stop(context)
                UploadRepository.logService(context, "Tracking paused by user")
            } else {
                TrackingController.start(context)
                UploadRepository.logService(context, "Tracking resumed by user")
            }
            refresh()
        }
    }

    private fun formatUploadSuccess(stats: UploadStats24h): String {
        val percent = stats.successPercent
        return if (percent == null) {
            "—"
        } else {
            "$percent% (${stats.successCount}/${stats.totalAttempts})"
        }
    }

    private fun formatEpoch(epochMs: Long?): String {
        if (epochMs == null) return "—"
        val relative = TrackingStatus.formatRelative(epochMs)
        val time = DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(epochMs))
        return "$relative ($time)"
    }

    class Factory(private val context: android.content.Context) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return StatusViewModel(
                context.applicationContext,
                SettingsRepository(context),
                UploadRepository(context),
                ServiceStateRepository(context),
                AppDatabase.get(context),
            ) as T
        }
    }
}

@Composable
fun StatusScreen(
    onOpenSettings: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: StatusViewModel = viewModel(factory = StatusViewModel.Factory(LocalContext.current)),
) {
    val state by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                viewModel.refresh()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusDot(state.health)
                Column {
                    Text(
                        text = TrackingStatus.healthLabel(state.health),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = if (state.trackingPaused) {
                            "Tracking paused"
                        } else {
                            "Collecting every ${state.intervalMinutes} min"
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            OutlinedButton(onClick = onOpenSettings) { Text("Settings") }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            StatCard("Last sent", state.lastSentLabel, Modifier.weight(1f))
            StatCard("Queue", "${state.queueCount} pending", Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            StatCard("Last reading", state.lastReadingLabel, Modifier.weight(1f))
            StatCard("Upload success (24h)", state.uploadSuccessLabel, Modifier.weight(1f))
        }
        StatCard("Service uptime", state.serviceUptimeLabel, Modifier.fillMaxWidth())

        if (state.problems.isNotEmpty()) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
            ) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Upload backlog", style = MaterialTheme.typography.titleSmall)
                    state.problems.forEach { problem ->
                        Text(problem.message, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Current location")
                val reading = state.latestReading
                if (reading == null) {
                    Text("No reading yet")
                } else {
                    Text("${reading.latitude}, ${reading.longitude}")
                    reading.accuracyM?.let { Text("±${it.toInt()} m") }
                    Text("Battery ${reading.batteryPct ?: "?"}% · ${reading.networkType ?: "unknown"}")
                }
                OutlinedButton(
                    onClick = {
                        reading?.let {
                            val uri = Uri.parse("geo:${it.latitude},${it.longitude}?q=${it.latitude},${it.longitude}")
                            context.startActivity(Intent(Intent.ACTION_VIEW, uri))
                        }
                    },
                    enabled = reading != null,
                ) { Text("Open in Google Maps") }
            }
        }

        Button(
            onClick = { viewModel.syncNow() },
            enabled = !state.syncInProgress,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (state.syncInProgress) "Syncing…" else "Sync now")
        }
        state.syncMessage?.let { message ->
            Text(
                text = message,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
            )
        }
        OutlinedButton(
            onClick = { viewModel.togglePause() },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (state.trackingPaused) "Resume tracking" else "Pause tracking")
        }
        OutlinedButton(
            onClick = {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(DEFAULT_API_URL))
                context.startActivity(intent)
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Open dashboard")
        }
    }
}

@Composable
private fun StatusDot(health: TrackingHealth) {
    val color = when (health) {
        TrackingHealth.Active -> Color(0xFF4CAF50)
        TrackingHealth.Syncing -> MaterialTheme.colorScheme.primary
        TrackingHealth.Paused -> MaterialTheme.colorScheme.outline
        TrackingHealth.Warning -> Color(0xFFFF9800)
        TrackingHealth.Error -> MaterialTheme.colorScheme.error
    }
    Box(
        modifier = Modifier
            .size(14.dp)
            .background(color, CircleShape),
    )
}

@Composable
private fun StatCard(title: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(Modifier.padding(12.dp)) {
            Text(title, style = MaterialTheme.typography.labelMedium)
            Text(value, style = MaterialTheme.typography.bodyMedium)
        }
    }
}
