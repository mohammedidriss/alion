"""
Experimental ML Pipeline: Data Collection.

Run this script to generate your own custom dataset of punches.
It uses the existing Heuristic detector to find exactly when you punch,
and saves the 3D coordinates of your upper body at that precise moment into a CSV.
"""

import csv
import sys
import time
from pathlib import Path

import cv2

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages"))

from analyze.punch_detector_heuristic import HeuristicPunchDetector
from capture.cv.overlay import draw_pose
from capture.cv.pose import PoseEstimator


def main():
    print("🥊 ALION ML DATA COLLECTION 🥊\n")
    print("Stand in front of the camera.")

    classes = ["jab", "cross", "hook", "uppercut"]
    target_count = 10  # 10 of each punch type for a quick test

    out_dir = Path("data/ml")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "punches_dataset.csv"

    # We will save the x,y,z of left_shoulder, right_shoulder, left_wrist, right_wrist
    # at the exact moment of the punch peak.
    headers = [
        "label",
        "hand",
        "velocity",
        "ls_x",
        "ls_y",
        "ls_z",
        "rs_x",
        "rs_y",
        "rs_z",
        "lw_x",
        "lw_y",
        "lw_z",
        "rw_x",
        "rw_y",
        "rw_z",
    ]

    dataset = []

    import uuid

    session_id = uuid.uuid4()

    cap = cv2.VideoCapture(0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    estimator = PoseEstimator(session_id, fps)
    detector = HeuristicPunchDetector()

    # We open the estimator
    with estimator.open() as est:
        for current_class in classes:
            print(f"\n--- GET READY TO THROW {target_count} {current_class.upper()}S ---")
            time.sleep(3)

            count = 0
            while count < target_count:
                ret, frame = cap.read()
                if not ret:
                    break

                # Mirror frame for easier user interaction
                frame = cv2.flip(frame, 1)

                pose = est.process(frame)

                if pose:
                    events = detector.feed(pose)
                    for ev in events:
                        # Grab the world landmarks at the moment of impact
                        if pose.world_landmarks:
                            ls = pose.world_landmarks[11]
                            rs = pose.world_landmarks[12]
                            lw = pose.world_landmarks[15]
                            rw = pose.world_landmarks[16]

                            row = [
                                current_class,
                                ev.hand,
                                ev.velocity_ms,
                                ls.x,
                                ls.y,
                                ls.z,
                                rs.x,
                                rs.y,
                                rs.z,
                                lw.x,
                                lw.y,
                                lw.z,
                                rw.x,
                                rw.y,
                                rw.z,
                            ]
                            dataset.append(row)
                            count += 1
                            print(
                                f"✅ Recorded {current_class} ({count}/{target_count}) - {ev.velocity_ms:.1f} m/s"
                            )

                    draw_pose(frame, pose)

                # Display instructions on screen
                cv2.putText(
                    frame,
                    f"Throw: {current_class.upper()} ({count}/{target_count})",
                    (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 255),
                    2,
                )

                cv2.imshow("Data Collection", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("Aborting.")
                    cap.release()
                    cv2.destroyAllWindows()
                    return

    cap.release()
    cv2.destroyAllWindows()

    # Save to CSV
    print(f"\nSaving dataset to {csv_path}...")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(dataset)

    print("Dataset complete! You can now run train_model.py")


if __name__ == "__main__":
    main()
