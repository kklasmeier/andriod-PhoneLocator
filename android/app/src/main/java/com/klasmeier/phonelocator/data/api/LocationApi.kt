package com.klasmeier.phonelocator.data.api

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST

interface LocationApi {
    @GET("api/v1/health")
    suspend fun health(): HealthResponse

    @POST("api/v1/location/batch")
    suspend fun uploadBatch(
        @Header("Authorization") authorization: String,
        @Body body: BatchUploadRequest,
    ): BatchUploadResponse

    @GET("api/v1/devices/{deviceId}/commands/pending")
    suspend fun pendingCommands(
        @Header("Authorization") authorization: String,
        @retrofit2.http.Path("deviceId") deviceId: String,
    ): PendingCommandsResponse

    @GET("api/v1/devices/{deviceId}/commands/{commandId}")
    suspend fun getCommand(
        @Header("Authorization") authorization: String,
        @retrofit2.http.Path("deviceId") deviceId: String,
        @retrofit2.http.Path("commandId") commandId: String,
    ): CommandOut

    @POST("api/v1/devices/{deviceId}/commands/{commandId}/start")
    suspend fun startRingCommand(
        @Header("Authorization") authorization: String,
        @retrofit2.http.Path("deviceId") deviceId: String,
        @retrofit2.http.Path("commandId") commandId: String,
    ): CommandOut

    @POST("api/v1/devices/{deviceId}/commands/{commandId}/ack")
    suspend fun ackCommand(
        @Header("Authorization") authorization: String,
        @retrofit2.http.Path("deviceId") deviceId: String,
        @retrofit2.http.Path("commandId") commandId: String,
        @Body body: CommandAckRequest,
    )
}
