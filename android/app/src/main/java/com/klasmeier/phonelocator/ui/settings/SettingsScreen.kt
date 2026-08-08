package com.klasmeier.phonelocator.ui.settings

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.klasmeier.phonelocator.BuildConfig
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.monitor.TrackingController
import com.klasmeier.phonelocator.sync.UploadRepository
import com.klasmeier.phonelocator.ui.AppPermissions
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val settingsRepository = remember { SettingsRepository(context) }
    val uploadRepository = remember { UploadRepository(context) }
    val settings by settingsRepository.settingsFlow.collectAsState(
        initial = com.klasmeier.phonelocator.data.AppSettings(),
    )

    var apiUrl by remember(settings.apiBaseUrl) { mutableStateOf(settings.apiBaseUrl) }
    var token by remember(settings.apiToken) {
        mutableStateOf(settings.apiToken.ifBlank { BuildConfig.DEFAULT_API_TOKEN })
    }
    var deviceId by remember(settings.deviceId) { mutableStateOf(settings.deviceId) }
    var interval by remember(settings.uploadIntervalMinutes) {
        mutableStateOf(settings.uploadIntervalMinutes.toString())
    }
    var message by remember { mutableStateOf<String?>(null) }
    var queueSize by remember { mutableStateOf<Int?>(null) }
    var permissionSummary by remember { mutableStateOf(AppPermissions.statusSummary(context)) }
    var batteryOk by remember { mutableStateOf(AppPermissions.isBatteryOptimizationDisabled(context)) }

    fun refreshStatus() {
        permissionSummary = AppPermissions.statusSummary(context)
        batteryOk = AppPermissions.isBatteryOptimizationDisabled(context)
        scope.launch { queueSize = uploadRepository.queueCount() }
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) refreshStatus()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    LaunchedEffect(Unit) { refreshStatus() }

    val batteryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { refreshStatus() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Settings", style = MaterialTheme.typography.titleMedium)

        Text("Connection", style = MaterialTheme.typography.titleSmall)
        OutlinedTextField(
            value = apiUrl,
            onValueChange = { apiUrl = it },
            label = { Text("API URL") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            label = { Text("API token") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = deviceId,
            onValueChange = { deviceId = it },
            label = { Text("Device ID") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = interval,
            onValueChange = { interval = it.filter { ch -> ch.isDigit() }.take(2) },
            label = { Text("Upload interval (minutes)") },
            modifier = Modifier.fillMaxWidth(),
        )

        Button(
            onClick = {
                scope.launch {
                    try {
                        settingsRepository.saveSetup(
                            apiBaseUrl = apiUrl,
                            apiToken = token,
                            deviceId = deviceId,
                            uploadIntervalMinutes = interval.toIntOrNull()
                                ?: SettingsRepository.DEFAULT_INTERVAL_MINUTES,
                        )
                        val health = uploadRepository.testConnection()
                        message = "Saved · server health: $health"
                        TrackingController.ensureRunningIfConfigured(context)
                    } catch (exc: Exception) {
                        message = exc.message
                    }
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Save") }

        Button(
            onClick = {
                scope.launch {
                    try {
                        message = "Health: ${uploadRepository.testConnection()}"
                    } catch (exc: Exception) {
                        message = exc.message
                    }
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Test connection") }

        HorizontalDivider()

        Text("Permissions", style = MaterialTheme.typography.titleSmall)
        Text(permissionSummary, style = MaterialTheme.typography.bodySmall)
        Text(
            if (batteryOk) "Battery optimization: disabled for this app ✓" else "Battery optimization: enabled — may stop tracking",
            style = MaterialTheme.typography.bodySmall,
            color = if (batteryOk) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
        )
        OutlinedButton(
            onClick = { context.startActivity(AppPermissions.appSettingsIntent(context)) },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Open app permissions") }
        if (!batteryOk) {
            OutlinedButton(
                onClick = { batteryLauncher.launch(AppPermissions.batteryOptimizationIntent(context)) },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Disable battery optimization") }
        }

        HorizontalDivider()

        Text("About", style = MaterialTheme.typography.titleSmall)
        Text("App version ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
        queueSize?.let { Text("Queue size: $it points") }

        HorizontalDivider()

        Text("Advanced", style = MaterialTheme.typography.titleSmall)
        OutlinedButton(
            onClick = {
                scope.launch {
                    uploadRepository.clearActivityLog()
                    message = "Activity log cleared"
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Clear activity log") }

        message?.let { Text(it) }

        Button(onClick = onBack, modifier = Modifier.fillMaxWidth()) { Text("Back") }
    }
}
