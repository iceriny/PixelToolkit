# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "Pillow>=11,<13"]
# ///
"""Reusable Oklab pixel-art conversion engine."""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps


LMS = np.array([[.41222147, .53633254, .05144599],
                [.21190350, .68069955, .10739696],
                [.08830246, .28171884, .62997870]], dtype=np.float32)
LAB = np.array([[.21045426, .79361779, -.00407205],
                [1.97799850, -2.42859221, .45059371],
                [.02590404, .78277177, -.80867577]], dtype=np.float32)
LAB_INV = np.linalg.inv(LAB)
LMS_INV = np.linalg.inv(LMS)
SUPPORTED = {".png", ".webp", ".jpg", ".jpeg", ".tiff", ".bmp"}
PRESETS = {
    "item": (16, 14, 1, "cutout"),
    "detail": (32, 24, 2, "cutout"),
    "tile": (16, 12, 0, "keep"),
    "ui": (64, 32, 0, "keep"),
}


def to_lab(rgb):
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    return np.cbrt(linear @ LMS.T) @ LAB.T


def to_rgb(lab):
    linear = np.clip(((lab @ LAB_INV.T) ** 3) @ LMS_INV.T, 0, 1)
    rgb = np.where(linear <= .0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - .055)
    return np.rint(rgb * 255).astype(np.uint8)


def remove_backdrop(art, key, tolerance):
    """Remove only key-colored regions connected to the image border."""
    rgba = np.array(art)
    eligible = np.max(np.abs(rgba[..., :3].astype(np.int16) - key), axis=2) <= tolerance
    eligible |= rgba[..., 3] == 0
    mask = ImageOps.expand(Image.fromarray(eligible.astype(np.uint8)), border=1, fill=1)
    ImageDraw.floodfill(mask, (0, 0), 2)
    rgba[..., 3][np.asarray(mask)[1:-1, 1:-1] == 2] = 0
    return Image.fromarray(rgba)


