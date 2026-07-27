package com.klasmeier.phonelocator.ui.setup

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
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
import java.util.UUID

@Composable
fun SetupScreen(onComplete: () -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val settingsRepository = remember { SettingsRepository(context) }
    val uploadRepository = remember { UploadRepository(context) }

    var apiUrl by remember {
        mutableStateOf(
            BuildConfig.DEFAULT_API_URL.ifBlank { SettingsRepository.DEFAULT_API_URL },
        )
    }
    var token by remember { mutableStateOf(BuildConfig.DEFAULT_API_TOKEN) }
    var deviceId by remember { mutableStateOf(UUID.randomUUID().toString()) }
    var interval by remember { mutableStateOf(SettingsRepository.DEFAULT_INTERVAL_MINUTES.toString()) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf<String?>(null) }
    var permissionStatus by remember { mutableStateOf(AppPermissions.statusSummary(context)) }
    var permissionMessage by remember { mutableStateOf<String?>(null) }

    fun refreshPermissionStatus() {
        permissionStatus = AppPermissions.statusSummary(context)
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                refreshPermissionStatus()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    val permissionContinuation = remember { mutableStateOf<() -> Unit>({}) }

    val notificationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        refreshPermissionStatus()
        permissionMessage = if (granted) {
            "Notification permission granted."
        } else {
            "Notification permission denied — tracking notification may not show."
        }
        permissionContinuation.value()
    }

    val foregroundLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { results ->
        refreshPermissionStatus()
        val fineGranted = results.values.all { it }
        permissionMessage = if (fineGranted) {
            "Location (while in use) granted. If prompted next, choose Allow all the time."
        } else {
            "Location permission denied — tracking will not work."
        }
        permissionContinuation.value()
    }

    val backgroundLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        refreshPermissionStatus()
        permissionMessage = if (granted) {
            "All permissions granted."
        } else {
            "Background location denied — choose Allow all the time in Settings for reliable tracking."
        }
    }

    permissionContinuation.value = {
        when {
            AppPermissions.notificationPermission()?.let { permission ->
                !AppPermissions.hasNotifications(context)
            } == true -> notificationLauncher.launch(AppPermissions.notificationPermission()!!)
            !AppPermissions.hasFineLocation(context) ->
                foregroundLauncher.launch(AppPermissions.foregroundPermissions())
            AppPermissions.backgroundPermission()?.let { permission ->
                !AppPermissions.hasBackgroundLocation(context)
            } == true -> backgroundLauncher.launch(AppPermissions.backgroundPermission()!!)
            AppPermissions.allGranted(context) ->
                permissionMessage = "All permissions already granted."
        }
    }

    fun requestPermissions() {
        permissionMessage = "Opening permission prompts…"
        if (AppPermissions.allGranted(context)) {
            permissionMessage = "All permissions already granted."
            refreshPermissionStatus()
            return
        }
        permissionContinuation.value()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Phone Locator setup")
        Text("A persistent notification is required while tracking is active.")

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
            keyboardOptions = KeyboardOptions.Default,
            modifier = Modifier.fillMaxWidth(),
        )

        Text(
            text = permissionStatus,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Button(onClick = { requestPermissions() }, modifier = Modifier.fillMaxWidth()) {
            Text(
                if (AppPermissions.allGranted(context)) {
                    "Permissions granted"
                } else {
                    "Grant location & notification permissions"
                },
            )
        }

        permissionMessage?.let {
            Text(
                text = it,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
            )
        }

        Button(
            onClick = {
                scope.launch {
                    busy = true
                    error = null
                    status = null
                    try {
                        settingsRepository.saveSetup(
                            apiBaseUrl = apiUrl,
                            apiToken = token,
                            deviceId = deviceId,
                            uploadIntervalMinutes = interval.toIntOrNull()
                                ?: SettingsRepository.DEFAULT_INTERVAL_MINUTES,
                        )
                        val health = uploadRepository.testConnection()
                        status = "Server health: $health"
                    } catch (exc: Exception) {
                        error = exc.message ?: "Connection test failed"
                    } finally {
                        busy = false
                    }
                }
            },
            enabled = !busy && token.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Test connection")
        }

        Button(
            onClick = {
                scope.launch {
                    busy = true
                    error = null
                    try {
                        settingsRepository.saveSetup(
                            apiBaseUrl = apiUrl,
                            apiToken = token,
                            deviceId = deviceId,
                            uploadIntervalMinutes = interval.toIntOrNull()
                                ?: SettingsRepository.DEFAULT_INTERVAL_MINUTES,
                        )
                        TrackingController.start(context)
                        onComplete()
                    } catch (exc: Exception) {
                        error = exc.message ?: "Save failed"
                    } finally {
                        busy = false
                    }
                }
            },
            enabled = !busy && token.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Save & start tracking")
        }

        status?.let { Text(it) }
        error?.let { Text("Error: $it") }
        if (busy) {
            CircularProgressIndicator()
        }
    }
}
