"""
Demonstration of the Clap-Sync Fusion Engine.

Simulates a mismatched timeline between a CV (webcam) stream and an IMU (wrist) stream.
Visualizes how the Fusion Aligner uses the physical clap to mathematically sync them.
"""

import sys
from pathlib import Path

# Add packages to path so we can import from fusion
sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))

from fusion.aligner import TimeAligner


def print_timeline(name: str, stream: list[dict], spike_t: float):
    print(f"\n=== {name} ===")
    print("Time (ms) | Signal (G-force / Activity)")
    print("-" * 55)
    for sample in stream:
        t = sample["t_ms"]
        val = sample["val"]

        # Determine bar length
        bar_len = int(val * 10)
        bar = "█" * bar_len

        # Highlight the spike
        if t == spike_t:
            print(f"{t:9.0f} | \033[91m{bar} <-- CLAP SPIKE\033[0m")
        else:
            print(f"{t:9.0f} | \033[90m{bar}\033[0m")


def main():
    print("🥊 ALION: SYNTHETIC IMU FUSION DEMO 🥊\n")

    # 1. Simulate the CV Stream
    # The camera started exactly at T=0.
    # The fighter stood there, then clapped their gloves together at exactly 1500ms.
    cv_clap_t_ms = 1500.0

    # 2. Simulate the IMU Stream
    # The IMU sensor was turned on LATE. Its internal clock thinks the clap
    # happened at 2300ms.
    imu_spike_t_ms = 2300.0

    # Generate fake IMU time-series
    raw_imu_stream = []
    for t in range(0, 4000, 100):
        val = 0.2  # Background noise
        if t == imu_spike_t_ms:
            val = 4.0  # Massive G-force spike from gloves hitting
        elif abs(t - imu_spike_t_ms) <= 100:
            val = 1.5  # Aftershock

        raw_imu_stream.append({"t_ms": float(t), "val": val})

    print("1. BEFORE ALIGNMENT: Unsynchronized Clocks")
    print(f"   - CV Camera saw the clap at:  {cv_clap_t_ms} ms")
    print(f"   - IMU Sensor felt the clap at: {imu_spike_t_ms} ms")
    print("   (Notice the physical IMU data is shifted way down the timeline)")

    print_timeline("UNALIGNED IMU STREAM", raw_imu_stream, imu_spike_t_ms)

    print("\n2. RUNNING FUSION ALIGNER...")
    aligner = TimeAligner()
    offset_ms = aligner.compute_offset(cv_clap_t_ms=cv_clap_t_ms, imu_spike_t_ms=imu_spike_t_ms)
    print(f"   >> Computed Offset: {offset_ms} ms")

    print("\n3. AFTER ALIGNMENT: Fused Streams")

    # Apply offset to the raw IMU stream
    aligned_imu_stream = []
    for sample in raw_imu_stream:
        aligned_imu_stream.append({"t_ms": sample["t_ms"] + offset_ms, "val": sample["val"]})

    aligned_spike_t = imu_spike_t_ms + offset_ms
    print(f"   - CV Camera saw the clap at:  {cv_clap_t_ms} ms")
    print(f"   - IMU Sensor shifted to:      {aligned_spike_t} ms")
    print("   (The physical shockwave now PERFECTLY aligns with the visual video frame)")

    # Filter the aligned stream to keep the timeline bounds similar for display
    display_stream = [s for s in aligned_imu_stream if 0 <= s["t_ms"] < 3200]

    print_timeline("ALIGNED IMU STREAM", display_stream, aligned_spike_t)


if __name__ == "__main__":
    main()
