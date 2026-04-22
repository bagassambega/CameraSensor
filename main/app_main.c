#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/time.h>
#include <time.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_sntp.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "nvs_flash.h"

#include "protocol_examples_common.h"
#include "mqtt_client.h"

#include "../header/video_frames.h"

static const char *TAG = "MQTT_VIDEO_APP";

/* --------------------------------------------------------------------------
 * Configuration
 * -------------------------------------------------------------------------- */
#define MQTT_TOPIC "esp32/image"


#define MOTION_THRESHOLD 0.008f

typedef struct __attribute__((packed))
{
    uint64_t timestamp_us;
    uint16_t test_group;
    uint16_t sequence_in_test;
    uint32_t image_size;
} image_packet_header_t;


static uint64_t get_epoch_time_us(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return ((uint64_t)tv.tv_sec * 1000000ULL) + (uint64_t)tv.tv_usec;
}



static void sync_time_with_sntp(void)
{
    ESP_LOGI(TAG, "Starting SNTP clock sync");

    esp_sntp_stop();
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_init();

    time_t now = 0;
    struct tm timeinfo = {0};

    for (int retry = 0; retry < 15; retry++)
    {
        time(&now);
        localtime_r(&now, &timeinfo);
        if (timeinfo.tm_year >= (2020 - 1900))
        {
            ESP_LOGI(TAG, "Clock synchronized");
            return;
        }
        ESP_LOGI(TAG, "Waiting for SNTP sync... (%d/15)", retry + 1);
        vTaskDelay(pdMS_TO_TICKS(2000));
    }

    ESP_LOGW(TAG, "SNTP sync timeout, continuing with current clock");
}


static uint8_t *build_packet(const uint8_t *image,
                             size_t image_size,
                             uint16_t test_group,
                             uint16_t sequence_in_test,
                             size_t *out_size)
{
    image_packet_header_t header = {
        .timestamp_us = get_epoch_time_us(),
        .test_group = test_group,
        .sequence_in_test = sequence_in_test,
        .image_size = (uint32_t)image_size,
    };

    size_t total_size = sizeof(image_packet_header_t) + image_size;

    uint8_t *packet = malloc(total_size);
    if (!packet)
    {
        ESP_LOGE(TAG, "Failed to allocate packet (%d bytes)", (int)total_size);
        return NULL;
    }

    memcpy(packet, &header, sizeof(image_packet_header_t));
    memcpy(packet + sizeof(image_packet_header_t), image, image_size);

    *out_size = total_size;
    return packet;
}



static float compute_motion_score(const uint8_t *prev_thumb,
                                  const uint8_t *curr_thumb)
{
    uint32_t sad = 0;
    for (int i = 0; i < THUMBNAIL_SIZE; i++)
    {
        int diff = (int)curr_thumb[i] - (int)prev_thumb[i];
        if (diff < 0)
            diff = -diff;
        sad += (uint32_t)diff;
    }
    /* Normalise: divide by (pixel_count * max_pixel_value) */
    return (float)sad / (float)(THUMBNAIL_SIZE * 255);
}


