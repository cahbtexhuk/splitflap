#include <cassert>
#include <cstdint>
#include <iostream>

#include "native/Arduino.h"

#define private public
#include "../src/splitflap_module.h"
#undef private

FakeSerial Serial;
unsigned long fake_micros = 0;

unsigned long micros() {
    return fake_micros;
}

struct Fixture {
    uint8_t motor = 0;
    uint8_t sensor = 0;
    SplitflapModule module;

    Fixture() : module(motor, 0, sensor, 1) {
        fake_micros = 0;
        module.state = NORMAL;
    }

    void step() {
        fake_micros += module.current_period;
        module.Update();
    }
};

void test_display_periods() {
    Fixture fixture;
    fixture.module.GoToFlapIndex(10);
    assert(fixture.module.display_move);
    assert(fixture.module.current_period == Acceleration::ACCEL_STEP_PERIODS[0]);

    for (uint8_t index = 1; index <= Acceleration::MAX_ACCEL_STEP; index++) {
        fixture.module.state = NORMAL;
        fixture.module.home_state = IGNORE;
        fixture.module.current_step = 0;
        fixture.module.delta_steps = STEPS_PER_REVOLUTION;
        fixture.module.current_accel_step = index - 1;
        fixture.step();
        uint32_t expected = uint32_t(Acceleration::ACCEL_STEP_PERIODS[index]) * 2;
        assert(expected <= UINT16_MAX);
        assert(fixture.module.current_accel_step == index);
        assert(fixture.module.current_period == expected);
    }
}

void test_homing_periods() {
    Fixture fixture;
    fixture.module.GoToFlapIndex(10);
    fixture.module.FindAndRecalibrateHome();
    assert(!fixture.module.display_move);
    for (uint8_t index = 1; index < Acceleration::MAX_ACCEL_STEP; index++) {
        fixture.module.state = LOOK_FOR_HOME;
        fixture.module.delta_steps = MAX_STEPS_LOOKING_FOR_HOME;
        fixture.module.current_accel_step = index < 9 ? index - 1 : (index == 9 ? 9 : index + 1);
        fixture.step();
        assert(fixture.module.current_accel_step == index);
        assert(fixture.module.current_period == Acceleration::ACCEL_STEP_PERIODS[index]);
    }
}

void test_display_requested_during_homing() {
    Fixture fixture;
    fixture.module.FindAndRecalibrateHome();
    fixture.module.GoToFlapIndex(7);
    fixture.step();
    assert(fixture.module.state == LOOK_FOR_HOME);
    assert(fixture.module.display_move);
    assert(fixture.module.current_period == Acceleration::ACCEL_STEP_PERIODS[1]);

    fixture.step();
    fixture.sensor = 1;
    fixture.step();
    assert(fixture.module.state == NORMAL);
    assert(fixture.module.GetTargetFlapIndex() == 7);
    assert(fixture.module.current_accel_step > 0);
    assert(fixture.module.current_period == uint32_t(Acceleration::ACCEL_STEP_PERIODS[fixture.module.current_accel_step]) * 2);
}

void test_display_resumes_after_automatic_rehome() {
    Fixture fixture;
    fixture.module.GoToFlapIndex(7);
    fixture.module.home_state = UNEXPECTED;
    fixture.sensor = 1;
    fixture.step();
    assert(fixture.module.state == LOOK_FOR_HOME);
    assert(fixture.module.display_move);
    assert(fixture.module.count_unexpected_home == 1);

    fixture.sensor = 0;
    fixture.step();
    assert(fixture.module.current_period == Acceleration::ACCEL_STEP_PERIODS[fixture.module.current_accel_step]);
    fixture.step();
    fixture.sensor = 1;
    fixture.step();
    assert(fixture.module.state == NORMAL);
    assert(fixture.module.display_move);
    assert(fixture.module.GetTargetFlapIndex() == 7);
    assert(fixture.module.current_accel_step > 0);
    assert(fixture.module.current_period == uint32_t(Acceleration::ACCEL_STEP_PERIODS[fixture.module.current_accel_step]) * 2);
}

void test_calibration_and_reset_clear_display_mode() {
    Fixture fixture;
    fixture.module.GoToFlapIndex(5);
    fixture.step();
    assert(fixture.module.current_accel_step == 1);
    assert(fixture.module.current_period == uint32_t(Acceleration::ACCEL_STEP_PERIODS[1]) * 2);
    fixture.module.IncreaseOffset(5);
    assert(!fixture.module.display_move);
    fixture.step();
    assert(fixture.module.current_period == Acceleration::ACCEL_STEP_PERIODS[fixture.module.current_accel_step]);

    fixture.module.GoToFlapIndex(5);
    fixture.module.SetOffset();
    assert(!fixture.module.display_move);
    fixture.step();
    assert(fixture.module.current_period == Acceleration::ACCEL_STEP_PERIODS[fixture.module.current_accel_step]);

    fixture.module.GoToFlapIndex(5);
    fixture.module.ResetState();
    assert(!fixture.module.display_move);

    fixture.module.GoToFlapIndex(5);
    fixture.module.RestoreOffset((fixture.module.offset_steps + 1) % STEPS_PER_REVOLUTION);
    assert(fixture.module.state == LOOK_FOR_HOME);
    assert(!fixture.module.display_move);
}

unsigned long movement_time(uint16_t start_step, uint8_t target, bool display) {
    Fixture fixture;
    fixture.module.current_step = start_step;
    fixture.module.GoToFlapIndex(target);
    fixture.module.display_move = display;
    unsigned long initial_time = fake_micros;
    unsigned int updates = 0;
    do {
        fixture.step();
        updates++;
        assert(fixture.module.state == NORMAL);
        assert(updates < STEPS_PER_REVOLUTION * 3);
    } while (fixture.module.delta_steps || fixture.module.current_accel_step);
    assert(fixture.module.current_step == fixture.module.GetTargetStepForFlapIndex(target));
    return fake_micros - initial_time;
}

void test_movement_duration(uint16_t start_step, uint8_t target) {
    unsigned long original = movement_time(start_step, target, false);
    unsigned long slower = movement_time(start_step, target, true);
    assert(slower == 2 * original - Acceleration::ACCEL_STEP_PERIODS[0]);
}

int main() {
    test_display_periods();
    test_homing_periods();
    test_display_requested_during_homing();
    test_display_resumes_after_automatic_rehome();
    test_calibration_and_reset_clear_display_mode();
    test_movement_duration(0, 1);
    test_movement_duration(0, 12);
    test_movement_duration(STEPS_PER_REVOLUTION - 20, 1);
    std::cout << "Splitflap motion tests passed\n";
}