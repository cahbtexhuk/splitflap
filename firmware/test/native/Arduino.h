#pragma once

#include <stdint.h>

#define PROGMEM
#define pgm_read_word_near(address) (*(address))
#define B00000001 1
#define B00000010 2
#define B00000100 4
#define B00001000 8

using String = const char*;

struct FakeSerial {
    void print(const char*) {}
};

extern FakeSerial Serial;
unsigned long micros();