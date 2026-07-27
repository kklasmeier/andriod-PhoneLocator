package com.klasmeier.phonelocator

import android.app.Application
import com.klasmeier.phonelocator.data.db.AppDatabase

class PhoneLocatorApp : Application() {
    val database: AppDatabase by lazy { AppDatabase.get(this) }
}
