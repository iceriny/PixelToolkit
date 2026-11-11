"""Verify that the frozen app serves its UI and converts an uploaded image."""

import base64
from io import BytesIO
import json
import os
from pathlib import Path
from queue import Queue
import re
import subprocess
import sys
from threading import Thread
import urllib.request

from PIL import Image


def main():
    executable = Path(sys.argv[1]).resolve()
    process = subprocess.Popen(
        [str(executable), "gui", "--no-browser"], stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    ready = Queue()

    def read_url():
        for line in process.stdout:
            print(line.strip(), flush=True)
            if line.startswith("PixelToolkit http://"):
                ready.put(line.strip().split()[-1])
                return

    Thread(target=read_url, daemon=True).start()
    try:
        url = ready.get(timeout=45)
        with urllib.request.urlopen(url, timeout=10) as response:
            page = response.read().decode("utf-8")
        token = re.search(r'const token="([^"]+)"', page).group(1)
        image = BytesIO()
        Image.new("RGBA", (64,64), (180,90,50,200)).save(image, format="PNG")
        payload = json.dumps({
            "files": [{"name": "sample.png", "data": base64.b64encode(image.getvalue()).decode()}],
            "settings": {"size": [16,16], "alpha": "keep", "padding": 1},
        }).encode()
        request = urllib.request.Request(url+"/convert", payload, {
            "Content-Type": "application/json", "X-PixelToolkit-Token": token,
        })
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
        assert result["size"] == [16,16], result
        with Image.open(BytesIO(base64.b64decode(result["image"]))) as converted:
            assert converted.size == (16,16)
        print("Portable UI and image conversion passed", flush=True)
    finally:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            process.terminate()
        process.wait(timeout=15)


if __name__ == "__main__":
    main()
