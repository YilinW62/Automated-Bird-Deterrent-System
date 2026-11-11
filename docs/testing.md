# Testing and validation

## Bench tests

1. Start in vision-only mode: `python3 Bird_Deterrent.py --dry-run`.
2. Verify USB camera preview, bird-class bounding boxes, detection snapshots, and CSV event logs.
3. With power and driver wiring professionally checked, test servo and buzzer independently before running the integrated system.
4. In hardware mode, check scanning nominally every 2 seconds, nominal 15-degree positioning steps (subject to servo calibration), and 10-second buzzer activation after a confirmed detection.
5. Check stopping and restart behavior after a bird is no longer detected.

## Metrics to collect

- Detection TP, FP, FN, TN on a labeled evaluation set
- Precision = TP / (TP + FP); recall = TP / (TP + FN)
- Detection-to-alarm latency (ms), alarm duration (s)
- Measured servo angles, step intervals, missed steps
- Tested illumination, camera distance, system uptime and supply voltage under load

Do not publish performance statistics until they have been measured. Images of birds shown on another screen are useful demo stimuli but do not establish real-world outdoor detection accuracy.
