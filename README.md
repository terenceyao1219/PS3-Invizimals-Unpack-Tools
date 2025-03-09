# Overview
This project is the result of research on extracting modeling resources from the PS3 game Invizimals The Lost Kingdom. 

Two Python3 script tools are provided here：

* Texture Unpacker
* PAK Mesh Finder (include bones & weights)

# Texture Unpacker
This tool outputs files in DDS format. If the texture format is unknown, it will generate a raw file instead.
```
usage: bliTexUnpacker.py [-h] -b BLH [-i BLI] [-o OUT] [--show]

Invizimals Texture Unpacker

options:
  -h, --help         show this help message and exit
  -b BLH, --blh BLH  Give a *.blh header file for texture bundle
  -i BLI, --bli BLI  Give a *.bli texture file for unpacking
  -o OUT, --out OUT  Set an output path for texture unpacking
  --show             Show structure detail
```
Usage example：
```
python3 bliTexUnpacker.py -b Award_Shizoku_QTE.blh -i Award_Shizoku_QTE.bli -o D:\GameArchive\PS3\Invizimals
```

# PAK Model Finder
This tool only outputs **Parameter List Container** in ***.plc*** file.

Please use [AXE (Advanced Mesh Reaper - Xtreme Edition)](https://github.com/Bigchillghost/AXE) to open it and  export models from PAK file.

⚠ NOTE：If the Parameter List Container contains multiple mesh objects, it's recommended to export them separately. AXE has a bug in weight assignment; if different meshes use the same bones, AXE will assign broken weights.
```
usage: pakModelFinder.py [-h] -p PAK [-m MESH] [-b BONE] [-s SKIP] [-r] [-a] [-t]

Invizimals PAK Model Finder

options:
  -h, --help            show this help message and exit
  -p PAK, --pak PAK     Give a *.pak file for creating AXE(*.plc) content
  -m MESH, --mesh MESH  Set the HEX offset of mesh data section manually (default: auto)
  -b BONE, --bone BONE  Set the HEX offset of bone data section manually (default: auto)
  -s SKIP, --skip SKIP  Skip the first N meshes (default: 0)
  -r, --reverse         Reverse the order of the mesh list (default: OFF)
  -a, --rename          Rename the mesh with bone indices (default: OFF)
  -t, --split           Split different meshs to different plc files (default: OFF)
```
Usage example for auto case：
```
python3 pakModelFinder.py -p Award_XiongMao.pak -r -s 4
```
Usage example for manual case：
```
python3 pakModelFinder.py -p objects.pak -m d75570 -b dc1770
```
