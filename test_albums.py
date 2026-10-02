import requests
import io
from PIL import Image
import colorsys
import json
import sys

# Import functions from main
from main import get_top_3_colors, _is_visually_distinct, _clamp_background_brightness, boost_saturation

def fetch_top_albums():
    # Let's search iTunes for popular albums from 2025 (or just general popular ones if none specific)
    url = "https://itunes.apple.com/search?term=album&entity=album&limit=20&attribute=releaseYearTerm&term=2025"
    response = requests.get(url)
    if response.status_code != 200:
        print("Failed to fetch from iTunes")
        return []
    
    data = response.json()
    albums = []
    for item in data.get("results", []):
        img_url = item.get("artworkUrl100", "").replace("100x100bb", "300x300bb")
        if img_url:
            albums.append((item.get("collectionName", "Unknown Album"), img_url))
    
    # fallback if search by year fails
    if not albums:
        url = "https://itunes.apple.com/search?term=pop&entity=album&limit=20"
        response = requests.get(url)
        data = response.json()
        for item in data.get("results", []):
            img_url = item.get("artworkUrl100", "").replace("100x100bb", "300x300bb")
            if img_url:
                albums.append((item.get("collectionName", "Unknown Album"), img_url))
    return albums[:20]

def analyze_relationships(bg, bass, treble):
    # Convert to HSV to analyze
    bg_hsv = colorsys.rgb_to_hsv(bg[0]/255, bg[1]/255, bg[2]/255)
    bass_hsv = colorsys.rgb_to_hsv(bass[0]/255, bass[1]/255, bass[2]/255)
    treble_hsv = colorsys.rgb_to_hsv(treble[0]/255, treble[1]/255, treble[2]/255)
    
    # 1. Luminance (V)
    lum_diff_bass_treble = abs(bass_hsv[2] - treble_hsv[2])
    lum_diff_bg = abs(bg_hsv[2] - bass_hsv[2])
    
    # 2. Hue distance
    hue_dist_bass_treble = min(abs(bass_hsv[0] - treble_hsv[0]), 1.0 - abs(bass_hsv[0] - treble_hsv[0]))
    
    # 3. Saturation difference
    sat_diff = abs(bass_hsv[1] - treble_hsv[1])
    
    print(f"  Background: {bg} (H={bg_hsv[0]:.2f}, S={bg_hsv[1]:.2f}, V={bg_hsv[2]:.2f})")
    print(f"  Bass:       {bass} (H={bass_hsv[0]:.2f}, S={bass_hsv[1]:.2f}, V={bass_hsv[2]:.2f})")
    print(f"  Treble:     {treble} (H={treble_hsv[0]:.2f}, S={treble_hsv[1]:.2f}, V={treble_hsv[2]:.2f})")
    
    # Analysis
    print(f"  --> Bass vs Treble Hue Dist: {hue_dist_bass_treble*360:.0f} degrees")
    print(f"  --> Bass vs Treble Lum Diff: {lum_diff_bass_treble:.2f}")
    print(f"  --> Bass vs Treble Sat Diff: {sat_diff:.2f}")
    if hue_dist_bass_treble * 360 > 150:
        print("  --> WARNING: Bass and Treble are complementary/opposites. Could be harsh.")
    elif hue_dist_bass_treble * 360 < 60:
        print("  --> GOOD: Bass and Treble are analogous.")
    
    if lum_diff_bass_treble > 0.4:
        print("  --> WARNING: High luminance difference between Bass and Treble.")
    else:
        print("  --> GOOD: Luminance is balanced.")

def main():
    albums = fetch_top_albums()
    for i, (name, url) in enumerate(albums):
        print(f"\n[{i+1}/20] Analyzing '{name}'")
        try:
            resp = requests.get(url)
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            palette = get_top_3_colors(img)
            
            bg = palette[0]
            bass = palette[1]
            treble = palette[2]
            
            analyze_relationships(bg, bass, treble)
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == '__main__':
    # Need to define EXTRACTION_SATURATION_BOOST for main.py to work properly since it's global there.
    # Wait, main.py imports everything. Let's just run this and see.
    main()
