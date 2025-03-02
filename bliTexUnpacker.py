import os
import argparse
import asyncio
import struct
import logging
import time

#######################################################################################################
# Log Colored Formatter

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.DEBUG:
            record.msg = f"\033[0m[DEBG] {record.msg}\033[0m"
        elif record.levelno == logging.INFO:
            record.msg = f"\033[32m[INFO] {record.msg}\033[0m"
        elif record.levelno == logging.WARNING:
            record.msg = f"\033[33m[WARN] {record.msg}\033[0m"
        elif record.levelno == logging.ERROR:
            record.msg = f"\033[31m[ERRO] {record.msg}\033[0m"
        elif record.levelno == logging.CRITICAL:
            record.msg = f"\033[35m[CRIT] {record.msg}\033[0m"
        return super().format(record)
 
LOG_FORMATTER = '%(message)s' # '[%(asctime)s]%(message)s'
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter(LOG_FORMATTER))
logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

#######################################################################################################
# DDS Header

# DDS header define
DDS_MAGIC = b'DDS '
DDS_HEADER_SIZE = 124
DDS_PIXELFORMAT_SIZE = 32

# DDS hader flags
DDSD_CAPS        = 0x00000001
DDSD_HEIGHT      = 0x00000002
DDSD_WIDTH       = 0x00000004
DDSD_PITCH       = 0x00000008
DDSD_PIXELFORMAT = 0x00001000
DDSD_MIPMAPCOUNT = 0x00020000
DDSD_LINEARSIZE  = 0x00080000 

# DDS Cap flags
DDSCAPS_TEXTURE  = 0x00001000
DDSCAPS_MIPMAP   = 0x00400000
DDSCAPS_COMPLEX  = 0x00000008

# DXGI define
DXGI_FORMAT_UNKNOWN                 = 0x00
DXGI_FORMAT_BC1_UNORM               = 0x47
DXGI_FORMAT_BC3_UNORM               = 0x4D
DXGI_FORMAT_R8G8B8A8_UNORM          = 0x1C
D3D10_RESOURCE_DIMENSION_TEXTURE2D  = 0x03

def create_r8g8b8a8_unorm_header(width: int, height: int, mipmap_count=1) -> bytes:
    # 计算基本标志
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_PITCH
    if mipmap_count > 1:
        flags |= DDSD_MIPMAPCOUNT
    # 计算行间距 (每行字节数)
    pitch = width * 4  # 每个像素 4 字节 (8位 x 4通道)
    # 组装 DDS_PIXELFORMAT 结构
    ddspf = struct.pack(
        '<II4sIIIII',
        DDS_PIXELFORMAT_SIZE,   # dwSize
        0x4,                    # dwFlags (DDPF_FOURCC)
        b'DX10',                # dwFourCC
        0,                      # dwRGBBitCount
        0,                      # dwRBitMask
        0,                      # dwGBitMask
        0,                      # dwBBitMask
        0                       # dwABitMask
    )
    # 计算能力标志
    caps1 = DDSCAPS_TEXTURE
    if mipmap_count > 1:
        caps1 |= DDSCAPS_COMPLEX | DDSCAPS_MIPMAP
    # 组装 DDS_HEADER
    header = struct.pack(
        '<IIIIIII11I32sIIIII',
        DDS_HEADER_SIZE,         # dwSize
        flags,                   # dwFlags
        height,                  # dwHeight
        width,                   # dwWidth
        pitch,                   # dwPitch
        1,                       # dwDepth (2D纹理)
        mipmap_count,            # dwMipMapCount
        # dwReserved1 (11个保留字段)
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        ddspf,                   # DDS_PIXELFORMAT
        caps1,                   # dwCaps
        0,                       # dwCaps2
        0,                       # dwCaps3
        0,                       # dwCaps4
        0                        # dwReserved2
    )
    # 组装 DX10 扩展头
    dx10_header = struct.pack(
        '<5I',
        DXGI_FORMAT_R8G8B8A8_UNORM, # dxgiFormat
        D3D10_RESOURCE_DIMENSION_TEXTURE2D, # resourceDimension
        0,  # miscFlag
        1,  # arraySize (单张纹理)
        0   # miscFlags2
    )
    # 合并所有部分
    return DDS_MAGIC + header + dx10_header

