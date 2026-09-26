import pandas as pd
import numpy as np

def analyze():
    try:
        df = pd.read_csv('light_activity.csv', names=['time', 'r', 'g', 'b'])
    except Exception:
        print("No light_activity.csv found. Let the visualizer run for a bit first!")
        return

    if len(df) < 50:
        print("Not enough data collected yet. Let the music play a bit longer.")
        return

    # Calculate overall brightness
    df['brightness'] = df[['r', 'g', 'b']].mean(axis=1)
    
    # Calculate time deltas and derivatives (flux)
    df['dt'] = df['time'].diff()
    df['db'] = df['brightness'].diff()
    
    avg_fps = 1.0 / df['dt'].mean()
    
    # Analyze Patterns
    # 1. Flatline (Stuck pixels or silence)
    std_brightness = df['brightness'].std()
    
    # 2. Jitter / Flicker (Rapid changes back and forth)
    # If derivative changes sign constantly and magnitude is high
    sign_changes = np.sign(df['db']).diff().abs() > 0
    jitter_rate = sign_changes.sum() / len(df)
    
    # 3. Dynamic Range
    b_max = df['brightness'].max()
    b_min = df['brightness'].min()
    dynamic_range = b_max - b_min
    
    print("\n" + "="*40)
    print(" LIGHT ACTIVITY ANALYSIS ")
    print("="*40)
    print(f"Total frames recorded : {len(df)}")
    print(f"Estimated refresh rate: {avg_fps:.1f} FPS")
    print(f"Average Brightness    : {df['brightness'].mean():.1f} (Max: {b_max:.1f}, Min: {b_min:.1f})")
    print(f"Jitter Rate           : {jitter_rate*100:.1f}% of frames flip direction")
    print("-"*40)
    
    # Verdicts
    if std_brightness < 2.0:
        print("[BAD PATTERN] Flatline detected.")
        print("   The lights are practically frozen (very low standard deviation).")
        print("   This usually means silence or a constant drone is washing out the transients.")
    
    elif jitter_rate > 0.55 and df['db'].abs().mean() > 10:
        print("[BAD PATTERN] High-Frequency Jitter ('Fused Capacitor' effect).")
        print("   The lights are flickering aggressively back and forth like a raw strobe.")
        print("   This means the FFT envelope smoothing is too fast and is tracking micro-spikes.")
    
    elif dynamic_range >= 100 and jitter_rate <= 0.45:
        print("[GOOD PATTERN] Healthy Rhythmic Pulses.")
        print("   The lights have massive dynamic range and aren't jittering excessively.")
        print("   This indicates clean transient extraction-it's breathing perfectly with the beat.")
    
    elif dynamic_range < 100:
        print("[NEUTRAL PATTERN] Low Dynamic Range.")
        print("   The visualizer is working and reacting, but it's heavily compressed.")
        print("   This might be due to a quiet section of the song, or the AGC gain is too low.")
    
    else:
        print("[NEUTRAL PATTERN] Average behavior.")
        print("   Everything is functioning normally, but no extreme pulses were detected.")

if __name__ == "__main__":
    analyze()
