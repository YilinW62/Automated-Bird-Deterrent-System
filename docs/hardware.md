# Hardware and wiring notes

The prototype uses a Raspberry Pi 5, USB webcam, servo, two-wire 3–24V DC buzzer, breadboard, and VEX 7.2V NiMH battery. GPIO assignments in `Bird_Deterrent.py` use BCM numbering: GPIO17 (physical pin 11) for the servo signal, and GPIO27 (physical pin 13) for the buzzer's external driver control.

**Power safety:** Never connect raw 7.2V from the VEX pack to Raspberry Pi GPIO, the 3.3V rail, or the 5V rail. A Raspberry Pi 5 ordinarily uses a suitably rated USB-C 5.1V/5A supply. An LM2596 HW-411 module is *not* an independently verified 5A Pi 5 supply. A servo needs regulated power appropriate to its documented rating, adequate peak-current capacity, and a common ground shared with the Pi.

The observed two-wire DC buzzer is controlled through a TIP120 NPN Darlington transistor, **not a MOSFET**. The control branch needs a correctly sized base resistor; inductive loads need appropriate flyback protection. Verify pinout from the TIP120 datasheet and ensure the switching device and power source can handle actual buzzer current.

A positional servo scans its limited angular range and reverses direction; do not claim continuous precise 360-degree rotation without extra position feedback and cable-management hardware.

**Status:** Software integration was demonstrated in bench testing. Exact servo calibration, electrical ratings, outdoor weather protection, and long-duration battery operation require further verification.
