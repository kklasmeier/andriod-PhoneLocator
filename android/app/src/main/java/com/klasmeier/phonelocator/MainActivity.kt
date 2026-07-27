package com.klasmeier.phonelocator

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Place
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import com.klasmeier.phonelocator.data.SettingsRepository
import com.klasmeier.phonelocator.monitor.TrackingController
import com.klasmeier.phonelocator.ui.log.LogScreen
import com.klasmeier.phonelocator.ui.setup.SetupScreen
import com.klasmeier.phonelocator.ui.settings.SettingsScreen
import com.klasmeier.phonelocator.ui.status.StatusScreen
import com.klasmeier.phonelocator.ui.theme.PhoneLocatorTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PhoneLocatorTheme {
                PhoneLocatorAppRoot()
            }
        }
    }
}

@Composable
private fun PhoneLocatorAppRoot() {
    val context = LocalContext.current
    val settingsRepository = remember { SettingsRepository(context) }
    val configured by settingsRepository.isConfigured.collectAsState(initial = false)
    var showSetup by remember { mutableStateOf(false) }
    var showSettings by remember { mutableStateOf(false) }
    var selectedTab by remember { mutableIntStateOf(0) }

    LaunchedEffect(configured) {
        showSetup = !configured
        if (configured) {
            TrackingController.ensureRunningIfConfigured(context)
        }
    }

    when {
        showSetup -> SetupScreen(onComplete = { showSetup = false })
        showSettings -> SettingsScreen(onBack = { showSettings = false })
        else -> {
            Scaffold(
                bottomBar = {
                    NavigationBar {
                        NavigationBarItem(
                            selected = selectedTab == 0,
                            onClick = { selectedTab = 0 },
                            icon = { Icon(Icons.Default.Place, contentDescription = null) },
                            label = { Text("Status") },
                        )
                        NavigationBarItem(
                            selected = selectedTab == 1,
                            onClick = { selectedTab = 1 },
                            icon = { Icon(Icons.Default.List, contentDescription = null) },
                            label = { Text("Log") },
                        )
                    }
                },
            ) { padding ->
                when (selectedTab) {
                    0 -> StatusScreen(
                        onOpenSettings = { showSettings = true },
                        modifier = Modifier.padding(padding),
                    )
                    else -> LogScreen(
                        onBack = { selectedTab = 0 },
                        modifier = Modifier.padding(padding),
                    )
                }
            }
        }
    }
}
