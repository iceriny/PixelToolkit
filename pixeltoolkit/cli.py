"""Command-line entry points for the pixel-art tool suite."""

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path

from PIL import Image

from .engine import dimensions, hex_color, save_preview
from .workflow import (PRESETS, Settings, check_outputs, contact_sheet, extract_palette,
                       images_in, inspect_image, palette_text, read_palette, save_image)


def conversion_options(parser):
    parser.add_argument("--preset",choices=PRESETS,default="sprite")
    parser.add_argument("--config",type=Path,help="JSON settings saved by config or the workbench")
    parser.add_argument("--size",type=dimensions)
    for name in ("colors","padding","tolerance"):
        parser.add_argument("--"+name,type=int)
    for name in ("threshold","detail","cleanup","saturation"):
        parser.add_argument("--"+name,type=float)
    parser.add_argument("--alpha",choices=("cutout","keep"))
    parser.add_argument("--tile",action=argparse.BooleanOptionalAction,default=None)
    parser.add_argument("--trim",action=argparse.BooleanOptionalAction,default=None)
    parser.add_argument("--backdrop",type=hex_color)
    parser.add_argument("--palette",type=Path,help="JSON or GPL fixed palette")


def settings_from(args):
    config=json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else {}
    fields=Settings.__dataclass_fields__
    overrides={key:getattr(args,key) for key in fields if getattr(args,key,None) is not None}
    return Settings.resolve(args.preset,config,overrides)


def make_parser():
    parser=argparse.ArgumentParser(prog="pixeltoolkit",description="高清图转像素素材工具组")
    sub=parser.add_subparsers(dest="command",required=True)
    for command in ("convert","batch","compare"):
        p=sub.add_parser(command)
        p.add_argument("source",type=Path)
        p.add_argument("output",type=Path)
        conversion_options(p)
        p.add_argument("--overwrite",action="store_true")
        if command=="convert":
            p.add_argument("--preview",type=Path)
        if command=="batch":
            p.add_argument("--recursive",action="store_true")
            p.add_argument("--shared-palette",action="store_true")
            p.add_argument("--previews",action="store_true")
        if command=="compare":
            p.add_argument("--color-counts",type=int,nargs="+",default=[8,16,24,32])
    p=sub.add_parser("palette")
    p.add_argument("source",type=Path)
    p.add_argument("output",type=Path)
    p.add_argument("--colors",type=int,default=24)
    p.add_argument("--recursive",action="store_true")
    p.add_argument("--overwrite",action="store_true")
    p=sub.add_parser("sheet")
    p.add_argument("source",type=Path)
    p.add_argument("output",type=Path)
    p.add_argument("--columns",type=int,default=4)
    p.add_argument("--scale",type=int,default=4)
    p.add_argument("--recursive",action="store_true")
    p.add_argument("--overwrite",action="store_true")
    p=sub.add_parser("inspect")
    p.add_argument("source",type=Path)
    p.add_argument("--recursive",action="store_true")
    p=sub.add_parser("config")
    p.add_argument("output",type=Path)
    conversion_options(p)
    p.add_argument("--overwrite",action="store_true")
    p=sub.add_parser("gui")
    p.add_argument("--port",type=int,default=0,help="0 selects a free localhost port")
    p.add_argument("--no-browser",action="store_true")
    return parser


def require_png(path):
    if path.suffix.lower()!=".png":
        raise ValueError("image output must end in .png")


def convert(args):
    sources=images_in(args.source)
    if len(sources)!=1 or args.source.is_dir():
        raise ValueError("convert takes one file; use batch for directories")
    require_png(args.output)
    if args.preview:
        require_png(args.preview)
    check_outputs([args.output]+([args.preview] if args.preview else []),sources,args.overwrite)
    settings=settings_from(args)
    palette=read_palette(args.palette) if args.palette else None
    art=settings.convert(sources[0],palette)
    save_image(art,args.output)
    if args.preview:
        save_preview(art,args.preview)
    return str(args.output)


