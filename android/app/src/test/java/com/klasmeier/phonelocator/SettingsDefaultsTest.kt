package com.klasmeier.phonelocator

import com.klasmeier.phonelocator.data.SettingsRepository
import org.junit.Assert.assertEquals
import org.junit.Test

class SettingsDefaultsTest {
    @Test
    fun defaultApiUrl_pointsAtPiSensorsLocator() {
        assertEquals(
            "http://192.168.1.26:8000/locator",
            SettingsRepository.DEFAULT_API_URL,
        )
    }

    @Test
    fun defaultInterval_isThreeMinutes() {
        assertEquals(3, SettingsRepository.DEFAULT_INTERVAL_MINUTES)
    }
}
