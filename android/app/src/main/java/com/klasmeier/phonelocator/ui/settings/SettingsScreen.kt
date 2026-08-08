package com.klasmeier.phonelocator.ui.settings

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.klasmeier.phonelocator.BuildConfig
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.monitor.TrackingController
import com.klasmeier.phonelocator.sync.UploadRepository
import com.klasmeier.phonelocator.ui.AppPermissions
import com.klasmeier.phonelocator.ui.theme.AppThemeMode
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

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onBackground,
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .windowInsetsPadding(WindowInsets.safeDrawing)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                }
                Text("Settings", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
            }

        SettingsSectionCard(title = "Appearance") {
            Text(
                "Theme",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
                AppThemeMode.entries.forEachIndexed { index, mode ->
                    SegmentedButton(
                        selected = settings.themeMode == mode,
                        onClick = {
                            scope.launch { settingsRepository.setThemeMode(mode) }
                        },
                        shape = SegmentedButtonDefaults.itemShape(
                            index = index,
                            count = AppThemeMode.entries.size,
                        ),
                    ) {
                        Text(mode.label)
                    }
                }
            }
            Spacer(Modifier.height(4.dp))
            Text(
                "System follows your phone's light/dark setting.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        SettingsSectionCard(title = "Connection") {
            OutlinedTextField(
                value = apiUrl,
                onValueChange = { apiUrl = it },
                label = { Text("API URL") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            OutlinedTextField(
                value = token,
                onValueChange = { token = it },
                label = { Text("API token") },
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            OutlinedTextField(
                value = deviceId,
                onValueChange = { deviceId = it },
                label = { Text("Device ID") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            OutlinedTextField(
                value = interval,
                onValueChange = { interval = it.filter { ch -> ch.isDigit() }.take(2) },
                label = { Text("Upload interval (minutes)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(
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
                    modifier = Modifier.weight(1f),
                ) { Text("Save") }
                OutlinedButton(
                    onClick = {
                        scope.launch {
                            try {
                                message = "Health: ${uploadRepository.testConnection()}"
                            } catch (exc: Exception) {
                                message = exc.message
                            }
                        }
                    },
                    modifier = Modifier.weight(1f),
                ) { Text("Test") }
            }
        }

        SettingsSectionCard(title = "Permissions") {
            Text(permissionSummary, style = MaterialTheme.typography.bodyMedium)
            Text(
                if (batteryOk) "Battery optimization: disabled for this app ✓" else "Battery optimization: enabled — may stop tracking",
                style = MaterialTheme.typography.bodySmall,
                color = if (batteryOk) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
            )
            SettingsLinkRow(
                label = "Open app permissions",
                onClick = { context.startActivity(AppPermissions.appSettingsIntent(context)) },
            )
            if (!batteryOk) {
                SettingsLinkRow(
                    label = "Disable battery optimization",
                    onClick = { batteryLauncher.launch(AppPermissions.batteryOptimizationIntent(context)) },
                )
            }
        }

        SettingsSectionCard(title = "About") {
            SettingsInfoRow("App version", "${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
            queueSize?.let { SettingsInfoRow("Queue size", "$it points") }
        }

        SettingsSectionCard(title = "Advanced") {
            TextButton(
                onClick = {
                    scope.launch {
                        uploadRepository.clearActivityLog()
                        message = "Activity log cleared"
                    }
                },
            ) {
                Text("Clear activity log")
            }
        }

        message?.let { msg ->
            Text(
                text = msg,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
            )
        }

        Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun SettingsSectionCard(
    title: String,
    content: @Composable () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(
            Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

@Composable
private fun SettingsInfoRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun SettingsLinkRow(label: String, onClick: () -> Unit) {
    HorizontalDivider()
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        TextButton(onClick = onClick) {
            Text(label)
        }
        Icon(
            Icons.Outlined.ChevronRight,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