def create_bc_unorm_header(ver: int, width: int, height: int, mipmap_count=1) -> bytes:
    klen = 0
    dxt_name = b'DXT1'
    # Check version
    if ver == 1:
        dxt_name = b'DXT1'
        klen = 8
    elif ver == 3:
        dxt_name = b'DXT5'
        klen = 16
    else:
        logger.warning('Unsupport BC format version')
        return None
    # 验证宽高是否为4的倍数（BC压缩格式要求）
    if width % 4 != 0 or height % 4 != 0:
        logger.warning('Width and height must be multiples of 4 for BC format')
        return None
    # 计算标志位
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    if mipmap_count > 1:
        flags |= DDSD_MIPMAPCOUNT
    # 计算线性大小（ BC1 每个块 4x4 像素，占 8 字节）
    # 计算线性大小（ BC3 每个块 4x4 像素，占 16 字节）
    block_count_x = max(1, (width + 3) // 4)
    block_count_y = max(1, (height + 3) // 4)
    linear_size = block_count_x * block_count_y * klen
    # DDS_PIXELFORMAT 结构
    ddspf = struct.pack(
        '<II4sIIIII',
        DDS_PIXELFORMAT_SIZE,
        0x4,        # DDPF_FOURCC
        dxt_name,   # 使用 DXT 扩展头
        0, 0, 0, 0, 0
    )
    # 能力标志
    caps1 = DDSCAPS_TEXTURE
    if mipmap_count > 1:
        caps1 |= DDSCAPS_COMPLEX | DDSCAPS_MIPMAP
    # 主 DDS 头
    header = struct.pack(
        '<IIIIIII11I32sIIIII',
        DDS_HEADER_SIZE,
        flags,
        height,
        width,
        linear_size,  # 此处存储线性大小
        1,            # dwDepth (2D纹理)
        mipmap_count,
        # 保留字段
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        ddspf,
        caps1,
        0, 0, 0, 0    # 其他caps和保留
    )
    return DDS_MAGIC + header

def create_bc1_unorm_header(width: int, height: int, mipmap_count=1) -> bytes:
    return create_bc_unorm_header(1, width, height, mipmap_count)
    
def create_bc3_unorm_header(width: int, height: int, mipmap_count=1) -> bytes:
    return create_bc_unorm_header(3, width, height, mipmap_count)

#######################################################################################################
# Texture Header

class TexHeader:
    uint32_bli_pos  = 0
    uint32_unk0     = 0
    uint32_unk1     = 0
    uint32_unk2     = 0
    uint16_width    = 0
    uint16_height   = 0
    uint16_unk3     = 0
    uint08_fmt      = 0
    uint08_mips     = 0
    uint32_unk4     = 0
    
    mipmap_count    = 0
    base_size       = 0
    raw_size        = 0
    bswizzle        = False
    dds_header      = None
    fmt_type        = DXGI_FORMAT_UNKNOWN
    fmt_name        = ''
    name            = ''
    
    def __init__(self, data: bytes):
        if len(data) < 4 * 7:
            logger.error('TEX header data is too small')
            return
        values = struct.unpack('>4I3H2B1I', data)
        self.uint32_bli_pos  = values[0]
        self.uint32_unk0     = values[1]
        self.uint32_unk1     = values[2]
        self.uint32_unk2     = values[3]
        self.uint16_width    = values[4]
        self.uint16_height   = values[5]
        self.uint16_unk3     = values[6]
        self.uint08_fmt      = values[7]
        self.uint08_mips     = values[8]
        self.uint32_unk4     = values[9]
        self.__build_fmt_type__()
        self.__build_mips__()
        self.__build_dds__()
        self.setName()

    def __build_fmt_type__(self):
        val = self.uint08_fmt
        if val == 0x85:
            self.raw_size = self.uint16_width * self.uint16_height * 4
            self.fmt_type = DXGI_FORMAT_R8G8B8A8_UNORM
            self.fmt_name = 'R8G8B8A8'
            self.bswizzle = True
        elif val == 0x86 or val == 0xA6:
            self.raw_size = self.uint16_width * self.uint16_height / 2
            self.fmt_type = DXGI_FORMAT_BC1_UNORM
            self.fmt_name = 'BC1'
        elif val == 0x88:
            self.raw_size = self.uint16_width * self.uint16_height
            self.fmt_type = DXGI_FORMAT_BC3_UNORM
            self.fmt_name = 'BC3'
        else:
            self.raw_size = 0
            self.fmt_type = DXGI_FORMAT_UNKNOWN
            self.fmt_name = f'UNK{val:02X}'
    
    def __build_mips__(self):
        self.mipmap_count = 0
        bsize = self.raw_size
        width = self.uint16_width
        height = self.uint16_height
        self.base_size = self.raw_size
        for idx in range(self.uint08_mips):
            add_one = 1
            if idx != 0:
                bsize = bsize // 4
                width = width // 2
                height = height // 2
                self.raw_size += bsize
            if self.fmt_type == DXGI_FORMAT_BC1_UNORM or self.fmt_type == DXGI_FORMAT_BC3_UNORM:
                if width < 4 or height < 4:
                    add_one = 0
            elif width <= 0 or height <= 0:
                add_one = 0
            self.mipmap_count += add_one
            
    def __build_dds__(self):
        if self.fmt_type == DXGI_FORMAT_R8G8B8A8_UNORM:
            self.dds_header = create_r8g8b8a8_unorm_header(self.uint16_width, self.uint16_height, self.mipmap_count)
        elif self.fmt_type == DXGI_FORMAT_BC1_UNORM:
            self.dds_header = create_bc1_unorm_header(self.uint16_width, self.uint16_height, self.mipmap_count)
        elif self.fmt_type == DXGI_FORMAT_BC3_UNORM:
            self.dds_header = create_bc3_unorm_header(self.uint16_width, self.uint16_height, self.mipmap_count)

    def setName(self, name=''):
        slen = len(name)
        self.name = f'0x{self.uint32_bli_pos:08X}' if slen == 0 else name
        
    def getName(self) -> str:
        return self.name
        
    def getFullName(self, show_sw_flag=True) -> str:
        return f'{self.name}@0x{self.uint32_bli_pos:08X}.{self.getFmtName(show_sw_flag)}'
        
    def getFmtName(self, show_sw_flag=True) -> str:
        if show_sw_flag and self.bswizzle:
            return f'{self.fmt_name}-PS3Swizzle'
        return self.fmt_name
        
    def getFmtType(self) -> int:
        return self.fmt_type
        
    def isSwizzle(self) -> bool:
        return self.bswizzle
        
    def getPosition(self) -> int:
        return self.uint32_bli_pos
        
    def getRawSize(self) -> int:
        if self.raw_size == 0:
            logger.warning(f'Canot get texture raw data size for unknown format(0x{self.uint08_fmt:02X}) @0x{self.uint32_bli_pos:08X}')
        return self.raw_size
        
    def getBaseRawSize(self) -> int:
        return self.base_size
        
    def getMipmapNum(self, auto_fix_flag=False) -> int:
        if not auto_fix_flag:
            return self.uint08_mips
        return self.mipmap_count
        
    def getDDSHeader(self) -> bytes:
        return self.dds_header
        
    def width(self) -> int:
        return self.uint16_width

    def height(self) -> int:
        return self.uint16_height

    def printStruct(self):
        print(f'uint32_bli_pos  = 0x{self.uint32_bli_pos:08X}')
        print(f'uint32_unk0     = 0x{self.uint32_unk0:08X}')
        print(f'uint32_unk1     = 0x{self.uint32_unk1:08X}')
        print(f'uint32_unk2     = 0x{self.uint32_unk2:08X}')
        print(f'uint16_width    = {self.uint16_width}')
        print(f'uint16_height   = {self.uint16_height}')
        print(f'uint08_fmt      = 0x{self.uint08_fmt:02X}')
        print(f'uint08_mips     = 0x{self.uint08_mips:02X}')
        print(f'uint32_unk4     = 0x{self.uint32_unk4:04X}')

#######################################################################################################
# Bundle Texture Header

class BlhHeader:
    uint32_prefix   = 0
    uint32_unk0     = 0
    uint32_lp_strtb = 0
    uint32_unk1     = 0
    uint32_num      = 0
    uint32_unk2     = 0
    uint32_padding0 = 0
    uint32_padding1 = 0
    texHdrs: list[TexHeader] = []
    b_OK = False
    
    def __read_string__(self, file) -> str:
        result = bytearray()
        while True:
            byte = file.read(1)
            if not byte or byte == b'\x00':
                break
            result.extend(byte)
        return result.decode('utf-8')

    def __init__(self, filename: str):
        # Check file exists
        if not os.path.exists(filename):
            logger.error(f'{filename} is not found')
            return
        # Start read file
        with open(filename, 'rb') as f:
            # Get file size
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            f.seek(0, os.SEEK_SET)
            # Read blh header
            data = f.read(4 * 8)
            if len(data) < 4 * 8:
                logger.error('BLH header file is too small')
                return
            values = struct.unpack('>8I', data)
            self.uint32_prefix   = values[0]
            self.uint32_unk0     = values[1]
            self.uint32_lp_strtb = values[2]
            self.uint32_unk1     = values[3]
            self.uint32_num      = values[4]
            self.uint32_unk2     = values[5]
            self.uint32_padding0 = values[6]
            self.uint32_padding1 = values[7]
            # Check prefix
            if self.uint32_prefix != 0x040E0000:
                logger.error('BLH prefix is not 0x040E0000')
                return
            # Read rexture header data
            for i in range(values[4]):
                texHdr = TexHeader(f.read(4 * 7))
                self.texHdrs.append(texHdr)
            # Load all rexture header done
            self.b_OK = True
            # Start to find rexture file name
            if values[2] >= file_size:
                logger.warning('Invalid string table pointer, cannot build texture file name')
                return
            # Read string pointers table
            f.seek(values[2], os.SEEK_SET)
            data = f.read(4 * values[4])
            if len(data) < 4 * values[4]:
                logger.warning('Real string table size is too small, cannot build texture file name')
                return
            # Unpacking all string data
            addrs = struct.unpack(f'>{values[4]}I', data)
            for i in range(values[4]):
                f.seek(addrs[i], os.SEEK_SET)
                self.texHdrs[i].setName(self.__read_string__(f))

    def isOK(self) -> bool:
        return self.b_OK
                
    def getTextureNum(self) -> int:
        return self.uint32_num
        
    def getTextureHeader(self, index: int) -> TexHeader: 
        return self.texHdrs[index]
                
    def printBaseStruct(self):
        print(f'uint32_prefix   = 0x{self.uint32_prefix:08X}')
        print(f'uint32_unk0     = 0x{self.uint32_unk0:08X}')
        print(f'uint32_lp_strtb = 0x{self.uint32_lp_strtb:08X}')
        print(f'uint32_unk1     = 0x{self.uint32_unk1:08X}')
        print(f'uint32_num      = {self.uint32_num}')
        print(f'uint32_unk2     = 0x{self.uint32_unk2:08X}')
        print(f'uint32_padding0 = 0x{self.uint32_padding0:08X}')
        print(f'uint32_padding1 = 0x{self.uint32_padding1:08X}')
        
#######################################################################################################
# PS3 swizzle

def base_get_src_pos(size: int, x: int, y: int) -> int:
    if size == 4:
        return 0
    half = size // 2
    if x < half:
        if y < half: # top left quadrant
            return base_get_src_pos(half, x, y)
        else: # bottom left quadrant
            return base_get_src_pos(half, x, y - half) + (size * size // 2)
    else:
        if y < half: # top right quadrant
            return base_get_src_pos(half, x - half, y) + (size * size // 4)
        else: # bottom right quadrant
            return base_get_src_pos(half, x - half, y - half) + (3 * size * size // 4)

def get_src_pos(width: int, height: int, x: int, y: int) -> int:
    if width > height: # wide case
        adjusted_x = x - ((x // height) * height)
        return base_get_src_pos(height, adjusted_x, y) + ((x // height) * height)
    elif width < height: # tall case
        adjusted_y = y - ((y // width) * width)
        return base_get_src_pos(height, x, adjusted_y) + (((y // width) * width) * width)
    else: # square case
        return base_get_src_pos(width, x, y)

def ps3_unswiz(data: bytes, width: int, height: int) -> bytes:
    total = width * height * 4
    dlen = len(data)
    if dlen < total:
        logger.warning(f'ps3_unswiz(): Input data size is too small ({dlen} < {total}), it cannot be unswizzled')
        return data
    in_array = struct.unpack(f'>{width * height}I', data)
    out = [0] * (width * height)
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            srcpos = get_src_pos(width, height, x, y)
            #
            out[y * width + x] = in_array[srcpos]
            out[y * width + x + 1] = in_array[srcpos + 1]
            out[(y + 1) * width + x] = in_array[srcpos + 2]
            out[(y + 1) * width + x + 1] = in_array[srcpos + 3]
            #
            out[y * width + x + 2] = in_array[srcpos + 4]
            out[y * width + x + 3] = in_array[srcpos + 5]
            out[(y + 1) * width + x + 2] = in_array[srcpos + 6]
            out[(y + 1) * width + x + 3] = in_array[srcpos + 7]
            #
            out[(y + 2) * width + x] = in_array[srcpos + 8]
            out[(y + 2) * width + x + 1] = in_array[srcpos + 9]
            out[(y + 3) * width + x] = in_array[srcpos + 10]
            out[(y + 3) * width + x + 1] = in_array[srcpos + 11]
            #
            out[(y + 2) * width + x + 2] = in_array[srcpos + 12]
            out[(y + 2) * width + x + 3] = in_array[srcpos + 13]
            out[(y + 3) * width + x + 2] = in_array[srcpos + 14]
            out[(y + 3) * width + x + 3] = in_array[srcpos + 15]
    byte_array = struct.pack('>' + 'I' * len(out), *out)
    return byte_array
    
def ps3_mipmap_unswiz(data: bytes, width: int, height: int, mipmap_count=1) -> bytes:
    offset = 0
    result = bytes()
    for idx in range(mipmap_count):
        klen = width * height * 4
        cdata = data[offset:(offset + klen)]
        result += ps3_unswiz(cdata, width, height)
        width = width // 2
        height = height // 2
        offset += klen
    return result
        
#######################################################################################################
# Read Write Binary File

def read_bytes_from_file(idx: int, filename: str, beg_pos: int, dlen: int) -> bytes:
    with open(filename, 'rb') as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        if beg_pos >= file_size:
            logger.error(f'[{idx:03}] Start position (0x{beg_pos:08X}) is bigger than file size')
            return None
        if (beg_pos + dlen) > file_size:
            logger.warning(f'[{idx:03}] Overflow at 0x{beg_pos:08X} (Size:{dlen})')
        f.seek(beg_pos)
        data = f.read(int(min(dlen, file_size - beg_pos)))
    return data

def write_bytes_to_file(filename: str, data: bytes, hdr: bytes):
    with open(filename, 'wb') as f:
        if hdr is not None:
            f.write(hdr)
        f.write(data)

#######################################################################################################
# Main

async def main(args):
    # Parse *.blh file
    bundle = BlhHeader(args.blh)
    if not bundle.isOK():
        return
    logger.info(f'{args.blh} parsed DONE')
    # Show *.blh file structure
    if args.show or not args.bli:
        time.sleep(1) 
        for i in range(bundle.getTextureNum()):
            if i == 0:
                print('############################################')
                print('# TEX Bundle Header:')
                bundle.printBaseStruct()
                print('============================================')
            else:
                print('-----------------------------')
            hdr = bundle.getTextureHeader(i)
            print(hdr.getName(), f'({hdr.getFmtName()}):')
            hdr.printStruct()
    # Check *.bli exists
    if not args.bli:
        return
    if not os.path.exists(args.bli):
        logger.error(f'{args.bli} is not found')
        return
    # Check output path
    output = args.out if args.out else './'
    if not os.path.exists(output):
        logger.warning('Output path is not exists, use the default path')
        output = './'
    output = os.path.join(output, os.path.splitext(args.bli)[0])
    os.makedirs(output, exist_ok=True)
    # Start unpacking *.bli
    print(f'Start unpacking {args.bli} into {output}')
    for i in range(bundle.getTextureNum()):
        hdr = bundle.getTextureHeader(i)
        pos = hdr.getPosition()
        len = hdr.getRawSize()
        if len == 0:
            logger.warning(f'Pass unpack {hdr.getName()}')
            continue
        data = read_bytes_from_file(i + 1, args.bli, pos, len)  
        if data is None:
            logger.warning(f'Pass unpack {hdr.getName()}')
            continue
        if hdr.getMipmapNum() != hdr.getMipmapNum(True):
            logger.debug(f'[{(i + 1):03}] Mipmap count reduce form {hdr.getMipmapNum()} to {hdr.getMipmapNum(True)}')    
        if hdr.getFmtType() == DXGI_FORMAT_R8G8B8A8_UNORM and hdr.isSwizzle():
            data = ps3_mipmap_unswiz(data, hdr.width(), hdr.height(), hdr.getMipmapNum())
        ext_name = 'raw'
        if hdr.getDDSHeader() is not None:
            ext_name = 'dds'
        output_file = f'{output}/{hdr.getFullName(False)}.{ext_name}'
        write_bytes_to_file(output_file, data, hdr.getDDSHeader())
        logger.info(f'[{(i + 1):03}] {output_file}')

def args_parser():
    parser = argparse.ArgumentParser(description='Invizimals Texture Unpacker')
    parser.add_argument('-b', '--blh', type=str, required=True,  help='Give a *.blh header file for texture bundle')
    parser.add_argument('-i', '--bli', type=str, required=False, help='Give a *.bli texture file for unpacking')
    parser.add_argument('-o', '--out', type=str, required=False, help='Set an output path for texture unpacking')
    parser.add_argument('--show', action='store_true', default=False, help='Show structure detail')
    return parser.parse_args()

if __name__ == "__main__":
    args = args_parser()
    asyncio.run(main(args))
