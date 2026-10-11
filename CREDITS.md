# Credits

The S-Bike Training Hub is built on other people's open work. Thank you. These are credits, not claims of sponsorship or partnership.

## Built by

**JHarp199345**, with [Claude](https://claude.com) (Anthropic) and ChatGPT (OpenAI) as coding partners. The running-load block model was worked out with ChatGPT and built into the hub with Claude; the hub has since moved to report-based running response (see [how it works](docs/how-it-works.md#status-of-the-models)).

## Maps, routes and terrain

- **Map data:** © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL), served as map tiles built by [Protomaps](https://protomaps.com), with label fonts from [protomaps/basemaps-assets](https://github.com/protomaps/basemaps-assets).
- **Map tiles on your computer:** [go-pmtiles](https://github.com/protomaps/go-pmtiles) (BSD-3-Clause).
- **Map display:** [MapLibre GL JS](https://maplibre.org) (BSD-3-Clause).
- **Routing:** [BRouter](https://github.com/abrensch/brouter) (MIT).
- **Terrain:** [Mapzen terrain tiles](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) on AWS Open Data. Their sources are listed in that attribution.

## Art and 3D

- **Body map:** [body-highlighter](https://www.npmjs.com/package/body-highlighter), based on [react-body-highlighter by GV79 / giavinh79](https://github.com/giavinh79/react-body-highlighter) (MIT). License: [web/vendor/body-highlighter.LICENSE](web/vendor/body-highlighter.LICENSE).
- **3D rendering:** [Three.js](https://threejs.org) (MIT), including its GLTFLoader, SkeletonUtils and BufferGeometryUtils add-ons. License: [web/vendor/three.LICENSE.txt](web/vendor/three.LICENSE.txt).
- **Haunted graveyard:** [Graveyard Kit](https://kenney.nl/assets/graveyard-kit) by [Kenney](https://kenney.nl) (CC0). See [web/graveyard/CREDITS.md](web/graveyard/CREDITS.md).
- **Course animals:** rendered from 3D models by [Quaternius](https://quaternius.com) (CC0). See [web/sprites/CREDITS.md](web/sprites/CREDITS.md).

## Python packages

| Package | Used for | License |
|---|---|---|
| [bleak](https://github.com/hbldh/bleak) | Bluetooth connection to the bike | MIT |
| [bless](https://github.com/kevincar/bless) | Sharing the bike with your watch and apps | MIT |
| [PyObjC](https://pyobjc.readthedocs.io) | macOS Bluetooth and text recognition | MIT |
| [rumps](https://github.com/jaredks/rumps) | macOS menu-bar icon | BSD |
| [Pillow](https://python-pillow.org) | Reading workout images | MIT-CMU |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) (PDFium) | Reading workout PDFs | BSD-3-Clause / Apache-2.0 |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | Text recognition on your computer | Apache-2.0 |
| [ONNX Runtime](https://onnxruntime.ai) | Running the recognition models | MIT |
| [OpenCV](https://opencv.org) (opencv-python) | Image processing for recognition | Apache-2.0 |
| [qrcode](https://github.com/lincolnloop/python-qrcode) | Phone pairing codes | BSD |

## Science

The models build on published work, including:
- Banister's fitness-fatigue model and TRIMP;
- Coggan's TSS and normalized power;
- Skiba's W′ balance;
- Foster's session RPE and the Borg CR-10 scale;
- the Hooper questionnaire (Hooper & Mackinnon 1995);
- the OSTRC overuse injury questionnaire (Clarsen et al. 2013);
- the pain-monitoring model (Silbernagel et al. 2007);
- the energy cost of running and walking (Margaria et al. 1963; Minetti et al. 2002) and the ACSM running equation;
- taper research (Bosquet et al. 2007);
- Williams' EWMA workload ratio;
- Millet et al. (2002) and Tanaka (1994) on cross-training;
- Mike Boyle's progressions and regressions.

Formulas were cross-checked against [GoldenCheetah](https://github.com/GoldenCheetah/GoldenCheetah)'s open-source metrics; no code was copied. None of this research validates the hub's own regional percentages or thresholds, which are labeled as estimates.

## A recommendation

[GoSwimFast's training hub](https://goswimfast.com/training) is a swim workout library and generator the hub's creator uses. It's an independent recommendation, not an integration.
