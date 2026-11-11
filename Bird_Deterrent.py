#!/usr/bin/env python3
"""SLDP Team 100 — Automatic Bird Deterrent (Raspberry Pi 4).

Features: MobileNet SSD / OpenCV bird detection, servo scan, 10-second
buzzer activation, post-alarm recheck, CSV logs and event snapshots.

Run with --dry-run before connecting actuators. See README.md.
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path
import time

import cv2
import numpy as np

BASE = Path(__file__).resolve().parent
MODEL_DIR = BASE / 'models'
# Classic 21-class Caffe MobileNet SSD; class index 3 = bird.
CLASSES = (
    'background', 'aeroplane', 'bicycle', 'bird', 'boat', 'bottle',
    'bus', 'car', 'cat', 'chair', 'cow', 'diningtable', 'dog', 'horse',
    'motorbike', 'person', 'pottedplant', 'sheep', 'sofa', 'train', 'tvmonitor'
)


class BirdDetector:
    def __init__(self, threshold=0.50):
        proto = MODEL_DIR / 'MobileNetSSD_deploy.prototxt'
        weights = MODEL_DIR / 'MobileNetSSD_deploy.caffemodel'
        if not proto.is_file() or not weights.is_file():
            raise FileNotFoundError(
                f'Missing {proto.name} or {weights.name}. Run bash download_model.sh first.'
            )
        self.network = cv2.dnn.readNetFromCaffe(str(proto), str(weights))
        self.threshold = threshold

    def detect(self, frame):
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5
        )
        self.network.setInput(blob)
        detections = self.network.forward()
        birds = []
        for item in detections[0, 0]:
            confidence = float(item[2])
            label_id = int(item[1])
            if label_id != 3 or confidence < self.threshold:
                continue
            coords = item[3:7] * np.array([w, h, w, h])
            x1, y1, x2, y2 = [int(v) for v in coords]
            x1, x2 = max(0, min(w - 1, x1)), max(0, min(w - 1, x2))
            y1, y2 = max(0, min(h - 1, y1)), max(0, min(h - 1, y2))
            if x2 > x1 and y2 > y1:
                birds.append((confidence, (x1, y1, x2, y2)))
        return birds


class Actuators:
    def __init__(self, args):
        self.args = args
        self.servo = None
        self.buzzer = None
        self.angle = args.min_angle
        self.direction = 1
        self.steps = 0
        if args.dry_run:
            print('[DRY RUN] GPIO disabled; servo and buzzer are simulated.')
            return
        try:
            from gpiozero import AngularServo, Servo, PWMOutputDevice, DigitalOutputDevice
            if args.servo_mode == 'positional':
                self.servo = AngularServo(
                    args.servo_pin, min_angle=args.min_angle,
                    max_angle=args.max_angle,
                    min_pulse_width=args.servo_min_pulse_ms / 1000,
                    max_pulse_width=args.servo_max_pulse_ms / 1000
                )
                self.servo.angle = self.angle
            else:
                self.servo = Servo(
                    args.servo_pin,
                    min_pulse_width=args.servo_min_pulse_ms / 1000,
                    max_pulse_width=args.servo_max_pulse_ms / 1000
                )
                self.servo.value = 0
            if args.buzzer_type == 'passive':
                self.buzzer = PWMOutputDevice(args.buzzer_pin, frequency=args.tone_hz, initial_value=0)
            else:
                self.buzzer = DigitalOutputDevice(args.buzzer_pin, initial_value=False)
        except Exception:
            self.close()
            raise

    def step(self):
        if self.args.servo_mode == 'positional':
            next_angle = self.angle + self.direction * self.args.step_degrees
            if next_angle > self.args.max_angle or next_angle < self.args.min_angle:
                self.direction *= -1
                next_angle = self.angle + self.direction * self.args.step_degrees
            self.angle = max(self.args.min_angle, min(self.args.max_angle, next_angle))
            if self.servo is not None:
                self.servo.angle = self.angle
            time.sleep(self.args.servo_settle_seconds)
            return f'{self.angle:.1f} deg (positional sweep)'
        # Continuous servos control speed, NOT angle. This is a timed approximation.
        if self.servo is not None:
            self.servo.value = self.args.continuous_speed
        time.sleep(self.args.continuous_seconds_per_15 * self.args.step_degrees / 15.0)
        if self.servo is not None:
            self.servo.value = 0
        self.steps += 1
        return f'approx {self.steps * self.args.step_degrees % 360:.0f} deg (uncalibrated estimate)'

    def buzz(self, seconds, tick=None):
        print(f'[ALERT] Buzzer ON for {seconds:.1f} seconds')
        if self.buzzer is not None:
            self.buzzer.value = 0.5 if self.args.buzzer_type == 'passive' else 1
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                if tick:
                    tick()
                time.sleep(min(0.08, max(0, end - time.monotonic())))
        finally:
            if self.buzzer is not None:
                self.buzzer.off()
        print('[ALERT] Buzzer OFF')

    def close(self):
        if self.buzzer is not None:
            try:
                self.buzzer.off()
            finally:
                self.buzzer.close()
            self.buzzer = None
        if self.servo is not None:
            try:
                if self.args.servo_mode == 'continuous':
                    self.servo.value = 0
                else:
                    self.servo.value = None  # stop sending PWM, not a home command
            finally:
                self.servo.close()
            self.servo = None


def cli():
    p = argparse.ArgumentParser(description='Camera + MobileNetSSD + Servo + Buzzer')
    p.add_argument('--source', default='0', help='Camera index (0) or video file path')
    p.add_argument('--dry-run', action='store_true', help='Run vision without accessing GPIO')
    p.add_argument('--headless', action='store_true', help='No preview window')
    p.add_argument('--confidence', type=float, default=0.50)
    p.add_argument('--confirm-frames', type=int, default=2,
                   help='Consecutive positive inference frames before alarm')
    p.add_argument('--step-degrees', type=float, default=15)
    p.add_argument('--scan-interval', type=float, default=2.0)
    p.add_argument('--alarm-seconds', type=float, default=10.0)
    p.add_argument('--recheck-seconds', type=float, default=0.8,
                   help='Collect a brief recheck observation after buzzer stops')
    p.add_argument('--servo-mode', choices=['positional', 'continuous'], default='positional')
    p.add_argument('--min-angle', type=float, default=-90)
    p.add_argument('--max-angle', type=float, default=90)
    p.add_argument('--servo-pin', type=int, default=17, help='BCM numbering')
    p.add_argument('--buzzer-pin', type=int, default=27, help='BCM numbering')
    p.add_argument('--buzzer-type', choices=['passive', 'active'], default='passive')
    p.add_argument('--tone-hz', type=int, default=2000)
    p.add_argument('--servo-min-pulse-ms', type=float, default=1.0)
    p.add_argument('--servo-max-pulse-ms', type=float, default=2.0)
    p.add_argument('--servo-settle-seconds', type=float, default=0.25)
    p.add_argument('--continuous-speed', type=float, default=0.6)
    p.add_argument('--continuous-seconds-per-15', type=float, default=0.20,
                   help='MUST calibrate against markings; time is not precise angle')
    p.add_argument('--width', type=int, default=640)
    p.add_argument('--height', type=int, default=480)
    p.add_argument('--output', type=Path, default=BASE / 'results')
    a = p.parse_args()
    if not 0 < a.confidence <= 1 or a.confirm_frames < 1:
        p.error('Confidence must be (0,1], confirm-frames >= 1')
    if a.step_degrees <= 0 or a.scan_interval <= 0 or a.alarm_seconds <= 0:
        p.error('step-degrees, scan-interval and alarm-seconds must be positive')
    if a.recheck_seconds <= 0 or a.servo_settle_seconds < 0:
        p.error('recheck-seconds must be positive, servo-settle-seconds >= 0')
    if a.min_angle >= a.max_angle or a.step_degrees > a.max_angle - a.min_angle:
        p.error('Invalid positional servo range/step')
    if not -1 <= a.continuous_speed <= 1 or a.continuous_speed == 0:
        p.error('continuous-speed must be nonzero and within [-1,1]')
    if a.continuous_seconds_per_15 <= 0:
        p.error('continuous-seconds-per-15 must be positive')
    if a.servo_pin == a.buzzer_pin:
        p.error('Servo and buzzer GPIO pins must differ')
    return a


def main():
    a = cli()
    a.output.mkdir(parents=True, exist_ok=True)
    detector = BirdDetector(a.confidence)
    source = int(a.source) if a.source.isdigit() else a.source
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f'Unable to open camera/video source: {a.source}')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, a.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, a.height)
    log_path = a.output / 'events.csv'
    first_log = not log_path.exists() or log_path.stat().st_size == 0
    device = None
    try:
        device = Actuators(a)
        with log_path.open('a', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            if first_log:
                writer.writerow(['timestamp', 'event', 'confidence', 'servo_position', 'notes'])
                fh.flush()

            def log(event, confidence='', position='', notes=''):
                stamp = datetime.now().isoformat(timespec='milliseconds')
                writer.writerow([stamp, event, confidence, position, notes])
                fh.flush()
                print(f'[{stamp}] {event} {notes}')

            def frame_and_detect(display=True):
                ok, frame = cap.read()
                if not ok:
                    return None, []
                birds = detector.detect(frame)
                if display and not a.headless:
                    for confidence, (x1, y1, x2, y2) in birds:
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, f'BIRD {confidence:.0%}',
                                    (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.6, (0, 255, 0), 2)
                    cv2.imshow('SLDP Bird Deterrent - press q to quit', frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        raise KeyboardInterrupt
                return frame, birds

            log('START', notes=f'mode={a.servo_mode}; dry_run={a.dry_run}')
            # Start scanning immediately. Subsequent steps occur roughly every 2 seconds.
            next_step = time.monotonic()
            positives = 0
            while True:
                now = time.monotonic()
                if now >= next_step:
                    position = device.step()
                    log('SERVO_STEP', position=position)
                    next_step = time.monotonic() + a.scan_interval

                frame, birds = frame_and_detect()
                if frame is None:
                    log('SOURCE_ENDED', notes='Camera failure or end of video')
                    break
                positives = positives + 1 if birds else 0
                if positives < a.confirm_frames:
                    continue

                strongest = max(conf for conf, _ in birds)
                stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                image_path = a.output / f'bird_{stamp}.jpg'
                cv2.imwrite(str(image_path), frame)
                log('BIRD_DETECTED', confidence=f'{strongest:.3f}',
                    notes=f'snapshot={image_path.name}')
                # Servo has already stopped after each scan step.
                device.buzz(a.alarm_seconds)
                log('BUZZER_OFF', notes=f'alarm_seconds={a.alarm_seconds}')

                recheck_end = time.monotonic() + a.recheck_seconds
                found_again = False
                valid_recheck = False
                while time.monotonic() < recheck_end:
                    reframe, rebirds = frame_and_detect()
                    if reframe is None:
                        log('SOURCE_ENDED', notes='Source ended during recheck')
                        return
                    valid_recheck = True
                    found_again = found_again or bool(rebirds)
                log('RECHECK', notes='bird_present' if found_again else 'no_bird_detected')
                positives = 0
                if found_again:
                    # Re-trigger on next confirmed sighting; no motion while alarm sounds.
                    log('BIRD_STILL_PRESENT', notes='Next confirmation will reactivate alarm')
                    next_step = float('inf')
                else:
                    next_step = time.monotonic() + a.scan_interval
                # When a bird persists, do not rotate; keep watching to confirm again.
                if found_again:
                    while True:
                        follow_frame, follow_birds = frame_and_detect()
                        if follow_frame is None:
                            log('SOURCE_ENDED', notes='Source ended after recheck')
                            return
                        positives = positives + 1 if follow_birds else 0
                        if positives >= a.confirm_frames:
                            # Return to regular loop, triggering next alarm promptly.
                            break
                        if not follow_birds:
                            log('SCAN_RESUMED', notes='Bird disappeared during follow-up')
                            next_step = time.monotonic() + a.scan_interval
                            break
                    if positives >= a.confirm_frames:
                        # Next iteration should re-detect and sound alarm.
                        positives = a.confirm_frames - 1
    except KeyboardInterrupt:
        print('\nStopped by user.')
    finally:
        if device is not None:
            device.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()