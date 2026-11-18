"""Command line interface.

    python -m nautilus list
    python -m nautilus enhance Input Output                      # default model (WaterNet)
    python -m nautilus enhance photo.jpg Output                  # a single photo
    python -m nautilus enhance Input Output -m fusion -p red=1.4 -p fusion.sharpen=2
    python -m nautilus enhance Input Output -m waternet -m fusion -m funiegan   # compare
    python -m nautilus compare photo.jpg               # photo_compare.jpg: original + every method
    python -m nautilus compare dive.mp4 --time 12      # the same for one frame of a video
    python -m nautilus video dive.mp4 -m fusion --start 60 --duration 10        # video preview
"""

import argparse
import csv
import json
import os
import sys
import time

import cv2

from . import load_models, metrics

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")


def find_images(folder):
    for root, _, files in os.walk(folder):
        for name in sorted(files):
            if name.lower().endswith(IMAGE_EXTENSIONS):
                yield os.path.relpath(os.path.join(root, name), folder)


def parse_params(pairs, model):
    values = {}
    names = {p.name for p in model.params}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            sys.exit(f"Bad parameter '{pair}': use name=value")
        # "fusion.sharpen=2" targets one model when several share a parameter name.
        target, dot, name = key.rpartition(".")
        if dot:
            if target != model.id:
                continue
            key = name
        if key not in names:
            continue  # parameter belongs to another selected model
        try:
            values[key] = json.loads(value)
        except json.JSONDecodeError:
            values[key] = value
    return values


def cmd_list(models, _args):
    from . import inference

    print(f"AI methods run on: {inference.device_name()} ({inference.BACKEND} {inference.DEVICE})\n")
    for m in models.values():
        status = "" if m.check() is None else f"  [unavailable: {m.check()}]"
        print(f"{m.id:<12} {m.name}  ({m.technical}){status}")
        for p in m.params:
            extra = f" choices={p.choices}" if p.choices else f" range={p.min}..{p.max}" if p.min is not None else ""
            print(f"    {p.name}={p.default!r}{extra}  {p.help}")


def cmd_enhance(models, args):
    selected = args.model or [next(iter(models))]
    for mid in selected:
        if mid not in models:
            sys.exit(f"Unknown model '{mid}'. Available: {', '.join(models)}")
        problem = models[mid].check()
        if problem:
            sys.exit(f"{mid}: {problem}")

    if os.path.isfile(args.input):  # a single photo
        folder, images = os.path.dirname(args.input), [os.path.basename(args.input)]
    else:
        folder, images = args.input, list(find_images(args.input))
    if not images:
        sys.exit(f"No images found in {args.input}")

    # With several models, each one gets its own sub-folder of the output.
    per_model_dir = len(selected) > 1
    log_path = os.path.join(args.output, "enhancement_log.csv")
    os.makedirs(args.output, exist_ok=True)
    total = len(images) * len(selected)
    print(f"{len(images)} image(s) x {len(selected)} model(s) = {total} job(s)")

    with open(log_path, "a", newline="") as log_file:
        log = csv.writer(log_file)
        if log_file.tell() == 0:
            log.writerow(["file", "model", "parameters", "seconds", "uiqm", "uciqe"])
        done = 0
        for mid in selected:
            model = models[mid]
            values = model.coerce(parse_params(args.param, model))
            print(f"\n{model.name}  {json.dumps(values)}")
            for rel in images:
                done += 1
                src = os.path.join(folder, rel)
                dst = os.path.join(args.output, mid, rel) if per_model_dir else os.path.join(args.output, rel)
                image = cv2.imread(src, cv2.IMREAD_COLOR)
                if image is None:
                    print(f"  [{done}/{total}] {rel}: could not read, skipped")
                    continue
                start = time.perf_counter()
                try:
                    result = model.run(image, values)
                except ValueError as e:
                    print(f"  [{done}/{total}] {rel}: {e}")
                    continue
                elapsed = time.perf_counter() - start
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                cv2.imwrite(dst, result)
                scores = metrics.compute(result) if args.metrics else {}
                log.writerow([os.path.relpath(dst, args.output), mid, json.dumps(values),
                              f"{elapsed:.2f}", scores.get("uiqm", ""), scores.get("uciqe", "")])
                print(f"  [{done}/{total}] {rel}  {elapsed:.1f}s")
    print(f"\nSaved in {args.output} (log: {log_path})")


def _compare_sources(args):
    """The images to compare, as (sheet name, function returning the BGR image or None), and the output folder."""
    from . import video

    if os.path.isdir(args.input):
        folder = os.path.normpath(args.input)
        read = lambda path: lambda: cv2.imread(path, cv2.IMREAD_COLOR)  # noqa: E731
        sources = [(os.path.splitext(rel)[0], read(os.path.join(folder, rel))) for rel in find_images(folder)]
        return sources, args.output or folder + "_compare"
    output = args.output or os.path.dirname(args.input) or "."
    stem = os.path.splitext(os.path.basename(args.input))[0]
    if args.input.lower().endswith(IMAGE_EXTENSIONS):
        return [(stem, lambda: cv2.imread(args.input, cv2.IMREAD_COLOR))], output
    length = video.duration(args.input)
    times = args.time or ([round(length * f, 1) for f in (0.25, 0.5, 0.75)] if length else [0.0])
    return [(f"{stem}_{t:g}s", lambda t=t: video.read_frame(args.input, t)) for t in times], output