static void video_playback_task(void *pvParameters)
{
    esp_mqtt_client_handle_t client = (esp_mqtt_client_handle_t)pvParameters;

    /* Frame interval in milliseconds, derived from the video's FPS */
    const uint32_t frame_interval_ms = 1000 / VIDEO_FPS;

    /* Track whether this is the very first frame ever processed.
     * On the first frame there is no previous reference, so we always send it. */
    bool first_frame_ever = true;

    ESP_LOGI(TAG, "=== Video playback starting ===");
    ESP_LOGI(TAG, "  Frames         : %d", VIDEO_FRAME_COUNT);
    ESP_LOGI(TAG, "  FPS            : %d", VIDEO_FPS);
    ESP_LOGI(TAG, "  Interval       : %lu ms", (unsigned long)frame_interval_ms);
    ESP_LOGI(TAG, "  Threshold      : %.4f", MOTION_THRESHOLD);
    ESP_LOGI(TAG, "  Thumbnail      : %dx%d", THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT);

    while (1) /* Loop continuously */
    {
        uint16_t motion_count = 0;
        uint16_t skip_count = 0;

        for (int i = 0; i < VIDEO_FRAME_COUNT; i++)
        {
            const video_frame_t *frame = &video_frames[i];
            float motion_score;

            if (first_frame_ever)
            {
                /* No previous reference exists (always transmit frame 0) */
                motion_score = 1.0f;
                first_frame_ever = false;
            }
            else
            {
                /* Compare with the previous frame.
                 * When i == 0 (start of a new loop), compare with the last
                 * frame of the previous iteration to detect motion. */
                int prev_idx = (i > 0) ? (i - 1) : (VIDEO_FRAME_COUNT - 1);
                motion_score = compute_motion_score(
                    video_frames[prev_idx].thumbnail,
                    frame->thumbnail);
            }

            if (motion_score > MOTION_THRESHOLD)
            {
                /* Motion detected: build and publish packet */
                motion_count++;

                size_t packet_size = 0;
                uint8_t *packet = build_packet(
                    frame->jpeg_data,
                    frame->jpeg_size,
                    0,           /* test_group: unused in Level 2 */
                    (uint16_t)i, /* frame index */
                    &packet_size);

                if (packet)
                {
                    int msg_id = esp_mqtt_client_publish(
                        client,
                        MQTT_TOPIC,
                        (const char *)packet,
                        packet_size,
                        0,  /* QoS 0 */
                        0); /* no retain */

                    ESP_LOGI(TAG,
                             "[MOTION] frame=%d | score=%.4f | jpeg=%lu B | msg_id=%d",
                             i, motion_score,
                             (unsigned long)frame->jpeg_size,
                             msg_id);

                    free(packet);
                }
            }
            else
            {
                /* No movement/difference: skip transmission */
                skip_count++;
                ESP_LOGD(TAG,
                         "[SKIP]   frame=%d | score=%.4f",
                         i, motion_score);
            }

            /* Wait for the next frame interval */
            vTaskDelay(pdMS_TO_TICKS(frame_interval_ms));
        }

        ESP_LOGI(TAG,
                 "=== Loop complete | sent=%d | skipped=%d | total=%d ===",
                 motion_count, skip_count, VIDEO_FRAME_COUNT);

        /* Brief pause between loop iterations */
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

/* --------------------------------------------------------------------------
 * MQTT event handler
 * -------------------------------------------------------------------------- */
static void mqtt_event_handler(void *handler_args,
                               esp_event_base_t base,
                               int32_t event_id,
                               void *event_data)
{
    esp_mqtt_event_handle_t event = event_data;
    esp_mqtt_client_handle_t client = event->client;

    switch ((esp_mqtt_event_id_t)event_id)
    {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "MQTT connected");

        /* Start the video playback + motion detection task */
        xTaskCreate(video_playback_task,
                    "video_task",
                    8192,
                    client,
                    5,
                    NULL);
        break;

    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGI(TAG, "MQTT disconnected");
        break;

    case MQTT_EVENT_PUBLISHED:
        ESP_LOGI(TAG, "Message published, msg_id=%d", event->msg_id);
        break;

    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "MQTT error");
        break;

    default:
        break;
    }
}

/* --------------------------------------------------------------------------
 * MQTT client initialisation
 * -------------------------------------------------------------------------- */
static void mqtt_app_start(void)
{
    const esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = CONFIG_EXAMPLE_MQTT_BROKER_URI,
    };

    esp_mqtt_client_handle_t client = esp_mqtt_client_init(&mqtt_cfg);

    esp_mqtt_client_register_event(client,
                                   ESP_EVENT_ANY_ID,
                                   mqtt_event_handler,
                                   NULL);

    esp_mqtt_client_start(client);
}

/* --------------------------------------------------------------------------
 * Entry point
 * -------------------------------------------------------------------------- */
void app_main(void)
{
    ESP_LOGI(TAG, "=== Level 2: Video Motion Detection Sensor ===");
    ESP_LOGI(TAG, "Embedded video: %d frames, %d FPS", VIDEO_FRAME_COUNT, VIDEO_FPS);

    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    /* Connect WiFi */
    ESP_ERROR_CHECK(example_connect());
    ESP_LOGI(TAG, "WiFi connected");

    /* Synchronize ESP32 wall clock with NTP */
    sync_time_with_sntp();

    /* Start MQTT (video playback begins on MQTT_EVENT_CONNECTED) */
    mqtt_app_start();
}
