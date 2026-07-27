package com.klasmeier.phonelocator.data.db

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query

@Entity(tableName = "upload_queue")
data class UploadQueueEntity(
    @PrimaryKey val clientPointId: String,
    val payloadJson: String,
    val recordedAt: String,
    val createdAtEpochMs: Long,
    val syncAttempts: Int = 0,
)

@Dao
interface UploadQueueDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(entity: UploadQueueEntity)

    @Query("SELECT * FROM upload_queue ORDER BY recordedAt ASC, createdAtEpochMs ASC LIMIT :limit")
    suspend fun oldest(limit: Int): List<UploadQueueEntity>

    @Query("SELECT COUNT(*) FROM upload_queue")
    suspend fun count(): Int

    @Query("DELETE FROM upload_queue WHERE clientPointId IN (:ids)")
    suspend fun deleteByIds(ids: List<String>)

    @Query("UPDATE upload_queue SET syncAttempts = syncAttempts + 1 WHERE clientPointId IN (:ids)")
    suspend fun incrementAttempts(ids: List<String>)
}

@Entity(tableName = "activity_log")
data class ActivityLogEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val timestampEpochMs: Long,
    val level: String,
    val message: String,
)

@Dao
interface ActivityLogDao {
    @Insert
    suspend fun insert(entity: ActivityLogEntity)

    @Query("SELECT * FROM activity_log ORDER BY timestampEpochMs DESC LIMIT :limit")
    suspend fun recent(limit: Int): List<ActivityLogEntity>

    @Query("DELETE FROM activity_log WHERE id NOT IN (SELECT id FROM activity_log ORDER BY timestampEpochMs DESC LIMIT :keep)")
    suspend fun trim(keep: Int)
}

@Entity(tableName = "latest_reading")
data class LatestReadingEntity(
    @PrimaryKey val id: Int = 1,
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Double?,
    val batteryPct: Int?,
    val networkType: String?,
    val recordedAt: String,
    val recordedAtEpochMs: Long,
)

@Dao
interface LatestReadingDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: LatestReadingEntity)

    @Query("SELECT * FROM latest_reading WHERE id = 1 LIMIT 1")
    suspend fun get(): LatestReadingEntity?
}
