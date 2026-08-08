package com.klasmeier.phonelocator.ui.log

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.klasmeier.phonelocator.data.db.ActivityLogEntity
import com.klasmeier.phonelocator.sync.UploadRepository
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date

@Composable
fun LogScreen(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val uploadRepository = remember { UploadRepository(context) }
    val scope = rememberCoroutineScope()
    val entries = remember { mutableStateListOf<ActivityLogEntity>() }
    var statusMessage by remember { mutableStateOf<String?>(null) }

    fun reload() {
        scope.launch {
            entries.clear()
            entries.addAll(uploadRepository.recentLogs(50))
            statusMessage = null
        }
    }

    LaunchedEffect(Unit) {
        entries.clear()
        entries.addAll(uploadRepository.recentLogs(50))
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("Activity log", style = MaterialTheme.typography.titleMedium)
        Text(
            "Upload and service events (last 50, local only)",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { reload() }, modifier = Modifier.weight(1f)) {
                Text("Refresh")
            }
            OutlinedButton(
                onClick = {
                    scope.launch {
                        uploadRepository.clearActivityLog()
                        entries.clear()
                        statusMessage = "Log cleared"
                    }
                },
                modifier = Modifier.weight(1f),
            ) { Text("Clear") }
        }

        statusMessage?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
        }

        if (entries.isEmpty()) {
            Text("No events yet", modifier = Modifier.weight(1f))
        } else {
            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                items(entries, key = { it.id }) { entry ->
                    LogEntryRow(entry)
                }
            }
        }
    }
}

@Composable
private fun LogEntryRow(entry: ActivityLogEntity) {
    val time = DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(entry.timestampEpochMs))
    val date = DateFormat.getDateInstance(DateFormat.SHORT).format(Date(entry.timestampEpochMs))
    val prefix = when (entry.level) {
        "success" -> "✓"
        "error" -> "✗"
        else -> "·"
    }
    val color = when (entry.level) {
        "success" -> MaterialTheme.colorScheme.primary
        "error" -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.onSurface
    }
    Text(
        text = "$prefix $date $time  ${entry.message}",
        style = MaterialTheme.typography.bodySmall,
        color = color,
    )
}
