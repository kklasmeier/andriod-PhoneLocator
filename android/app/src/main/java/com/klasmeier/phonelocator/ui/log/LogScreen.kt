package com.klasmeier.phonelocator.ui.log

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.klasmeier.phonelocator.data.db.ActivityLogEntity
import com.klasmeier.phonelocator.sync.UploadRepository
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date

@Composable
fun LogScreen(onBack: () -> Unit, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val uploadRepository = remember { UploadRepository(context) }
    val scope = rememberCoroutineScope()
    val entries = remember { mutableStateListOf<ActivityLogEntity>() }

    LaunchedEffect(Unit) {
        entries.clear()
        entries.addAll(uploadRepository.recentLogs(50))
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
    ) {
        Text("Activity log")
        Button(
            onClick = {
                scope.launch {
                    entries.clear()
                    entries.addAll(uploadRepository.recentLogs(50))
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Refresh") }
        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(entries) { entry ->
                val time = DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(entry.timestampEpochMs))
                val prefix = if (entry.level == "success") "✓" else if (entry.level == "error") "✗" else "·"
                Text("$prefix $time  ${entry.message}")
            }
        }
        Button(onClick = onBack, modifier = Modifier.fillMaxWidth()) { Text("Back") }
    }
}
