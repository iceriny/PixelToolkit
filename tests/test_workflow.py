import base64
from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

import numpy as np
from PIL import Image, ImageDraw

from pixeltoolkit.cli import main
from pixeltoolkit.server import process
from pixeltoolkit.workflow import Settings, read_palette


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.source=self.root/"input"
        self.source.mkdir()
        art=Image.new("RGBA",(256,256))
        d=ImageDraw.Draw(art)
        d.ellipse((25,20,225,226),fill="#a15348",outline="#d6bb86",width=14)
        d.rectangle((90,90,166,172),fill="#7fbdb0")
        d.line((42,164,211,81),fill="#e4d2aa",width=8)
        self.image=self.source/"样本.png"
        art.save(self.image)

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self,*args):
        with redirect_stdout(StringIO()):
            main([str(arg) for arg in args])

    def test_web_and_cli_use_same_conversion(self):
        output=self.root/"pixel.png"
        self.invoke("convert",self.image,output,"--size","24x16","--padding","1","--colors","8")
        payload={"files":[{"name":"样本.png","data":base64.b64encode(self.image.read_bytes()).decode()}],
                 "settings":{"size":[24,16],"padding":1,"colors":8}}
        body,kind=process(payload,"convert")
        self.assertEqual(kind,"application/json")
        with Image.open(BytesIO(base64.b64decode(json.loads(body)["image"]))) as actual, Image.open(output) as expected:
            self.assertEqual(actual.tobytes(),expected.tobytes())

    def test_batch_shared_palette_and_recursive_paths(self):
        nested=self.source/"nested"
        nested.mkdir()
        Image.new("RGBA",(32,32),"#526e96").save(nested/"样本.png")
        output=self.root/"batch"
        self.invoke("batch",self.source,output,"--recursive","--shared-palette","--colors","8","--previews")
        palette=set(read_palette(output/"palette.json"))
        self.assertEqual(len(json.loads((output/"report.json").read_text(encoding="utf-8"))["results"]),2)
        self.assertTrue((output/"images/nested/样本.png").exists())
        for path in (output/"images").rglob("*.png"):
            with Image.open(path) as image:
                pixels=np.asarray(image)
                self.assertTrue({tuple(v) for v in pixels[pixels[...,3]>0,:3]}<=palette)

    def test_source_and_case_insensitive_name_collisions_rejected(self):
        original=self.image.read_bytes()
        with self.assertRaises(SystemExit):
            self.invoke("convert",self.image,self.image,"--overwrite")
        self.assertEqual(original,self.image.read_bytes())
        Image.new("RGBA",(10,10),"red").save(self.source/"same.png")
        Image.new("RGB",(10,10),"blue").save(self.source/"same.jpg")
        with self.assertRaises(SystemExit):
            self.invoke("batch",self.source,self.root/"bad")
        self.assertFalse((self.root/"bad").exists())

    def test_config_and_palette_round_trip(self):
        config=self.root/"settings.json"
        self.invoke("config",config,"--preset","icon","--alpha","keep")
        self.assertEqual(json.loads(config.read_text())["size"],[16,16])
        for suffix in ("json","gpl"):
            palette=self.root/f"colors.{suffix}"
            self.invoke("palette",self.source,palette,"--colors","8")
            self.assertLessEqual(len(read_palette(palette)),8)
        out=self.root/"configured.png"
        self.invoke("convert",self.image,out,"--config",config,"--palette",self.root/"colors.gpl")
        with Image.open(out) as image:
            self.assertEqual(image.size,(16,16))

    def test_web_batch_contains_assets_and_previews(self):
        payload={"files":[{"name":"样本.png","data":base64.b64encode(self.image.read_bytes()).decode()}],
                 "shared":True}
        body,kind=process(payload,"batch")
        self.assertEqual(kind,"application/zip")
        with ZipFile(BytesIO(body)) as archive:
            self.assertEqual(set(archive.namelist()),{
                "images/样本.png","previews/样本.png","settings.json","palette.json"})

    def test_partial_alpha_and_invalid_options(self):
        translucent=self.root/"glass.png"
        Image.new("RGBA",(32,32),(200,120,60,100)).save(translucent)
        result=Settings.resolve("texture",{"alpha":"keep"}).convert(translucent)
        alpha=np.asarray(result)[...,3]
        self.assertTrue(((alpha>0)&(alpha<255)).any())
        for config in ({"size":[0,32]},{"size":[16,16],"padding":8},
                       {"detail":float("nan")},{"colors":1}):
            with self.assertRaises(ValueError):
                Settings.resolve(config=config)

    def test_compare_sheet_and_inspect_commands(self):
        compare=self.root/"compare.png"
        self.invoke("compare",self.image,compare,"--size","16","--color-counts","4","8")
        with Image.open(compare) as image:
            self.assertGreater(image.width,32)
        self.invoke("sheet",self.source,self.root/"sheet.png","--scale","1")
        output=StringIO()
        with redirect_stdout(output):
            main(["inspect",str(self.image)])
        report=json.loads(output.getvalue())
        self.assertEqual(report[0]["size"],[256,256])
        self.assertGreater(report[0]["transparent_pixels"],0)


if __name__=="__main__":
    unittest.main()
