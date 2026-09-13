# IMU Sensor Due Diligence — WitMotion WT901BLECL

**Question:** Before spending money, can we be sure this sensor *works* and that we can
*extract and integrate* its raw data into Alion — with no repeat of the Hykso ("couldn't
order") or Polar H10 ("worked on paper, fought us on BLE") surprises?

**Verdict: GO.** ✅ This is the most de-risked hardware decision we've made. Four independent
implementations (one of them WitMotion's *official* SDK) agree byte-for-byte on the protocol,
all use the same BLE library we already have working on this Mac, and the one genuine risk
(sustained data rate over BLE) is platform-dependent and lands on the *good* side for macOS —
with a concrete mitigation regardless.

---

## What you're buying

| | |
|---|---|
| **Model** | WitMotion **WT901BLECL** (Bluetooth 5.0, 9-axis) |
| **ASIN** | `B07T2C97WN` (also sold as `B0B1WQFPN8`) — matches the Amazon.sa link you sent |
| **Sensor** | MPU9250: 3-axis accel **±16 g**, 3-axis gyro **±2000 °/s**, 3-axis magnetometer |
| **On-board** | Kalman/AHRS fusion → also outputs Euler angles (roll/pitch/yaw) |
| **Battery** | ~10 h, USB-C rechargeable |
| **Range** | 50 m (BLE 5.0) |
| **Output rate** | 0.1–200 Hz configurable, **factory default 10 Hz** |

---

## Pillar 1 — It exists and is purchasable (the Hykso test)

Unlike Hykso (website but no way to order), the WT901BLECL is a mainstream, in-stock product
sold on Amazon.com, Amazon.sa, RobotShop, and WitMotion's own store. The ASIN you found
(`B07T2C97WN`) is globally unique and resolves to this exact model. **No availability risk.**

> ⚠️ Buy from the **WitMotion official store or an Amazon-fulfilled listing** to guarantee a
> genuine unit, current firmware, and the USB-C cable. Avoid unknown third-party resellers.

## Pillar 2 — The raw data can actually be extracted (proven 4×)

The extraction path is confirmed by **four independent implementations that agree exactly**:

1. **WitMotion's OFFICIAL Python SDK** — `WITMOTION/WitBluetooth_BWT901BLE5_0`
   (`Python/BWT901BLE5.0_python_sdk/`), maintained (updated Sep 2024). **Uses `bleak`.**
2. **Community MIT repo** — `LiDline/witmotion_WT901BLECL_py` (2023, exact model). Uses `bleak`,
   and even sets output rate + calibration over the write characteristic.
3. **Protocol reference** — `DanielIzquierdo/WT901BLECL` (bluepy). Confirms the packet math.
4. **Developer walkthrough** — fastriver's blog: reading data *and* changing settings on this
   exact model over BLE.

All four agree on the GATT layout and the packet format:

| Purpose | UUID |
|---|---|
| Service | `0000ffe5-0000-1000-8000-00805f9a34fb` |
| Notify / read (data stream) | `0000ffe4-0000-1000-8000-00805f9a34fb` |
| Write / command (config, rate, calibrate) | `0000ffe9-0000-1000-8000-00805f9a34fb` |

**Streaming packet** (`0x55` header, `0x61` flag, 20 bytes = nine `int16` little-endian):

```
accel  = raw / 32768 * 16 * 9.8   # m/s²   (ax, ay, az)
gyro   = raw / 32768 * 2000        # °/s    (wx, wy, wz)
angle  = raw / 32768 * 180         # °      (roll, pitch, yaw)
```

Accel + angular velocity + angle stream **by default with no setup** — exactly the fields punch
detection needs. (Quaternion, magnetometer, and battery are *not* in the default stream; they
require a register-read command — not needed for our RQ.)

## Pillar 3 — It works on YOUR Mac (the Polar H10 lesson)

`bleak` is a wrapper over each OS's native BLE stack — **CoreBluetooth on macOS**. We already
have a **working `bleak` adapter on this exact machine**: `packages/capture/hrv/polar.py`
streams the Polar H10 live. The WT901 adapter is the *same pattern* with different UUIDs and a
different packet parse. **No new platform risk** — the BLE stack is already proven here.

## Pillar 4 — It maps cleanly into Alion's architecture

The IMU vertical mirrors the HRV vertical we already built:

| HRV (built & working) | IMU (to build) |
|---|---|
| `HRSample` raw event | **add `IMUSample`** raw event (additive, stays on v1 per ADR-005) |
| `PolarH10Source` (`bleak`, bg thread + queue) | `WT901Source` — same skeleton, UUIDs `ffe4`/`ffe9` |
| `hrv_runner` → `HRVStream` | `imu_runner` → **`IMUStream`** (contract already exists: `schema.py:49`) |

The `IMUStream` summary contract (`punches_detected`, `max/mean_velocity_ms`, `punch_types`,
`confidence`) is **already defined**. Integration is bounded and follows a template we've
shipped once already.

---

## Honest risks & mitigations

| Risk | Reality | Mitigation |
|---|---|---|
| **Sustained rate over BLE** — "200 Hz" is the sensor's *internal* rate; BLE throughput depends on the OS stack. | The bad case is **Windows/WinRT** (bleak issue #642: one user got <25 Hz). **macOS/CoreBluetooth is the good case** and our Polar stream already proves reliable BLE here. | Configure return rate to a **known-good 50–100 Hz** via the write char; **timestamp every packet and measure the real rate in session #1** — never assume it. 50 Hz = 5–8 samples across a 100–150 ms punch, which is scientifically adequate for counting, typing, and peak velocity. |
| **±16 g accel clipping** on hard impacts. | Alion measures **wrist kinematics** (velocity, counts, type) — not knuckle impact-g. | Fine for the RQ. Impact-g would be a different sensor class (that's what the mouthguard modality is for). |
| **Community-library reliance** (not plug-and-play). | Mitigated by the official SDK + 2 community repos + a protocol we can parse in ~30 lines. | We port the parse into our own `capture/imu` adapter (no runtime dependency on a random repo), same as we did for Polar. |
| **BLE pairing quirks** (the Polar annoyance). | Expect a one-time OS pairing. | Scan by name filter `"WT"`, connect by address — identical to `polar.py`. Known-good flow. |

## Bottom line

Order it. The data is open, the protocol is confirmed four ways, the library is the one we
already run on this Mac, and the integration is a known template. The only thing to *verify on
arrival* (not assume) is the effective BLE sample rate — and we'll measure that in the first
session and pin the return-rate setting accordingly.

---

### Sources
- WitMotion official Python BLE SDK — https://github.com/WITMOTION/WitBluetooth_BWT901BLE5_0
- Community (MIT, exact model) — https://github.com/LiDline/witmotion_WT901BLECL_py
- Protocol reference (bluepy) — https://github.com/DanielIzquierdo/WT901BLECL
- Developer walkthrough (read data / change settings) — https://zenn.dev/fastriver/articles/wt901blecl_read_data
- WT901BLECL manual (v23-0420) — https://cdn.robotshop.com/rbm/f83835f4-5e29-4ee0-9cc2-e49300031503/b/bf5c1f59-3b36-40a4-a5f0-e5a0eea52565/15a3f141_wt901blecl-manual.pdf
- Amazon product (ASIN B07T2C97WN) — https://www.amazon.com/WT901BLECL-Accelerometer-Acceleration-Low-Consumption-Compatible/dp/B07T2C97WN
- bleak cross-platform BLE (rate caveat, issue #642) — https://github.com/hbldh/bleak/issues/642
