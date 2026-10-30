// ESP32-C3 telemetry publisher for MQTT Telemetry Hub.
// Topics: home/esp32c3/{rssi,heap,uptime}
// Board: ESP32-C3 Dev Module (esp32:esp32:esp32c3), USB CDC On Boot = Enabled
// Library: PubSubClient

#include <WiFi.h>
#include <PubSubClient.h>

static const char *WIFI_SSID = "YOUR_WIFI";
static const char *WIFI_PASS = "YOUR_PASSWORD";
static const char *MQTT_HOST = "192.168.1.10";
static const uint16_t MQTT_PORT = 1883;
static const char *MQTT_USER = "esp32";
static const char *MQTT_PASS = "change-me";

WiFiClient net;
PubSubClient mqtt(net);

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("esp32c3");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
  WiFi.setSleep(false);
}

void connectMqtt() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  if (mqtt.connect("esp32c3", MQTT_USER, MQTT_PASS, "home/esp32c3/status", 0, true, "offline")) {
    mqtt.publish("home/esp32c3/status", "online", true);
  }
}

void setup() {
  Serial.begin(115200);
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();

  mqtt.publish("home/esp32c3/rssi", String(WiFi.RSSI()).c_str(), true);
  mqtt.publish("home/esp32c3/heap", String(ESP.getFreeHeap()).c_str(), true);
  mqtt.publish("home/esp32c3/uptime", String(millis() / 1000).c_str(), true);
  delay(10000);
}
