package com.klasmeier.phonelocator.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [
        UploadQueueEntity::class,
        ActivityLogEntity::class,
        LatestReadingEntity::class,
    ],
    version = 1,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun uploadQueueDao(): UploadQueueDao
    abstract fun activityLogDao(): ActivityLogDao
    abstract fun latestReadingDao(): LatestReadingDao

    companion object {
        @Volatile
        private var instance: AppDatabase? = null

        fun get(context: Context): AppDatabase {
            return instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "phone_locator.db",
                ).build().also { instance = it }
            }
        }
    }
}
