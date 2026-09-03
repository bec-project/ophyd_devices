#!/usr/bin/env python3

import argparse
import threading
import time

from caproto.server import PVGroup, SubGroup, pvproperty, run
from caproto.server.records import MotorFields
from caproto.sync.repeater import RepeaterAlreadyRunning, check_for_running_repeater
from caproto.sync.repeater import run as run_repeater


def ensure_repeater() -> None:
    try:
        sock = check_for_running_repeater(("0.0.0.0", 5065))
    except RepeaterAlreadyRunning:
        return
    else:
        sock.close()

    thread = threading.Thread(target=run_repeater, kwargs={"host": "0.0.0.0"}, daemon=True)
    thread.start()

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            sock = check_for_running_repeater(("0.0.0.0", 5065))
        except RepeaterAlreadyRunning:
            return
        else:
            sock.close()
            time.sleep(0.05)


async def broadcast_precision_to_fields(record: pvproperty) -> None:
    precision = record.precision
    for prop in record.field_inst.pvdb.values():
        if hasattr(prop, "precision"):
            await prop.write_metadata(precision=precision)


async def motor_record_simulator(
    instance: pvproperty,
    async_lib,
    *,
    velocity: float,
    precision: int,
    acceleration: float,
    resolution: float,
    user_limits: tuple[float, float],
    tick_rate_hz: float,
    final_offset_pv: pvproperty,
) -> None:
    fields: MotorFields = instance.field_inst
    have_new_position = False

    async def value_write_hook(_fields, value):
        nonlocal have_new_position
        have_new_position = True

    fields.value_write_hook = value_write_hook

    await instance.write_metadata(precision=precision)
    await broadcast_precision_to_fields(instance)
    await fields.velocity.write(velocity)
    await fields.seconds_to_velocity.write(acceleration)
    await fields.motor_step_size.write(resolution)
    await fields.user_low_limit.write(user_limits[0])
    await fields.user_high_limit.write(user_limits[1])
    await fields.done_moving_to_value.write(1)

    while True:
        dwell = 1.0 / tick_rate_hz
        if not have_new_position:
            await async_lib.library.sleep(dwell)
            continue

        target = instance.value
        readback = fields.user_readback_value.value
        delta = target - readback

        await fields.done_moving_to_value.write(0)
        await fields.motor_is_moving.write(1)

        total_time = abs(delta / fields.velocity.value) if fields.velocity.value else 0.0
        num_steps = int(total_time // dwell)
        step_size = delta / num_steps if num_steps > 0 else 0.0
        raw_resolution = max(fields.motor_step_size.value, 1e-10)

        for _ in range(num_steps):
            readback += step_size
            await fields.user_readback_value.write(readback)
            await fields.dial_readback_value.write(readback)
            await fields.raw_readback_value.write(readback / raw_resolution)
            await async_lib.library.sleep(dwell)

        final_value = target + final_offset_pv.value
        await fields.user_readback_value.write(final_value)
        await fields.dial_readback_value.write(final_value)
        await fields.raw_readback_value.write(final_value / raw_resolution)
        await fields.motor_is_moving.write(0)
        await fields.done_moving_to_value.write(1)
        have_new_position = False


class FakeMotor(PVGroup):
    final_offset = pvproperty(value=0.0, name="final_offset")
    motor = pvproperty(value=0.0, name="", record="motor", precision=3)

    def __init__(
        self,
        *args,
        velocity: float = 2.0,
        precision: int = 3,
        acceleration: float = 0.5,
        resolution: float = 1e-3,
        user_limits: tuple[float, float] = (-100.0, 100.0),
        tick_rate_hz: float = 20.0,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.velocity = velocity
        self.precision = precision
        self.acceleration = acceleration
        self.resolution = resolution
        self.user_limits = user_limits
        self.tick_rate_hz = tick_rate_hz

    @motor.startup
    async def motor(self, instance, async_lib):
        await motor_record_simulator(
            instance,
            async_lib,
            velocity=self.velocity,
            precision=self.precision,
            acceleration=self.acceleration,
            resolution=self.resolution,
            user_limits=self.user_limits,
            tick_rate_hz=self.tick_rate_hz,
            final_offset_pv=self.final_offset,
        )


class MotorIOC(PVGroup):
    mtr1 = SubGroup(FakeMotor, prefix="mtr1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="SIM:MOTOR:")
    parser.add_argument("--interface", default="127.0.0.1")
    args = parser.parse_args()

    ensure_repeater()
    ioc = MotorIOC(prefix=args.prefix)
    run(ioc.pvdb, interfaces=[args.interface])


if __name__ == "__main__":
    main()
