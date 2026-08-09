package com.klasmeier.phonelocator.notification

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

object RingSessionState {
    private val _isRinging = MutableStateFlow(false)
    val isRinging: StateFlow<Boolean> = _isRinging.asStateFlow()

    fun setRinging(active: Boolean) {
        _isRinging.value = active
    }
}
