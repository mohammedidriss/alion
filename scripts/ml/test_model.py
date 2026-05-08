"""
Experimental ML Pipeline: Live Testing.

Loads the trained Random Forest model and runs it live on your webcam feed.
Throws punches and see what the model classifies them as!
"""

import sys
import time
from pathlib import Path

import cv2
import joblib
import pandas as pd

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages"))

from capture.cv.pose import PoseEstimator
from analyze.punch_detector_heuristic import HeuristicPunchDetector
from capture.cv.overlay import draw_pose

def main():
    print("🥊 ALION ML LIVE TEST 🥊\n")
    
    model_path = Path("data/ml/punch_classifier_v1.pkl")
    if not model_path.exists():
        print(f"Error: Model not found at {model_path}.")
        print("Please run scripts/ml/train_model.py first!")
        sys.exit(1)
        
    print("Loading model...")
    model = joblib.load(model_path)
    
    import uuid
    session_id = uuid.uuid4()
    
    cap = cv2.VideoCapture(0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    
    estimator = PoseEstimator(session_id, fps)
    detector = HeuristicPunchDetector()
    
    last_punch_time = 0
    last_classification = "None"
    last_velocity = 0.0
    
    print("Camera active. Throw some punches!")
    
    with estimator.open() as est:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            frame = cv2.flip(frame, 1)
            pose = est.process(frame)
            
            if pose:
                events = detector.feed(pose)
                for ev in events:
                    if pose.world_landmarks:
                        ls = pose.world_landmarks[11]
                        rs = pose.world_landmarks[12]
                        lw = pose.world_landmarks[15]
                        rw = pose.world_landmarks[16]
                        
                        # Prepare the feature array exactly how it was trained
                        is_left_hand = 1 if ev.hand == 'left' else 0
                        
                        features = pd.DataFrame([{
                            "velocity": ev.velocity_ms,
                            "is_left_hand": is_left_hand,
                            "ls_x": ls.x, "ls_y": ls.y, "ls_z": ls.z,
                            "rs_x": rs.x, "rs_y": rs.y, "rs_z": rs.z,
                            "lw_x": lw.x, "lw_y": lw.y, "lw_z": lw.z,
                            "rw_x": rw.x, "rw_y": rw.y, "rw_z": rw.z
                        }])
                        
                        # Predict using the loaded model
                        prediction = model.predict(features)[0]
                        
                        last_classification = prediction.upper()
                        last_velocity = ev.velocity_ms
                        last_punch_time = time.time()
                        print(f"🥊 Detected: {last_classification} ({ev.hand}) at {last_velocity:.1f} m/s")
                        
                draw_pose(frame, pose)
            
            # Show the last detected punch on the screen for 2 seconds
            if time.time() - last_punch_time < 2.0:
                cv2.putText(frame, f"{last_classification} ({last_velocity:.1f} m/s)", 
                            (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
            else:
                cv2.putText(frame, "Waiting for punch...", 
                            (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                        
            cv2.imshow("Live Model Testing", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()
    print("Testing session ended.")

if __name__ == "__main__":
    main()