def cmd_compare(models, args):
    from . import compare

    if not os.path.exists(args.input):
        sys.exit(f"{args.input} does not exist")
    if args.model:
        for mid in args.model:
            if mid not in models:
                sys.exit(f"Unknown model '{mid}'. Available: {', '.join(models)}")
            if models[mid].check():
                sys.exit(f"{mid}: {models[mid].check()}")
        selected = args.model
    else:
        selected = [mid for mid, m in models.items() if m.check() is None]
        for mid in models:
            if mid not in selected:
                print(f"Skipping {mid}: {models[mid].check()}")
    values = {mid: models[mid].coerce(parse_params(args.param, models[mid])) for mid in selected}
    for mid in selected:
        models[mid].preload()  # so the times shown don't include loading the networks

    sources, output = _compare_sources(args)
    if not sources:
        sys.exit(f"No images found in {args.input}")
    print(f"{len(sources)} image(s) x {len(selected)} method(s)")
    for name, read in sources:
        image = read()
        if image is None:
            print(f"  {name}: could not read it (or the video is shorter), skipped")
            continue
        tiles = [("Original", "", image)]
        for mid in selected:
            start = time.perf_counter()
            try:
                result = models[mid].run(image, values[mid])
            except ValueError as e:
                print(f"  {name}, {mid}: {e}")
                continue
            tiles.append((models[mid].name, f"{mid}, {time.perf_counter() - start:.1f} s", result))
        dst = os.path.join(output, f"{name}_compare.jpg")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        cv2.imwrite(dst, compare.make_sheet(tiles, args.width), [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"  {dst}")


def cmd_video(models, args):
    from . import video

    mid = args.model or next(iter(models))
    if mid not in models:
        sys.exit(f"Unknown model '{mid}'. Available: {', '.join(models)}")
    model = models[mid]
    problem = model.check()
    if problem:
        sys.exit(f"{mid}: {problem}")
    output = args.output or video.default_output(args.input, mid)
    if os.path.abspath(output) == os.path.abspath(args.input):
        sys.exit("The output would overwrite the input; choose another output file.")

    values = model.coerce(parse_params(args.param, model))
    print(f"{model.name}  {json.dumps(values)}\n{args.input} -> {output}")
    start = time.perf_counter()
    try:
        frames = video.enhance_video(args.input, output, model, values, crf=args.crf,
                                     start=args.start, duration=args.duration, jobs=args.jobs)
    except ValueError as e:
        sys.exit(str(e))
    elapsed = time.perf_counter() - start
    print(f"\n{frames} frames in {elapsed:.0f}s ({frames / max(elapsed, 1e-6):.1f} frames/s). Saved {output}")
    # Subtitle timings only match the whole video.
    if args.start == 0 and args.duration is None:
        for sub in video.copy_subtitles(args.input, output):
            print(f"Subtitles copied to {sub}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m nautilus", description="Nautilus underwater image enhancement.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List the available methods, their parameters and the device used.")

    enhance = sub.add_parser("enhance", help="Enhance a photo, or every image in a folder (recursively).")
    enhance.add_argument("input", help="Input photo or folder, e.g. Input")
    enhance.add_argument("output", help="Output folder, e.g. Output. Sub-folders are kept.")
    enhance.add_argument("-m", "--model", action="append",
                         help="Model id (see 'list'). Repeat to compare models; each gets its own sub-folder.")
    enhance.add_argument("-p", "--param", action="append", default=[], metavar="NAME=VALUE",
                         help="Model parameter, e.g. -p sharpen=0.2 (every selected model with that "
                              "parameter) or -p fusion.sharpen=2 (one model). Repeatable.")
    enhance.add_argument("--metrics", action="store_true", help="Also log UIQM/UCIQE quality scores.")

    cmp = sub.add_parser("compare", help="Make one image with the original and every method's result, labelled.")
    cmp.add_argument("input", help="A photo, a folder of photos (one image each) or a video")
    cmp.add_argument("output", nargs="?",
                     help="Output folder (default: the input's folder; for a folder, <folder>_compare)")
    cmp.add_argument("-m", "--model", action="append",
                     help="Only compare these models (default: all of them). Repeatable.")
    cmp.add_argument("-p", "--param", action="append", default=[], metavar="NAME=VALUE",
                     help="Model parameter, as for 'enhance'. Repeatable.")
    cmp.add_argument("--time", type=float, action="append",
                     help="For a video: the second to compare. Repeatable (default: at 1/4, 1/2 and 3/4).")
    cmp.add_argument("--width", type=int, default=1000,
                     help="Width of each picture in the image, in pixels (default 1000).")

    vid = sub.add_parser("video", help="Enhance every frame of a video.")
    vid.add_argument("input", help="Input video, e.g. dive.mp4")
    vid.add_argument("output", nargs="?", help="Output video (default: <input>_<model>.mp4)")
    vid.add_argument("-m", "--model", help="Model id (see 'list'). Default: the first one.")
    vid.add_argument("-p", "--param", action="append", default=[], metavar="NAME=VALUE",
                     help="Model parameter, e.g. -p sharpen=0.2. Repeatable.")
    vid.add_argument("--start", type=float, default=0.0, help="Start at this many seconds (for a quick preview).")
    vid.add_argument("--duration", type=float, help="Only enhance this many seconds (for a quick preview).")
    vid.add_argument("--crf", type=int, default=18, help="H.264 quality: lower is better and larger (default 18).")
    vid.add_argument("--jobs", type=int, default=4, help="Frames processed at the same time (default 4).")

    args = parser.parse_args(argv)
    models = load_models()
    commands = {"list": cmd_list, "enhance": cmd_enhance, "compare": cmd_compare, "video": cmd_video}
    commands[args.command](models, args)


if __name__ == "__main__":
    main()
