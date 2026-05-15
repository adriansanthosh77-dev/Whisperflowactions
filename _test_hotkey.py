"""Test Pause/Break key detection via pynput."""
import sys
sys.path.insert(0, ".")
from pynput.keyboard import Key

print("Key.pause:", repr(Key.pause))
print("Key.pause.value:", Key.pause.value)

# Simulate the hotkey check logic
pressed_keys = {Key.pause}

is_pause = Key.pause in pressed_keys
print(f"Key.pause in pressed_keys: {is_pause}")

# Also check the on_press logic directly
from pynput.keyboard import Listener
import threading, time

detected = []

def on_press(key):
    detected.append(("press", key))
    if key == Key.esc:
        return False

def on_release(key):
    detected.append(("release", key))

print("\nListening for key presses (5s timeout)...")
print("Press Pause/Break, then Escape to stop...")

listener = Listener(on_press=on_press, on_release=on_release)
listener.start()
time.sleep(5)
listener.stop()

if detected:
    for event, key in detected:
        print(f"  {event}: {repr(key)} (type={type(key).__name__})")
        if hasattr(key, 'value'):
            print(f"    value: {key.value}")
else:
    print("  No keys detected.")
