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

// Include your images
#include "../header/images.h"

static const char *TAG = "MQTT_IMAGE_APP";

// CONFIG
#define XYZ 71
#define T_INTERVAL_SEC ((XYZ % 10) + 1) // = 2 seconds
int send_counts[] = {10, 20, 100};
#define MQTT_TOPIC "esp32/image"

typedef struct __attribute__((packed))
{
    uint64_t timestamp_us;
    uint16_t test_group;
    uint16_t sequence_in_test;
    uint32_t image_size;
} image_packet_header_t;

// IMAGE STRUCT
typedef struct
{
    const uint8_t *data;
    size_t size;
} image_t;

// IMAGE ARRAY
static image_t images[] = {
    {frame_000_jpg, frame_000_jpg_len},
    {frame_001_jpg, frame_001_jpg_len},
    {frame_002_jpg, frame_002_jpg_len},
    {frame_003_jpg, frame_003_jpg_len},
    {frame_004_jpg, frame_004_jpg_len},
    {frame_005_jpg, frame_005_jpg_len},
};

#define NUM_IMAGES (sizeof(images) / sizeof(images[0]))

// PACKET BUILDER
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
        ESP_LOGE(TAG, "Failed to allocate packet");
        return NULL;
    }

    memcpy(packet, &header, sizeof(image_packet_header_t));
    memcpy(packet + sizeof(image_packet_header_t), image, image_size);

    *out_size = total_size;
    return packet;
}

// SENDING TASK
static void send_image_task(void *pvParameters)
{
    esp_mqtt_client_handle_t client = (esp_mqtt_client_handle_t)pvParameters;

    int send_counts[] = {10, 20, 100};
    int num_tests = sizeof(send_counts) / sizeof(send_counts[0]);

    ESP_LOGI(TAG, "Starting transmission: T=%d sec", T_INTERVAL_SEC);

    for (int test = 0; test < num_tests; test++)
    {

        int N = send_counts[test];

        ESP_LOGI(TAG, "=== TEST START: N = %d ===", N);

        for (int i = 0; i < N; i++)
        {

            image_t img = images[i % NUM_IMAGES];

            size_t packet_size = 0;
            uint8_t *packet = build_packet(
                img.data,
                img.size,
                (uint16_t)N,
                (uint16_t)(i + 1),
                &packet_size);

            if (packet)
            {
                int msg_id = esp_mqtt_client_publish(
                    client,
                    MQTT_TOPIC,
                    (const char *)packet,
                    packet_size,
                    0,
                    0);

                ESP_LOGI(TAG,
                         "[N=%d] Sent [%d/%d] | img_idx=%d | size=%d | msg_id=%d | ts_us=%" PRIu64,
                         N,
                         i + 1,
                         N,
                         i % NUM_IMAGES,
                         packet_size,
                         msg_id,
                         get_epoch_time_us());

                free(packet);
            }

            vTaskDelay(pdMS_TO_TICKS(T_INTERVAL_SEC * 1000));
        }

        ESP_LOGI(TAG, "=== TEST END: N = %d ===", N);

        // Optional: pause between tests
        vTaskDelay(pdMS_TO_TICKS(3000));
    }

    ESP_LOGI(TAG, "All test scenarios completed");
    vTaskDelete(NULL);
}

// MQTT EVENT HANDLER
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

        // Start sending images
        xTaskCreate(send_image_task,
                    "send_task",
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

// MQTT INIT
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

// MAIN
void app_main(void)
{
    ESP_LOGI(TAG, "System startup");

    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    // Connect WiFi
    ESP_ERROR_CHECK(example_connect());

    ESP_LOGI(TAG, "WiFi connected");

    // Synchronize ESP32 wall clock with NTP so Linux/ESP32 timestamps share epoch.
    sync_time_with_sntp();

    // Start MQTT
    mqtt_app_start();
}
