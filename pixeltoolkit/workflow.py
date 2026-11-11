"""Configuration, palette interchange, file planning and reusable review operations."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .engine import SUPPORTED, fit_palette, hex_color, pixelize, to_lab, to_rgb


PRESETS = {
    "icon": dict(size=(16,16), colors=14, padding=1, alpha="cutout"),
    "sprite": dict(size=(32,32), colors=24, padding=2, alpha="cutout"),
    "texture": dict(size=(32,32), colors=16, padding=0, alpha="keep", tile=True, trim=False),
    "illustration": dict(size=(160,96), colors=32, padding=0, alpha="keep", trim=False),
    "ui": dict(size=(64,64), colors=24, padding=0, alpha="keep", trim=False),
}


@dataclass(frozen=True)
class Settings:
    size: tuple[int,int] = (32,32)
    colors: int = 24
    padding: int = 2
    tile: bool = False
    trim: bool = True
    alpha: str = "cutout"
    threshold: float = .48
    detail: float = .55
    cleanup: float = .045
    saturation: float = 1
    backdrop: tuple[int,int,int] | None = None
    tolerance: int = 24

    @classmethod
    def resolve(cls, preset="sprite", config=None, overrides=None):
        data = {**PRESETS[preset], **(config or {}), **(overrides or {})}
        if "size" in data:
            data["size"] = tuple(data["size"])
        if isinstance(data.get("backdrop"), str):
            data["backdrop"] = hex_color(data["backdrop"])
        result = cls(**data)
        result.validate()
        return result

    def validate(self):
        if len(self.size)!=2 or any(type(x) is not int or not 1<=x<=1024 for x in self.size):
            raise ValueError("size must contain two integers between 1 and 1024")
        if type(self.colors) is not int or not 2<=self.colors<=256:
            raise ValueError("colors must be an integer between 2 and 256")
        if type(self.padding) is not int or self.padding<0 or (not self.tile and min(self.size)<=2*self.padding):
            raise ValueError("padding must leave at least one pixel of content")
        if self.alpha not in ("cutout","keep"):
            raise ValueError("alpha must be cutout or keep")
        for key in ("threshold","detail","cleanup","saturation"):
            value=getattr(self,key)
            limit=2 if key in ("detail","saturation") else 1
            if not isinstance(value,(int,float)) or not np.isfinite(value) or not 0<=value<=limit:
                raise ValueError(f"{key} must be between 0 and {limit}")
        if self.threshold==0 or type(self.tolerance) is not int or not 0<=self.tolerance<=255:
            raise ValueError("threshold must be positive; tolerance must be an integer from 0 to 255")
        if any(type(getattr(self,key)) is not bool for key in ("tile","trim")):
            raise ValueError("tile and trim must be boolean")
        if self.backdrop is not None and (len(self.backdrop)!=3 or
                any(type(x) is not int or not 0<=x<=255 for x in self.backdrop)):
            raise ValueError("backdrop must be an RGB triple or a six-digit hex color")

    def convert(self, source, palette=None):
        self.validate()
        return pixelize(Path(source), palette=palette, **asdict(self))


def read_palette(path):
    path=Path(path)
    if path.suffix.lower()==".gpl":
        rows=[]
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            fields=line.split()
            if len(fields)>=3 and all(x.isdigit() for x in fields[:3]):
                rgb=tuple(map(int,fields[:3]))
                rows.append(rgb)
    else:
        value=json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(value,dict):
            value=value["colors"] if "colors" in value else [
                color for group in value.values() for color in group]
        rows=[hex_color(color) if isinstance(color,str) else tuple(color) for color in value]
    if not rows or len(rows)>256 or any(len(row)!=3 or any(type(v) is not int or not 0<=v<=255 for v in row) for row in rows):
        raise ValueError("palette must contain 1–256 RGB colors")
    return list(dict.fromkeys(rows))


def extract_palette(sources, count=24):
    if not 2<=count<=256:
        raise ValueError("palette color count must be between 2 and 256")
    samples,weights=[],[]
    # A fixed total fitting budget also bounds memory for large input folders.
    per_image=max(1,16384//len(sources))
    side=max(1,int(per_image**.5))
    for source in sources:
        with Image.open(source) as original:
            art=ImageOps.exif_transpose(original).convert("RGBA")
            art.thumbnail((side,side),Image.Resampling.BOX)
            pixels=np.asarray(art,dtype=np.float32).reshape(-1,4)/255
        visible=pixels[:,3]>.01
        samples.append(pixels[visible,:3])
        weights.append(pixels[visible,3])
    rgb=np.concatenate(samples)
    if not len(rgb):
        raise ValueError("no visible pixels in palette inputs")
    fitted=fit_palette(to_lab(rgb),np.concatenate(weights),count)
    return [tuple(int(v) for v in color) for color in to_rgb(fitted[np.argsort(fitted[:,0])])]


def palette_text(colors, suffix=".json"):
    if suffix==".gpl":
        return "GIMP Palette\nName: PixelToolkit\nColumns: 8\n#\n"+"".join(
            f"{r:3} {g:3} {b:3}  Color {i+1}\n" for i,(r,g,b) in enumerate(colors))
    return json.dumps({"colors":["#%02X%02X%02X"%tuple(rgb) for rgb in colors]},indent=2)+"\n"


def images_in(source, recursive=False):
    source=Path(source)
    if source.is_file():
        if source.suffix.lower() not in SUPPORTED:
            raise ValueError(f"unsupported image format: {source.suffix}")
        return [source]
    if not source.is_dir():
        raise ValueError(f"input does not exist: {source}")
    paths=source.rglob("*") if recursive else source.iterdir()
    result=sorted(p for p in paths if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not result:
        raise ValueError("input contains no supported images")
    return result


def check_outputs(outputs, sources=(), overwrite=False):
    reserved={Path(p).resolve() for p in sources}
    planned=set()
    for output in outputs:
        path=Path(output).resolve()
        key=str(path).casefold()
        if path in reserved or key in planned:
            raise ValueError(f"output collides with an input or another output: {output}")
        if path.exists() and (not overwrite or path.is_dir()):
            raise ValueError(f"output exists: {output}; use --overwrite to replace files")
        planned.add(key)


def save_image(image, path):
    path=Path(path)
    if path.suffix.lower()!=".png":
        raise ValueError("image output must have a .png extension")
    path.parent.mkdir(parents=True,exist_ok=True)
    image.save(path,format="PNG")


def inspect_image(path):
    with Image.open(path) as image:
        rgba=np.asarray(image.convert("RGBA"))
        alpha=rgba[...,3]
        visible=alpha>0
        colors=np.unique(rgba[visible,:3],axis=0)
        return {"path":str(path),"size":list(image.size),"mode":image.mode,
                "visible_colors":len(colors),"transparent_pixels":int((alpha==0).sum()),
                "partial_alpha_pixels":int(((alpha>0)&(alpha<255)).sum()),
                "visible_bounds":image.convert("RGBA").getbbox()}


def contact_sheet(images, columns=4, scale=4, labels=None):
    if not images or not 1<=columns<=32 or not 1<=scale<=32:
        raise ValueError("sheet needs images, 1–32 columns and a 1–32 scale")
    width=max(im.width for im in images)*scale+20
    height=max(im.height for im in images)*scale+32
    result=Image.new("RGBA",(width*min(columns,len(images)),height*((len(images)+columns-1)//columns)),"#28262a")
    draw=ImageDraw.Draw(result)
    for i,art in enumerate(images):
        x,y=(i%columns)*width,(i//columns)*height
        for yy in range(0,height-22,8):
            for xx in range(0,width,8):
                draw.rectangle((x+xx,y+yy,x+min(xx+7,width-1),y+min(yy+7,height-23)),
                               fill="#49464b" if (xx+yy)//8%2 else "#5b575c")
        scaled=art.resize((art.width*scale,art.height*scale),Image.Resampling.NEAREST)
        result.alpha_composite(scaled,(x+(width-scaled.width)//2,y+6))
        # File names can be non-ASCII; use an installed font when available.
        label=(labels or [str(n+1) for n in range(len(images))])[i]
        from PIL import ImageFont
        font_path=Path("C:/Windows/Fonts/msyh.ttc")
        font=ImageFont.truetype(str(font_path),11) if font_path.exists() else ImageFont.load_default()
        label=label if font_path.exists() else label.encode("ascii","replace").decode()
        while draw.textlength(label,font=font)>width-12:
            label=label[:-2]
        draw.text((x+6,y+height-20),label,fill="#eee0c6",font=font)
    return result
