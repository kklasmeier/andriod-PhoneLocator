package com.klasmeier.phonelocator.ui.status

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.klasmeier.phonelocator.R
import com.klasmeier.phonelocator.data.DEFAULT_API_URL
import com.klasmeier.phonelocator.data.ServiceStateRepository
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.data.db.AppDatabase
import com.klasmeier.phonelocator.data.db.LatestReadingEntity
import com.klasmeier.phonelocator.monitor.TrackingController
import com.klasmeier.phonelocator.notification.RingForegroundService
import com.klasmeier.phonelocator.notification.RingSessionState
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
    val isRinging by RingSessionState.isRinging.collectAsState()
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
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Phone Locator", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
            IconButton(onClick = onOpenSettings) {
                Icon(Icons.Default.Settings, contentDescription = "Settings")
            }
        }

        if (isRinging) {
            RingingStopCard(
                onStop = { RingForegroundService.stopRinging(context) },
            )
        }

        StatusHeroCard(
            health = state.health,
            trackingPaused = state.trackingPaused,
            intervalMinutes = state.intervalMinutes,
            onOpenDashboard = {
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(DEFAULT_API_URL)))
            },
        )

        QuickActionsRow(
            syncInProgress = state.syncInProgress,
            trackingPaused = state.trackingPaused,
            mapsEnabled = state.latestReading != null,
            onSync = { viewModel.syncNow() },
            onTogglePause = { viewModel.togglePause() },
            onOpenMaps = {
                state.latestReading?.let { reading ->
                    val uri = Uri.parse("geo:${reading.latitude},${reading.longitude}?q=${reading.latitude},${reading.longitude}")
                    context.startActivity(Intent(Intent.ACTION_VIEW, uri))
                }
            },
        )

        state.syncMessage?.let { message ->
            Text(
                text = message,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
            )
        }

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

        DetailsCard(
            lastSent = state.lastSentLabel,
            queueCount = state.queueCount,
            lastReading = state.lastReadingLabel,
            uploadSuccess = state.uploadSuccessLabel,
            serviceUptime = state.serviceUptimeLabel,
            latestReading = state.latestReading,
            onOpenMaps = {
                state.latestReading?.let { reading ->
                    val uri = Uri.parse("geo:${reading.latitude},${reading.longitude}?q=${reading.latitude},${reading.longitude}")
                    context.startActivity(Intent(Intent.ACTION_VIEW, uri))
                }
            },
        )
    }
}

@Composable
private fun RingingStopCard(onStop: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.ring_in_app_title),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
            Text(
                text = stringResource(R.string.ring_in_app_subtitle),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
            Button(
                onClick = onStop,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.error,
                    contentColor = MaterialTheme.colorScheme.onError,
                ),
            ) {
                Text(
                    text = stringResource(R.string.ring_in_app_stop),
                    fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.labelLarge,
                )
            }
        }
    }
}

@Composable
private fun StatusHeroCard(
    health: TrackingHealth,
    trackingPaused: Boolean,
    intervalMinutes: Int,
    onOpenDashboard: () -> Unit,
) {
    val accent = healthAccentColor(health)
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = accent.copy(alpha = 0.12f),
        ),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatusDot(health)
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = TrackingStatus.healthLabel(health),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = if (trackingPaused) {
                            "Tracking paused"
                        } else {
                            "Collecting every $intervalMinutes min"
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .clickable(onClick = onOpenDashboard),
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(12.dp),
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(
                        Icons.AutoMirrored.Filled.OpenInNew,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onPrimary,
                    )
                    Spacer(Modifier.width(12.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            "Open web dashboard",
                            style = MaterialTheme.typography.titleSmall,
                            color = MaterialTheme.colorScheme.onPrimary,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            "Timeline, map, places & travel",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.85f),
                        )
                    }
                    Icon(
                        Icons.Outlined.ChevronRight,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onPrimary,
                    )
                }
            }
        }
    }
}

@Composable
private fun QuickActionsRow(
    syncInProgress: Boolean,
    trackingPaused: Boolean,
    mapsEnabled: Boolean,
    onSync: () -> Unit,
    onTogglePause: () -> Unit,
    onOpenMaps: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        QuickActionTile(
            label = if (syncInProgress) "Syncing…" else "Sync now",
            icon = Icons.Default.Sync,
            onClick = onSync,
            enabled = !syncInProgress,
            loading = syncInProgress,
            modifier = Modifier.weight(1f),
        )
        QuickActionTile(
            label = if (trackingPaused) "Resume" else "Pause",
            icon = if (trackingPaused) Icons.Default.PlayArrow else Icons.Default.Pause,
            onClick = onTogglePause,
            modifier = Modifier.weight(1f),
        )
        QuickActionTile(
            label = "Maps",
            icon = Icons.Default.Map,
            onClick = onOpenMaps,
            enabled = mapsEnabled,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun QuickActionTile(
    label: String,
    icon: ImageVector,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
) {
    Card(
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .clickable(enabled = enabled && !loading, onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 12.dp, horizontal = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            if (loading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(22.dp),
                    strokeWidth = 2.dp,
                )
            } else {
                Icon(
                    icon,
                    contentDescription = label,
                    modifier = Modifier.size(22.dp),
                    tint = if (enabled) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f)
                    },
                )
            }
            Text(
                text = label,
                style = MaterialTheme.typography.labelMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun DetailsCard(
    lastSent: String,
    queueCount: Int,
    lastReading: String,
    uploadSuccess: String,
    serviceUptime: String,
    latestReading: LatestReadingEntity?,
    onOpenMaps: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(vertical = 4.dp)) {
            DetailRow("Last sent", lastSent)
            DetailRow("Queue", "$queueCount pending")
            DetailRow("Last reading", lastReading)
            DetailRow("Upload success (24h)", uploadSuccess)
            DetailRow("Service uptime", serviceUptime)
            HorizontalDivider(modifier = Modifier.padding(horizontal = 16.dp))
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(enabled = latestReading != null, onClick = onOpenMaps)
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text("Current location", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(4.dp))
                    if (latestReading == null) {
                        Text("No reading yet", style = MaterialTheme.typography.bodyMedium)
                    } else {
                        Text(
                            "${latestReading.latitude}, ${latestReading.longitude}",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        latestReading.accuracyM?.let {
                            Text("±${it.toInt()} m", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text(
                            "Battery ${latestReading.batteryPct ?: "?"}% · ${latestReading.networkType ?: "unknown"}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                if (latestReading != null) {
                    Icon(
                        Icons.Default.Map,
                        contentDescription = "Open in Maps",
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(start = 8.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(0.42f),
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(0.58f),
        )
    }
}

@Composable
private fun StatusDot(health: TrackingHealth) {
    Box(
        modifier = Modifier
            .size(14.dp)
            .background(healthAccentColor(health), CircleShape),
    )
}

@Composable
private fun healthAccentColor(health: TrackingHealth): Color = when (health) {
    TrackingHealth.Active -> Color(0xFF4CAF50)
    TrackingHealth.Syncing -> MaterialTheme.colorScheme.primary
    TrackingHealth.Paused -> MaterialTheme.colorScheme.outline
    TrackingHealth.Warning -> Color(0xFFFF9800)
    TrackingHealth.Error -> MaterialTheme.colorScheme.error
}