def batch(args):
    if not args.source.is_dir():
        raise ValueError("batch source must be a directory")
    if args.source.resolve()==args.output.resolve() or args.source.resolve() in args.output.resolve().parents:
        raise ValueError("batch output must be outside the source tree")
    sources=images_in(args.source,args.recursive)
    settings=settings_from(args)
    if args.shared_palette and args.palette:
        raise ValueError("choose --palette or --shared-palette")
    outputs=[args.output/"images"/p.relative_to(args.source).with_suffix(".png") for p in sources]
    previews=[args.output/"previews"/p.relative_to(args.source).with_suffix(".png") for p in sources] if args.previews else []
    report=args.output/"report.json"
    palette_path=args.output/"palette.json"
    check_outputs([*outputs,*previews,report]+([palette_path] if args.shared_palette else []),sources,args.overwrite)
    palette=read_palette(args.palette) if args.palette else (
        extract_palette(sources,settings.colors) if args.shared_palette else None)
    records=[]
    for i,(source,output) in enumerate(zip(sources,outputs)):
        try:
            art=settings.convert(source,palette)
            save_image(art,output)
            if args.previews:
                save_preview(art,previews[i])
            records.append({"source":str(source),"output":str(output),"status":"ok"})
        except (ValueError,OSError) as error:
            records.append({"source":str(source),"status":"error","error":str(error)})
    args.output.mkdir(parents=True,exist_ok=True)
    if args.shared_palette:
        palette_path.write_text(palette_text(palette),encoding="utf-8")
    report.write_text(json.dumps({"settings":asdict(settings),"results":records},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    failures=sum(row["status"]=="error" for row in records)
    print(f"{len(records)-failures}/{len(records)} converted. {report}")
    return 1 if failures else 0


def main(argv=None):
    parser=make_parser()
    args=parser.parse_args(argv)
    try:
        if args.command=="gui":
            from .server import serve
            serve(args.port,not args.no_browser)
        elif args.command=="convert":
            print(convert(args))
        elif args.command=="batch":
            if batch(args):
                raise SystemExit(1)
        elif args.command=="palette":
            if args.output.suffix.lower() not in (".json",".gpl"):
                raise ValueError("palette output must be JSON or GPL")
            sources=images_in(args.source,args.recursive)
            check_outputs([args.output],sources,args.overwrite)
            colors=extract_palette(sources,args.colors)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(palette_text(colors,args.output.suffix.lower()),encoding="utf-8")
            print(args.output)
        elif args.command=="inspect":
            print(json.dumps([inspect_image(p) for p in images_in(args.source,args.recursive)],ensure_ascii=False,indent=2))
        elif args.command=="sheet":
            sources=images_in(args.source,args.recursive)
            require_png(args.output)
            check_outputs([args.output],sources,args.overwrite)
            arts=[]
            for path in sources:
                with Image.open(path) as image:
                    arts.append(image.convert("RGBA"))
            save_image(contact_sheet(arts,args.columns,args.scale,[p.name for p in sources]),args.output)
            print(args.output)
        elif args.command=="compare":
            if args.palette:
                raise ValueError("compare varies automatic color count; omit --palette")
            sources=images_in(args.source)
            if len(sources)!=1 or args.source.is_dir():
                raise ValueError("compare takes one source file")
            require_png(args.output)
            check_outputs([args.output],sources,args.overwrite)
            settings=settings_from(args)
            arts=[replace(settings,colors=count).convert(sources[0]) for count in args.color_counts]
            save_image(contact_sheet(arts,4,4,[f"{c} colors" for c in args.color_counts]),args.output)
            print(args.output)
        elif args.command=="config":
            check_outputs([args.output],overwrite=args.overwrite)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(asdict(settings_from(args)),indent=2)+"\n",encoding="utf-8")
            print(args.output)
    except (ValueError,OSError,TypeError,KeyError) as error:
        parser.exit(2,f"error: {error}\n")


if __name__=="__main__":
    main()