def sample_grid(art, size, detail):
    """Supersample a small working grid, keeping coherent local color transitions."""
    width, height = size
    samples = min(8, max(2, 768 // max(width, height)))
    work = art.resize((width * samples, height * samples), Image.Resampling.BOX)
    rgba = np.asarray(work, dtype=np.float32) / 255
    lab = to_lab(rgba[..., :3])
    light = lab[..., 0]
    energy = np.zeros_like(light)
    for axis in (0, 1):
        edge = np.abs(np.diff(light, axis=axis))
        if axis == 0:
            energy[:-1, :] += edge * rgba[1:, :, 3]
            energy[1:, :] += edge * rgba[:-1, :, 3]
        else:
            energy[:, :-1] += edge * rgba[:, 1:, 3]
            energy[:, 1:] += edge * rgba[:, :-1, 3]

    def cells(array):
        tail = array.shape[2:]
        return array.reshape(height, samples, width, samples, *tail).swapaxes(1, 2)

    coverage = cells(rgba[..., 3])
    values = cells(lab)
    weights = coverage * (1 + detail * np.clip(cells(energy) * 3, 0, 1))
    center = (samples - 1) / 2
    grid = (np.arange(samples, dtype=np.float32) - center) / samples
    spatial = 1 - .7 * (grid[:, None] ** 2 + grid[None, :] ** 2)
    weights *= spatial
    denominator = np.maximum(weights.sum((2, 3)), 1e-8)
    mean = (values * weights[..., None]).sum((2, 3)) / denominator[..., None]
    # Shift the local mean toward a coherent tone when two surfaces share one cell.
    spread = ((values - mean[:, :, None, None]) ** 2).sum(axis=-1)
    coherent = weights * np.exp(-spread * (35 * detail))
    tone = (values * coherent[..., None]).sum((2, 3)) / np.maximum(coherent.sum((2, 3)), 1e-8)[..., None]
    return tone, coverage.mean((2, 3))


def nearest(points, palette):
    indices = np.empty(len(points), dtype=np.int32)
    for start in range(0, len(points), 4096):
        chunk = points[start:start + 4096]
        distances = ((chunk[:, None, :] - palette[None, :, :]) ** 2).sum(axis=-1)
        indices[start:start + len(chunk)] = distances.argmin(axis=1)
    return indices


def fit_palette(points, weights, count):
    # Limit palette fitting to a deterministic representative sample. Full remap follows.
    stride = max(1, (len(points) + 16383) // 16384)
    points, weights = points[::stride], weights[::stride]
    count = min(count, len(points))
    center = np.average(points, axis=0, weights=weights)
    palette = [points[np.argmin(((points - center) ** 2).sum(axis=1))]]
    error = np.full(len(points), np.inf)
    for _ in range(1, count):
        error = np.minimum(error, ((points - palette[-1]) ** 2).sum(axis=1))
        index = np.argmax(error * weights)
        if error[index] < 1e-9:
            break
        palette.append(points[index])
    palette = np.array(palette)
    for _ in range(8):
        labels = nearest(points, palette)
        mass = np.bincount(labels, weights, minlength=len(palette))
        totals = np.stack([np.bincount(labels, points[:, i] * weights, minlength=len(palette))
                           for i in range(3)], axis=1)
        active = mass > 0
        updated = palette.copy()
        updated[active] = totals[active] / mass[active, None]
        if np.max(np.abs(updated - palette)) < .0001:
            break
        palette = updated
    return palette


def clean_clusters(labels, visible, palette, strength):
    """Remove weak, isolated color specks without eroding the alpha silhouette."""
    if strength == 0:
        return labels
    marked = np.where(visible, labels, -1)
    pad = np.pad(marked, 1, constant_values=-1)
    neighbors = np.stack([pad[:-2, 1:-1], pad[2:, 1:-1], pad[1:-1, :-2], pad[1:-1, 2:]])
    counts = (neighbors[:, None] == neighbors[None, :]).sum(axis=0)
    choices = np.take_along_axis(neighbors, counts.argmax(axis=0)[None, ...], axis=0)[0]
    close = np.linalg.norm(palette[labels] - palette[np.maximum(choices, 0)], axis=-1) < strength
    replace = visible & (choices >= 0) & (counts.max(axis=0) >= 3)
    replace &= ~(neighbors == labels).any(axis=0) & close
    return np.where(replace, choices, labels)


def pixelize(source: Path, size: int | tuple[int, int] = 32, colors: int = 24,
             padding: int = 2, tile: bool = False, *, alpha: str = "cutout",
             threshold: float = .48, detail: float = .55, cleanup: float = .045,
             saturation: float = 1, palette=None, backdrop=None, tolerance: int = 24,
             trim: bool = True) -> Image.Image:
    width, height = (size, size) if isinstance(size, int) else size
    with Image.open(source) as original:
        art = ImageOps.exif_transpose(original).convert("RGBA")
    if backdrop is not None:
        art = remove_backdrop(art, np.asarray(backdrop, dtype=np.int16), tolerance)
    bounds = art.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"Source has no visible pixels: {source}")
    if not tile and trim:
        bounds = art.getchannel("A").point(lambda a: 255 if a >= 16 else 0).getbbox() or bounds
        art = art.crop(bounds)
    if tile:
        target = width, height
    else:
        available = width - 2 * padding, height - 2 * padding
        if min(available) < 1:
            raise ValueError("Padding must leave room for the sprite")
        scale = min(available[0] / art.width, available[1] / art.height)
        target = max(1, round(art.width * scale)), max(1, round(art.height * scale))
    tones, coverage = sample_grid(art, target, detail)
    tones[..., 1:] *= saturation
    # Normalize out-of-gamut colors before fitting, so the preview matches exported RGB.
    tones = to_lab(to_rgb(tones).astype(np.float32) / 255)
    opacity = (coverage >= threshold).astype(np.uint8) * 255 if alpha == "cutout" else np.rint(coverage * 255).astype(np.uint8)
    visible = opacity > 0
    if not visible.any():
        raise ValueError(f"Nothing remains after the alpha threshold: {source}")
    points = tones[visible]
    fitted = (fit_palette(points, np.maximum(coverage[visible], .05), colors) if palette is None
              else to_lab(np.asarray(palette, dtype=np.float32) / 255))
    labels = np.zeros(visible.shape, dtype=np.int32)
    labels[visible] = nearest(points, fitted)
    labels = clean_clusters(labels, visible, fitted, cleanup)
    rgba = np.zeros((*visible.shape, 4), dtype=np.uint8)
    rgba[..., 3] = opacity
    rgba[visible, :3] = to_rgb(fitted)[labels[visible]]
    result = Image.new("RGBA", (width, height))
    result.paste(Image.fromarray(rgba), ((width - target[0]) // 2, (height - target[1]) // 2))
    return result


def hex_color(value):
    value = value.removeprefix("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("Use RRGGBB")
    try:
        return tuple(bytes.fromhex(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use RRGGBB") from error


def dimensions(value):
    try:
        values = tuple(int(v) for v in value.lower().split("x"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use N or WIDTHxHEIGHT") from error
    if len(values) not in (1, 2) or not all(1 <= v <= 1024 for v in values):
        raise argparse.ArgumentTypeError("Each edge must be between 1 and 1024")
    return values if len(values) == 2 else values * 2


def save_preview(result, path):
    # Show the asset on dark and light backgrounds at native size and magnified.
    width, height = result.size
    scale = max(1, min(12, 384 // max(width, height)))
    enlarged = result.resize((width * scale, height * scale), Image.Resampling.NEAREST)
    panel = Image.new("RGB", (enlarged.width * 2 + 36, enlarged.height + height + 36), "#353029")
    draw = ImageDraw.Draw(panel)
    for index, background in enumerate(("#25262a", "#d6c5a8")):
        x = 12 + index * (enlarged.width + 12)
        draw.rectangle((x, 12, x + enlarged.width - 1, 12 + enlarged.height - 1), fill=background)
        panel.paste(enlarged, (x, 12), enlarged)
        y = enlarged.height + 24
        draw.rectangle((x, y, x + width - 1, y + height - 1), fill=background)
        panel.paste(result, (x, y), result)
    path.parent.mkdir(parents=True, exist_ok=True)
    panel.save(path)
