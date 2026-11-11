"""Local browser workbench. Files stay on this computer."""

import base64
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore, Timer
import webbrowser
from zipfile import ZipFile

from PIL import Image

from .engine import save_preview
from .workflow import Settings, extract_palette, palette_text, read_palette


MAX_BODY=64*1024*1024


def png_bytes(image):
    output=BytesIO()
    image.save(output,format="PNG")
    return output.getvalue()


def process(payload, operation):
    files=payload.get("files",[])
    if not 1<=len(files)<=100:
        raise ValueError("choose 1–100 source images")
    settings=Settings.resolve(payload.get("preset","sprite"),payload.get("settings",{}))
    if max(settings.size)>512:
        raise ValueError("workbench size is limited to 512; use CLI for larger exports")
    with TemporaryDirectory(prefix="pixeltoolkit-") as temporary:
        root=Path(temporary)
        paths=[]
        names=set()
        for i,file in enumerate(files):
            name=Path(file["name"].replace("\\","/")).stem
            if not name or name.casefold() in names:
                raise ValueError("source names must have distinct stems")
            names.add(name.casefold())
            path=root/(str(i)+".png")
            path.write_bytes(base64.b64decode(file["data"],validate=True))
            with Image.open(path) as art:
                art.verify()
            paths.append((name,path))
        if operation=="palette":
            return palette_text(extract_palette([p for _,p in paths],settings.colors)).encode(), "application/json"
        palette=None
        if payload.get("palette"):
            path=root/"palette.json"
            path.write_text(payload["palette"],encoding="utf-8")
            palette=read_palette(path)
        elif payload.get("shared"):
            palette=extract_palette([p for _,p in paths],settings.colors)
        if operation=="convert":
            if len(paths)!=1:
                raise ValueError("single preview takes one image")
            result=settings.convert(paths[0][1],palette)
            return json.dumps({"image":base64.b64encode(png_bytes(result)).decode(),
                               "size":result.size,"settings":asdict(settings)}).encode(),"application/json"
        archive=BytesIO()
        with ZipFile(archive,"w") as zip_file:
            for name,path in paths:
                result=settings.convert(path,palette)
                zip_file.writestr(f"images/{name}.png",png_bytes(result))
                preview=root/"preview.png"
                save_preview(result,preview)
                zip_file.write(preview,f"previews/{name}.png")
            zip_file.writestr("settings.json",json.dumps(asdict(settings),indent=2))
            if palette:
                zip_file.writestr("palette.json",palette_text(palette))
        return archive.getvalue(),"application/zip"


def serve(port=0, open_browser=True):
    if not 0<=port<=65535:
        raise ValueError("port must be between 0 and 65535")
    token=secrets.token_urlsafe(24)
    slots=BoundedSemaphore(2)

    class Handler(BaseHTTPRequestHandler):
        def respond(self,status,body,kind="application/json"):
            self.send_response(status)
            self.send_header("Content-Type",kind)
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path not in ("/","/favicon.ico"):
                self.respond(404,b"{}")
                return
            if self.path=="/favicon.ico":
                self.respond(204,b"")
                return
            html=Path(__file__).with_name("web.html").read_text(encoding="utf-8").replace("__TOKEN__",token)
            self.respond(200,html.encode(),"text/html; charset=utf-8")

        def do_POST(self):
            if self.headers.get("X-PixelToolkit-Token")!=token:
                self.respond(403,b'{"error":"Invalid workbench token"}')
                return
            if self.path not in ("/convert","/batch","/palette"):
                self.respond(404,b"{}")
                return
            if not slots.acquire(blocking=False):
                self.respond(429,b'{"error":"Another task is still running"}')
                return
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=MAX_BODY:
                    raise ValueError("upload must be under 64 MB")
                payload=json.loads(self.rfile.read(length))
                body,kind=process(payload,self.path[1:])
                self.respond(200,body,kind)
            except (ValueError,OSError,TypeError,KeyError,Image.DecompressionBombError) as error:
                self.respond(400,json.dumps({"error":str(error)}).encode())
            finally:
                slots.release()

        def log_message(self,format,*args):
            return

    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    url=f"http://127.0.0.1:{server.server_port}"
    print(f"PixelToolkit {url}\nPress Ctrl+C to stop.",flush=True)
    if open_browser:
        timer=Timer(.3,webbrowser.open,args=(url,))
        timer.daemon=True
        timer.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
