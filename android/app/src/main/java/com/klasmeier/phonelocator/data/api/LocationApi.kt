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
}
