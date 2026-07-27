package com.klasmeier.phonelocator.ui.status

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.data.db.AppDatabase
import com.klasmeier.phonelocator.data.db.LatestReadingEntity
import com.klasmeier.phonelocator.monitor.TrackingController
import com.klasmeier.phonelocator.sync.UploadRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date
import java.util.concurrent.TimeUnit

data class StatusUiState(
    val trackingPaused: Boolean = false,
    val queueCount: Int = 0,
    val lastSentLabel: String = "—",
    val lastReadingLabel: String = "—",
    val latestReading: LatestReadingEntity? = null,
    val intervalMinutes: Int = 3,
    val syncMessage: String? = null,
    val syncInProgress: Boolean = false,
)

class StatusViewModel(
    private val settingsRepository: SettingsRepository,
    private val uploadRepository: UploadRepository,
    private val database: AppDatabase,
) : ViewModel() {
    private val queueFlow = MutableStateFlow(0)
    private val latestFlow = MutableStateFlow<LatestReadingEntity?>(null)
    private val syncMessageFlow = MutableStateFlow<String?>(null)
    private val syncInProgressFlow = MutableStateFlow(false)
    private val _uiState = MutableStateFlow(StatusUiState())
    val uiState: StateFlow<StatusUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            combine(
                settingsRepository.settingsFlow,
                queueFlow,
                latestFlow,
                syncMessageFlow,
                syncInProgressFlow,
            ) { settings, queue, latest, syncMessage, syncInProgress ->
                StatusUiState(
                    trackingPaused = settings.trackingPaused,
                    queueCount = queue,
                    lastSentLabel = formatEpoch(settings.lastSuccessfulUploadEpochMs),
                    lastReadingLabel = formatEpoch(settings.lastCollectionEpochMs),
                    latestReading = latest,
                    intervalMinutes = settings.uploadIntervalMinutes,
                    syncMessage = syncMessage,
                    syncInProgress = syncInProgress,
                )
            }.collect { _uiState.value = it }
        }
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            queueFlow.value = uploadRepository.queueCount()
            latestFlow.value = database.latestReadingDao().get()
        }
    }

    fun syncNow(context: android.content.Context) {
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

    fun togglePause(context: android.content.Context) {
        viewModelScope.launch {
            val paused = !settingsRepository.snapshot().trackingPaused
            settingsRepository.setTrackingPaused(paused)
            if (paused) {
                TrackingController.stop(context)
            } else {
                TrackingController.start(context)
            }
            refresh()
        }
    }

    private fun formatEpoch(epochMs: Long?): String {
        if (epochMs == null) return "—"
        val delta = System.currentTimeMillis() - epochMs
        val minutes = TimeUnit.MILLISECONDS.toMinutes(delta).coerceAtLeast(0)
        val relative = when {
            minutes < 1 -> "just now"
            minutes < 60 -> "${minutes}m ago"
            else -> "${minutes / 60}h ago"
        }
        val time = DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(epochMs))
        return "$relative ($time)"
    }

    class Factory(private val context: android.content.Context) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return StatusViewModel(
                SettingsRepository(context),
                UploadRepository(context),
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

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(if (state.trackingPaused) "Paused" else "Active")
            OutlinedButton(onClick = onOpenSettings) { Text("Settings") }
        }
        Text("Collecting every ${state.intervalMinutes} min")

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            StatCard("Last sent", state.lastSentLabel, Modifier.weight(1f))
            StatCard("Queue", "${state.queueCount} pending", Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            StatCard("Last reading", state.lastReadingLabel, Modifier.weight(1f))
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
            onClick = { viewModel.syncNow(context) },
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
            onClick = { viewModel.togglePause(context) },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (state.trackingPaused) "Resume tracking" else "Pause tracking")
        }
        OutlinedButton(
            onClick = {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(SettingsRepository.DEFAULT_API_URL))
                context.startActivity(intent)
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Open dashboard")
        }
    }
}

@Composable
private fun StatCard(title: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(Modifier.padding(12.dp)) {
            Text(title)
            Text(value)
        }
    }
}
