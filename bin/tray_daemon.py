import os
import sys
import subprocess
import pystray
from PIL import Image, ImageDraw

def create_indicator_image():
    # Create 32x32 transparent canvas
    image = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    accent_color = (247, 247, 247, 255) # Clean off-white matching taskbar
    
    # Draw 3 minimalist sliders
    # Slider 1
    draw.line([(6, 8), (26, 8)], fill=accent_color, width=2)
    draw.ellipse([(10, 5), (16, 11)], fill=accent_color)
    
    # Slider 2
    draw.line([(6, 16), (26, 16)], fill=accent_color, width=2)
    draw.ellipse([(18, 13), (24, 19)], fill=accent_color)
    
    # Slider 3
    draw.line([(6, 24), (26, 24)], fill=accent_color, width=2)
    draw.ellipse([(8, 21), (14, 27)], fill=accent_color)
    
    return image

def on_click(icon, item):
    # Toggle control center
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    env["WAYLAND_DISPLAY"] = "wayland-0"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    # Kill any active rofi or control-center instances, or spawn a new one
    subprocess.run("pkill -f rofi-control-center.py || python3 /home/sl01220/.local/bin/rofi-control-center.py &", shell=True, env=env)

def main():
    icon_image = create_indicator_image()
    
    # MenuItem with default=True handles the primary double/single click on statusnotifier
    icon = pystray.Icon(
        "control_center",
        icon_image,
        "Control Center",
        menu=pystray.Menu(
            pystray.MenuItem("Open Control Center", on_click, default=True, visible=False),
            pystray.MenuItem("Exit", lambda icon: icon.stop())
        )
    )
    
    # Set environment variables for SNI protocol integration
    os.environ["DISPLAY"] = ":0"
    os.environ["WAYLAND_DISPLAY"] = "wayland-0"
    os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"
    
    icon.run()

if __name__ == "__main__":
    main()
