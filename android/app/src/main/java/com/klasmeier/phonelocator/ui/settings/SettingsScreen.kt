package com.klasmeier.phonelocator.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.klasmeier.phonelocator.BuildConfig
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.monitor.TrackingController
import com.klasmeier.phonelocator.sync.UploadRepository
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(onBack: () -> Unit) {
    val context = LocalContext.current
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

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Settings")
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

        Text("App version ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
        message?.let { Text(it) }

        Button(onClick = onBack, modifier = Modifier.fillMaxWidth()) { Text("Back") }
    }
}
