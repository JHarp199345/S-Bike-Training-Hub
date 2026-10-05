#!/usr/bin/env python3
"""Portable local map setup. Large regional downloads require explicit confirmation."""
import argparse, io, json, math, os, platform, shutil, subprocess, tarfile, urllib.request, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def fetch(url, path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and path.stat().st_size:return
    part=path.with_name(path.name+'.part')
    try:
        with urllib.request.urlopen(url,timeout=120) as response,part.open('wb') as out:shutil.copyfileobj(response,out)
        part.replace(path)
    finally:part.unlink(missing_ok=True)

def unzip(data, dest):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for item in archive.infolist():
            target=(dest/item.filename).resolve()
            if not target.is_relative_to(dest.resolve()):raise ValueError('Unsafe archive path')
            if not item.is_dir():target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(item))

def install_tools(maps):
    for folder in ['tools','web/fonts','brouter/segments4','brouter/customprofiles','map','terrain']:(maps/folder).mkdir(parents=True,exist_ok=True)
    brouter=maps/'tools/brouter/brouter-1.7.10'
    if not (brouter/'brouter-1.7.10-all.jar').exists():
        print('Installing BRouter 1.7.10')
        with urllib.request.urlopen('https://github.com/abrensch/brouter/releases/download/v1.7.10/brouter-1.7.10.zip',timeout=120) as r:unzip(r.read(),maps/'tools/brouter')
    engine=maps/'web/maplibre'
    if not (engine/'maplibre-gl.mjs').exists():
        print('Installing MapLibre GL 6.11.2')
        with urllib.request.urlopen('https://registry.npmjs.org/maplibre-gl/-/maplibre-gl-6.11.2.tgz',timeout=120) as r:
            with tarfile.open(fileobj=io.BytesIO(r.read()),mode='r:gz') as archive:
                for item in archive.getmembers():
                    if item.isfile() and item.name.startswith('package/dist/'):
                        relative=Path(item.name).relative_to('package/dist');target=(engine/relative).resolve()
                        if not target.is_relative_to(engine.resolve()):raise ValueError('Unsafe map engine path')
                        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.extractfile(item).read())
    binary=maps/'tools/pmtiles/pmtiles'
    if not binary.exists():
        system=platform.system();arch={'aarch64':'arm64','arm64':'arm64','x86_64':'x86_64','AMD64':'x86_64'}.get(platform.machine())
        if system not in ('Linux','Darwin') or not arch:raise ValueError('Automatic map extraction supports macOS/Linux on ARM64 or x86-64')
        with urllib.request.urlopen('https://api.github.com/repos/protomaps/go-pmtiles/releases/tags/v1.31.2',timeout=30) as r:release=json.load(r)
        asset=next(a for a in release['assets'] if f'_{system}_{arch}.' in a['name'])
        print('Installing pmtiles 1.31.2 for',system,arch)
        with urllib.request.urlopen(asset['browser_download_url'],timeout=120) as r:data=r.read()
        if asset['name'].endswith('.zip'):unzip(data,binary.parent)
        else:
            with tarfile.open(fileobj=io.BytesIO(data),mode='r:*') as archive:
                member=next(m for m in archive.getmembers() if m.isfile() and Path(m.name).name=='pmtiles')
                binary.parent.mkdir(parents=True,exist_ok=True);binary.write_bytes(archive.extractfile(member).read())
        binary.chmod(0o755)
    for font in ['Noto Sans Regular','Noto Sans Medium','Noto Sans Italic']:
        for span in ['0-255','256-511','512-767','7680-7935','8192-8447']:
            fetch('https://raw.githubusercontent.com/protomaps/basemaps-assets/main/fonts/'+font.replace(' ','%20')+'/'+span+'.pbf',maps/'web/fonts'/font/(span+'.pbf'))
    print('Map tools installed. Regional data is separate; no region has been downloaded automatically.')

def regions(maps):
    config=json.loads((ROOT/'regions.json').read_text())['regions'];tiles=set()
    for region in config:
        w,s,e,n=region['bbox']
        for x in range(math.floor(w/5)*5,math.ceil(e/5)*5,5):
            for y in range(math.floor(s/5)*5,math.ceil(n/5)*5,5):tiles.add(f"{'W' if x<0 else 'E'}{abs(x)}_{'S' if y<0 else 'N'}{abs(y)}")
    print('Regions:',', '.join(r['name'] for r in config))
    if input(f'Download {len(tiles)} road tiles (roughly 50–100 MB each)? [y/N] ').lower()=='y':
        for tile in sorted(tiles):
            try:fetch('https://brouter.de/brouter/segments4/'+tile+'.rd5',maps/'brouter/segments4'/(tile+'.rd5'))
            except Exception as error:print('Road tile',tile,'not downloaded:',error)
    if input('Download street maps for these regions (potentially several GB)? [y/N] ').lower()=='y':
        with urllib.request.urlopen('https://build-metadata.protomaps.dev/builds.json',timeout=30) as r:build=json.load(r)[-1]['key']
        for region in config:
            w,s,e,n=region['bbox'];nx=max(1,math.ceil((e-w)/5));ny=max(1,math.ceil((n-s)/5))
            for i in range(nx):
                for j in range(ny):
                    bbox=','.join(str(v) for v in [w+(e-w)*i/nx,s+(n-s)*j/ny,w+(e-w)*(i+1)/nx,s+(n-s)*(j+1)/ny]);dest=maps/'map'/f"{region['name'].lower().replace(' ','-')}-{i}{j}.pmtiles"
                    if dest.exists():continue
                    part=dest.with_suffix('.part');subprocess.run([str(maps/'tools/pmtiles/pmtiles'),'extract','https://build.protomaps.com/'+build,str(part),'--bbox='+bbox,'--maxzoom=14','--download-threads=4'],check=True);part.replace(dest)
    print('Route planning requires Java and road data. Street maps work without elevation; optional terrain can be added later.')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tools-only',action='store_true');parser.add_argument('--maps',type=Path);args=parser.parse_args()
    maps=args.maps or Path(os.environ.get('S_BIKE_MAPS',str(ROOT/'maps')))
    install_tools(maps)
    if not args.tools_only:regions(maps)
if __name__=='__main__':main()
