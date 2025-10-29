/**
 * led_controller.ino
 * Recibe líneas Serial tipo: "RGB,r,g,b\n" y pinta toda la tira WS2812B.
 * Usa FastLED en el pin 6. Ajusta NUM_LEDS según tu tira.
 */
#include <FastLED.h>

#define LED_PIN     6
#define NUM_LEDS    30
#define BRIGHTNESS  255
#define LED_TYPE    NEOPIXEL  // WS2812B
#define COLOR_ORDER GRB

CRGB leds[NUM_LEDS];

String inputLine = "";

void setup() {
  FastLED.addLeds<LED_TYPE, LED_PIN>(leds, NUM_LEDS);
  FastLED.setBrightness(BRIGHTNESS);
  Serial.begin(9600);
  fill_solid(leds, NUM_LEDS, CRGB::Black);
  FastLED.show();
}

void applyRGB(uint8_t r, uint8_t g, uint8_t b) {
  CRGB color = CRGB(r, g, b);
  fill_solid(leds, NUM_LEDS, color);
  FastLED.show();
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      // parse
      if (inputLine.startsWith("RGB")) {
        // formato: "RGB,r,g,b"
        int first = inputLine.indexOf(',');
        int second = inputLine.indexOf(',', first + 1);
        int third = inputLine.indexOf(',', second + 1);
        if (first > 0 && second > first && third > second) {
          int r = inputLine.substring(first + 1, second).toInt();
          int g = inputLine.substring(second + 1, third).toInt();
          int b = inputLine.substring(third + 1).toInt();
          r = constrain(r, 0, 255);
          g = constrain(g, 0, 255);
          b = constrain(b, 0, 255);
          applyRGB((uint8_t)r, (uint8_t)g, (uint8_t)b);
        }
      }
      inputLine = "";
    } else {
      inputLine += c;
      // Evitar desbordamiento
      if (inputLine.length() > 64) inputLine = "";
    }
  }
}